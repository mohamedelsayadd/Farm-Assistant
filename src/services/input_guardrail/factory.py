import logging
from functools import lru_cache

from core.settings import get_settings
from services.input_guardrail.interface import GuardrailResult, InputGuardrail


logger = logging.getLogger(__name__)


class _UnavailableInputGuardrail(InputGuardrail):
    async def check(self, message: str) -> GuardrailResult:
        raise RuntimeError("input guardrail provider is unavailable")


@lru_cache
def get_input_guardrail() -> InputGuardrail | None:
    settings = get_settings()
    if not settings.INPUT_GUARDRAIL_ENABLED:
        logger.info("input_guardrail_disabled")
        return None

    if settings.INPUT_GUARDRAIL_PROVIDER.lower() == "huggingface":
        from services.input_guardrail.providers.huggingface import HuggingFaceInputGuardrail

        logger.info(
            "input_guardrail_created provider=huggingface model=%s",
            settings.INPUT_GUARDRAIL_MODEL_NAME,
        )
        try:
            return HuggingFaceInputGuardrail(
                model_name=settings.INPUT_GUARDRAIL_MODEL_NAME,
                max_tokens=settings.INPUT_GUARDRAIL_MAX_TOKENS,
                block_threshold=settings.INPUT_GUARDRAIL_BLOCK_THRESHOLD,
            )
        except Exception:
            logger.exception("input_guardrail_creation_failed provider=huggingface")
            if settings.INPUT_GUARDRAIL_FAIL_CLOSED:
                return _UnavailableInputGuardrail()
            return None

    raise ValueError(f"Unsupported input guardrail provider: {settings.INPUT_GUARDRAIL_PROVIDER}")
