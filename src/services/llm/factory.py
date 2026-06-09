import logging

from core.settings import get_settings
from services.llm.interface import LLMClient
from services.llm.providers.dashscope import DashScopeLLMClient


logger = logging.getLogger(__name__)


def get_llm_client() -> LLMClient:
    logger.info("llm_client_created provider=dashscope")
    return DashScopeLLMClient(get_settings())
