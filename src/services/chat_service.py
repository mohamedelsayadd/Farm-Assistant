import json
import logging
import time
from functools import lru_cache
from typing import Any

from services.chat_prompts import SYSTEM_PROMPT
from services.llm.factory import get_llm_client
from services.llm.interface import LLMClient
from services.farm_tools import execute_tool
from services.memory.factory import get_chat_memory
from services.memory.interface import ChatMemory


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_farm_info",
            "description": "Get structured farm information, connectivity details, configured sensors, latest sensor readings, units, thresholds, and reading timestamps.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_devices_status",
            "description": "Get current mock status for farm devices: fans, pumps, and lights.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]
logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, llm_client: LLMClient, chat_memory: ChatMemory | None = None) -> None:
        self.llm_client = llm_client
        self.chat_memory = chat_memory

        logger.info("chat_service_initialized")

    async def get_answer(self, JWT: str, conversation_id: str, user_message: str) -> str:
        start_time = time.perf_counter()
        logger.info("chat_started conversation_id=%s message_length=%s", conversation_id, len(user_message))
        messages = await self._build_messages(conversation_id, user_message)

        try:
            first_response = await self.llm_client.create_chat_completion(
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception:
            logger.exception("chat_initial_llm_call_failed message_length=%s", len(user_message))
            raise

        assistant_message = first_response.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            answer = assistant_message.content or "لا أستطيع تقديم إجابة واضحة في الوقت الحالي."
            await self._save_exchange(conversation_id, user_message, answer)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "chat_completed tool_calls=0 answer_length=%s duration_ms=%.2f",
                len(answer),
                duration_ms,
            )
            return answer

        logger.info("chat_tool_calls_requested count=%s", len(tool_calls))
        messages.append(assistant_message.model_dump(exclude_none=True))

        for tool_call in tool_calls:
            logger.info("chat_tool_call_started tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
            tool_result = await execute_tool(JWT=JWT,
                                              name=tool_call.function.name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
            logger.info("chat_tool_call_completed tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)

        try:
            final_response = await self.llm_client.create_chat_completion(
                messages=messages,
                tools=TOOLS,
                tool_choice="none",
            )
        except Exception:
            logger.exception("chat_final_llm_call_failed tool_call_count=%s", len(tool_calls))
            raise

        answer = final_response.choices[0].message.content or "لا أستطيع تقديم إجابة واضحة في الوقت الحالي."
        await self._save_exchange(conversation_id, user_message, answer)
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "chat_completed tool_calls=%s answer_length=%s duration_ms=%.2f",
            len(tool_calls),
            len(answer),
            duration_ms,
        )
        return answer

    async def _build_messages(self, conversation_id: str, user_message: str) -> list[dict[str, Any]]:
        if self.chat_memory is None:
            return [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

        messages = await self.chat_memory.get_messages(conversation_id)
        messages.append({"role": "user", "content": user_message})
        return messages

    async def _save_exchange(self, conversation_id: str, user_message: str, answer: str) -> None:
        if self.chat_memory is None:
            return
        await self.chat_memory.save_exchange(conversation_id, user_message, answer)


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(get_llm_client(), get_chat_memory())
