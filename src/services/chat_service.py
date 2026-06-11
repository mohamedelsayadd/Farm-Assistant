import json
import logging
import time
from functools import lru_cache
from typing import Any

from services.chat_prompts import SYSTEM_PROMPT
from services.llm.factory import get_llm_client
from services.llm.interface import LLMClient
from services.farm_tools import execute_tool
from services.input_guardrail.factory import get_input_guardrail
from services.input_guardrail.interface import InputGuardrail
from services.memory.factory import get_chat_memory
from services.memory.interface import ChatMemory
from core.settings import get_settings


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_farm_info",
            "description": "Get cleaned farm devices data including farm name, device names, employees, latest sensor readings, units, thresholds, Arabic labels, and reading timestamps.",
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
            "name": "get_device_id",
            "description": "Get all farm device names mapped to their device IDs. Use this when the user needs a device ID or asks for something requiring a device ID from a device name.",
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
            "name": "get_sensors_reads_at_time",
            "description": "Get historical sensor readings for a specific device and time range. Use only after calling get_device_id and selecting the matching device_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device ID selected from get_device_id results.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time requested by the user in ISO 8601 format.",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time requested by the user in ISO 8601 format. Used to clip returned data.",
                    },
                    "data_type": {
                        "type": "string",
                        "enum": ["day", "hour"],
                        "description": "Use day for daily readings and hour for hourly readings.",
                    },
                },
                "required": ["device_id", "start_time", "end_time", "data_type"],
                "additionalProperties": False,
            },
        },
    },
]
logger = logging.getLogger(__name__)
MAX_TOOL_CALL_ROUNDS = 3
DEFAULT_INPUT_GUARDRAIL_BLOCK_MESSAGE = (
    "لا أستطيع معالجة هذا الطلب لأنه قد يحتوي على تعليمات غير آمنة أو محاولة للتلاعب بالنظام."
)


class ChatService:
    def __init__(
        self,
        llm_client: LLMClient,
        chat_memory: ChatMemory | None = None,
        input_guardrail: InputGuardrail | None = None,
        input_guardrail_fail_closed: bool = True,
        input_guardrail_block_message: str = DEFAULT_INPUT_GUARDRAIL_BLOCK_MESSAGE,
    ) -> None:
        self.llm_client = llm_client
        self.chat_memory = chat_memory
        self.input_guardrail = input_guardrail
        self.input_guardrail_fail_closed = input_guardrail_fail_closed
        self.input_guardrail_block_message = input_guardrail_block_message

        logger.info("chat_service_initialized")

    async def get_answer(self, JWT: str, conversation_id: str, user_message: str) -> str:
        start_time = time.perf_counter()
        logger.info("chat_started conversation_id=%s message_length=%s", conversation_id, len(user_message))
        guardrail_answer = await self._check_input_guardrail(user_message)
        if guardrail_answer is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info("chat_blocked_by_input_guardrail duration_ms=%.2f", duration_ms)
            return guardrail_answer

        messages = await self._build_messages(conversation_id, user_message)

        total_tool_calls = 0
        answer = "لا أستطيع تقديم إجابة واضحة في الوقت الحالي."
        for tool_round in range(MAX_TOOL_CALL_ROUNDS):
            try:
                response = await self.llm_client.create_chat_completion(
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
            except Exception:
                logger.exception(
                    "chat_llm_call_failed message_length=%s tool_round=%s",
                    len(user_message),
                    tool_round,
                )
                raise

            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []

            if not tool_calls:
                answer = assistant_message.content or answer
                break

            total_tool_calls += len(tool_calls)
            logger.info("chat_tool_calls_requested count=%s round=%s", len(tool_calls), tool_round + 1)
            messages.append(assistant_message.model_dump(exclude_none=True))

            for tool_call in tool_calls:
                logger.info("chat_tool_call_started tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
                tool_arguments = self._parse_tool_arguments(tool_call)
                logger.info(
                    "chat_tool_call_arguments tool_call_id=%s tool_name=%s arguments=%s",
                    tool_call.id,
                    tool_call.function.name,
                    json.dumps(tool_arguments, ensure_ascii=False) if isinstance(tool_arguments, dict) else tool_arguments,
                )
                if isinstance(tool_arguments, dict):
                    tool_result = await execute_tool(
                        JWT=JWT,
                        name=tool_call.function.name,
                        arguments=tool_arguments,
                    )
                else:
                    tool_result = {"error": tool_arguments}
                tool_result_content = json.dumps(tool_result, ensure_ascii=False)
                logger.info(
                    "chat_tool_call_result_for_llm tool_call_id=%s tool_name=%s result=%s",
                    tool_call.id,
                    tool_call.function.name,
                    tool_result_content,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result_content,
                    }
                )
                logger.info("chat_tool_call_completed tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
        else:
            try:
                final_response = await self.llm_client.create_chat_completion(
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="none",
                )
            except Exception:
                logger.exception("chat_final_llm_call_failed tool_call_count=%s", total_tool_calls)
                raise
            answer = final_response.choices[0].message.content or answer

        await self._save_exchange(conversation_id, user_message, answer)
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "chat_completed tool_calls=%s answer_length=%s duration_ms=%.2f",
            total_tool_calls,
            len(answer),
            duration_ms,
        )
        return answer

    def _parse_tool_arguments(self, tool_call: Any) -> dict[str, Any] | str:
        raw_arguments = getattr(tool_call.function, "arguments", None)
        if raw_arguments in (None, ""):
            return {}

        try:
            parsed_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            logger.warning("chat_tool_arguments_invalid_json tool_name=%s", tool_call.function.name)
            return "Tool arguments must be valid JSON."

        if not isinstance(parsed_arguments, dict):
            logger.warning("chat_tool_arguments_invalid_type tool_name=%s", tool_call.function.name)
            return "Tool arguments must be a JSON object."

        return parsed_arguments

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

    async def _check_input_guardrail(self, user_message: str) -> str | None:
        if self.input_guardrail is None:
            return None

        try:
            result = await self.input_guardrail.check(user_message)
        except Exception:
            logger.exception("input_guardrail_check_failed fail_closed=%s", self.input_guardrail_fail_closed)
            if self.input_guardrail_fail_closed:
                return self.input_guardrail_block_message
            return None

        if result.allowed:
            logger.info("input_guardrail_allowed label=%s score=%.4f", result.label, result.score)
            return None

        logger.warning("input_guardrail_blocked label=%s score=%.4f reason=%s", result.label, result.score, result.reason)
        return self.input_guardrail_block_message


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        get_llm_client(),
        get_chat_memory(),
        get_input_guardrail(),
        settings.INPUT_GUARDRAIL_FAIL_CLOSED,
        settings.INPUT_GUARDRAIL_BLOCK_MESSAGE,
    )
