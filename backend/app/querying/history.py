# ============================================================
# history.py
# ============================================================
from abc import ABC, abstractmethod
from langchain_core.messages import BaseMessage


class ConversationHistory(ABC):
    @abstractmethod
    def get(self, session_id: str) -> list[BaseMessage]:
        pass

    @abstractmethod
    def append(self, session_id: str, messages: list[BaseMessage]) -> None:
        pass


class InMemoryConversationHistory(ConversationHistory):
    """Simple in-process store. Swap for a Redis/DB-backed impl later without
    touching any caller — only this class needs to change."""

    def __init__(self):
        self._store: dict[str, list[BaseMessage]] = {}

    def get(self, session_id: str) -> list[BaseMessage]:
        return self._store.get(session_id, [])

    def append(self, session_id: str, messages: list[BaseMessage]) -> None:
        self._store.setdefault(session_id, []).extend(messages)