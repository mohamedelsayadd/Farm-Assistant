import logging
from functools import lru_cache

from core.settings import get_settings
from services.chat_prompts import SYSTEM_PROMPT
from services.memory.interface import ChatMemory
from services.memory.providers.redis import RedisChatMemory


logger = logging.getLogger(__name__)


@lru_cache
def get_chat_memory() -> ChatMemory:
    settings = get_settings()
    logger.info("chat_memory_created provider=redis")
    return RedisChatMemory(
        redis_url=settings.REDIS_URL,
        system_prompt=SYSTEM_PROMPT,
        ttl_seconds=settings.CHAT_MEMORY_TTL_SECONDS,
        max_history_messages=settings.CHAT_MEMORY_MAX_HISTORY_MESSAGES,
    )
