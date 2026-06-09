import json
import logging
from typing import Any

from redis.asyncio import Redis

from services.memory.interface import ChatMemory


logger = logging.getLogger(__name__)


class RedisChatMemory(ChatMemory):
    def __init__(
        self,
        redis_url: str,
        system_prompt: str,
        ttl_seconds: int,
        max_history_messages: int,
    ) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)
        self.system_message = {"role": "system", "content": system_prompt}
        self.ttl_seconds = ttl_seconds
        self.max_history_messages = max_history_messages
        logger.info(
            "redis_chat_memory_initialized ttl_seconds=%s max_messages=%s",
            ttl_seconds,
            max_history_messages + 1,
        )

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        key = self._key(conversation_id)
        try:
            stored_messages = await self.client.get(key)
        except Exception:
            logger.exception("chat_memory_read_failed conversation_id=%s", conversation_id)
            return [self.system_message]

        if stored_messages is None:
            return [self.system_message]

        try:
            messages = json.loads(stored_messages)
        except json.JSONDecodeError:
            logger.exception("chat_memory_decode_failed conversation_id=%s", conversation_id)
            return [self.system_message]

        if not isinstance(messages, list):
            logger.warning("chat_memory_invalid_payload conversation_id=%s", conversation_id)
            return [self.system_message]

        return self._normalize_messages(messages)

    async def save_exchange(self, conversation_id: str, user_message: str, assistant_response: str) -> None:
        key = self._key(conversation_id)
        messages = await self.get_messages(conversation_id)
        history = self._history_messages(messages)
        history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_response},
            ]
        )
        trimmed_messages = [self.system_message, *history[-self.max_history_messages :]]

        try:
            await self.client.set(
                key,
                json.dumps(trimmed_messages, ensure_ascii=False),
                ex=self.ttl_seconds,
            )
        except Exception:
            logger.exception("chat_memory_write_failed conversation_id=%s", conversation_id)

    def _normalize_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        history = self._history_messages(messages)
        return [self.system_message, *history[-self.max_history_messages :]]

    def _history_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                history.append({"role": role, "content": content})
        return history

    def _key(self, conversation_id: str) -> str:
        return f"chat_memory:{conversation_id}"
