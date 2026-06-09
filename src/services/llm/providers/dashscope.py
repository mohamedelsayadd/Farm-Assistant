import logging
import time
from typing import Any

from openai import AsyncOpenAI

from core.settings import Settings,get_settings
from services.llm.interface import LLMClient

settigns = get_settings()

DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3.6-27b"
logger = logging.getLogger(__name__)


class DashScopeLLMClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url = settings.DASHSCOPE_BASE_URL
        )
        logger.info("dashscope_client_initialized model=%s base_url=%s", MODEL_NAME, DASHSCOPE_BASE_URL)

    async def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Any:
        
        kwargs: dict[str, Any] = {
            "model": settigns.MODEL_NAME,
            "messages": messages,
            "extra_body": {"enable_thinking": False},
        }

        if tools is not None:
            kwargs["tools"] = tools

        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        start_time = time.perf_counter()
        logger.info(
            "llm_request_started provider=dashscope model=%s message_count=%s tools_enabled=%s tool_choice=%s",
            MODEL_NAME,
            len(messages),
            tools is not None,
            tool_choice,
        )

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "llm_request_failed provider=dashscope model=%s duration_ms=%.2f",
                MODEL_NAME,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        finish_reason = response.choices[0].finish_reason if response.choices else "unknown"
        logger.info(
            "llm_request_completed provider=dashscope model=%s finish_reason=%s duration_ms=%.2f",
            MODEL_NAME,
            finish_reason,
            duration_ms,
        )
        return response
