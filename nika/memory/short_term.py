"""Short-term memory — in-session rolling message window with compression."""
from __future__ import annotations

from typing import Any


class ShortTermMemory:
    def __init__(self, limit: int = 20) -> None:
        self.limit = limit
        self._messages: list[dict[str, str]] = []
        self._summaries: list[str] = []

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict[str, str]]:
        return list(self._messages)

    def compress(self, summary: str) -> None:
        """Replace oldest half of messages with a summary."""
        mid = len(self._messages) // 2
        self._summaries.append(summary)
        self._messages = self._messages[mid:]

    def needs_compression(self) -> bool:
        return len(self._messages) >= self.limit

    def clear(self) -> None:
        self._messages.clear()
        self._summaries.clear()

    def summaries(self) -> list[str]:
        return list(self._summaries)
