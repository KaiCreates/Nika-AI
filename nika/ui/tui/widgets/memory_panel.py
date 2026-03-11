"""MemoryPanel — sidebar showing active memories."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


class MemoryPanel(Static):
    BORDER_TITLE = "Memory"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._memories: list[dict] = []

    def _refresh(self) -> None:
        lines = []
        for m in self._memories[:10]:
            content = m.get("content", "")
            cat = m.get("category", "fact")
            cat_color = {
                "preference": "#a78bfa",
                "fact": "#3b82f6",
                "rule": "#f59e0b",
            }.get(cat, "#71717a")
            lines.append(f"[{cat_color}]◆[/{cat_color}] {content[:40]}")
        if not lines:
            lines = ["[#71717a](no memories loaded)[/#71717a]"]
        self.update("\n".join(lines))

    def set_memories(self, memories: list[dict]) -> None:
        self._memories = memories
        self._refresh()

    def add_memory(self, memory: dict) -> None:
        self._memories.insert(0, memory)
        self._refresh()
