from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    label: str
    score: float
    reason: str | None = None


class InputGuardrail(ABC):
    @abstractmethod
    async def check(self, message: str) -> GuardrailResult:
        """Classify a single latest user message before it reaches the main LLM."""
