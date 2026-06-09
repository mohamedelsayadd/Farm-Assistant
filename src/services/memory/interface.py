from abc import ABC, abstractmethod
from typing import Any


class ChatMemory(ABC):
    @abstractmethod
    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return stored conversation messages for an isolated conversation."""

    @abstractmethod
    async def save_exchange(self, conversation_id: str, user_message: str, assistant_response: str) -> None:
        """Store the latest user/assistant exchange for an isolated conversation."""
