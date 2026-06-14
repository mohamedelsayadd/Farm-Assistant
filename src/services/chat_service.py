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

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_TOOL_CALL_ROUNDS = settings.MAX_TOOL_CALL_ROUNDS
DEFAULT_INPUT_GUARDRAIL_BLOCK_MESSAGE = settings.INPUT_GUARDRAIL_BLOCK_MESSAGE


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_devices_last_reads",
            "description": "Return the last reads of each sensor in each device, with its Africa/Cairo timestamp and configured lower/upper limits.",
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
                        "enum": ["day", "month"],
                        "description": """Use `month` for any request spanning more than 24 hours, including last week, last month, and multi-day historical trends. It returns one reading per day.
                                          Use `day` when hourly resolution is needed, including the last few hours, today, yesterday, or a specific hour/date (e.g. "the temperature at 5 AM the day before yesterday"). It returns one reading per hour."""
                    },
                },
                "required": ["device_id", "start_time", "end_time", "data_type"],
                "additionalProperties": False,
            },
        },
    },
]


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
        answer, total_tool_calls = await self._generate_answer(JWT, messages, user_message)
        await self._save_exchange(conversation_id, user_message, answer)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "chat_completed tool_calls=%s answer_length=%s duration_ms=%.2f",
            total_tool_calls,
            len(answer),
            duration_ms,
        )
        return answer

    async def _generate_answer(
        self,
        JWT: str,
        messages: list[dict[str, Any]],
        user_message: str,
    ) -> tuple[str, int]:
        total_tool_calls = 0
        answer = "لا أستطيع تقديم إجابة في الوقت الحالي."

        for tool_round in range(MAX_TOOL_CALL_ROUNDS):
            response = await self._create_chat_completion(messages, "auto", len(user_message), tool_round)
            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []

            if not tool_calls:
                return assistant_message.content or answer, total_tool_calls

            total_tool_calls += len(tool_calls)
            logger.info("chat_tool_calls_requested count=%s round=%s", len(tool_calls), tool_round + 1)
            logger.info(
                "chat_model_tool_calls round=%s tool_calls=%s",
                tool_round + 1,
                json.dumps(self._serialize_tool_calls(tool_calls), ensure_ascii=False),
            )
            messages.append(assistant_message.model_dump(exclude_none=True))

            for tool_call in tool_calls:
                messages.append(await self._build_tool_message(JWT, tool_call))

        final_response = await self._create_final_chat_completion(messages, total_tool_calls)
        return final_response.choices[0].message.content or answer, total_tool_calls

    async def _create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tool_choice: str,
        message_length: int,
        tool_round: int,
    ) -> Any:
        try:
            return await self.llm_client.create_chat_completion(
                messages=messages,
                tools=TOOLS,
                tool_choice=tool_choice,
            )
        except Exception:
            logger.exception(
                "chat_llm_call_failed message_length=%s tool_round=%s",
                message_length,
                tool_round,
            )
            raise

    async def _create_final_chat_completion(self, messages: list[dict[str, Any]], total_tool_calls: int) -> Any:
        try:
            return await self.llm_client.create_chat_completion(
                messages=messages,
                tools=TOOLS,
                tool_choice="none",
            )
        except Exception:
            logger.exception("chat_final_llm_call_failed tool_call_count=%s", total_tool_calls)
            raise

    async def _build_tool_message(self, JWT: str, tool_call: Any) -> dict[str, Any]:
        logger.info("chat_tool_call_started tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
        tool_result = await self._execute_tool_call(JWT, tool_call)
        tool_result_content = json.dumps(tool_result, ensure_ascii=False)
        logger.info(
            "chat_tool_call_result_for_llm tool_call_id=%s tool_name=%s result=%s",
            tool_call.id,
            tool_call.function.name,
            tool_result_content,
        )
        logger.info("chat_tool_call_completed tool_call_id=%s tool_name=%s", tool_call.id, tool_call.function.name)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result_content,
        }

    async def _execute_tool_call(self, JWT: str, tool_call: Any) -> Any:
        tool_arguments = self._parse_tool_arguments(tool_call)
        logger.info(
            "chat_tool_call_arguments tool_call_id=%s tool_name=%s arguments=%s",
            tool_call.id,
            tool_call.function.name,
            json.dumps(tool_arguments, ensure_ascii=False) if isinstance(tool_arguments, dict) else tool_arguments,
        )

        if not isinstance(tool_arguments, dict):
            return {"error": tool_arguments}

        return await execute_tool(
            JWT=JWT,
            name=tool_call.function.name,
            arguments=tool_arguments,
        )

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

    def _serialize_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "tool_call_id": getattr(tool_call, "id", None),
                "tool_name": getattr(tool_call.function, "name", None),
                "arguments": getattr(tool_call.function, "arguments", None) or "{}",
            }
            for tool_call in tool_calls
        ]

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
