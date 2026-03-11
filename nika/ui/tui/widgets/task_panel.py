"""TaskPanel — task queue and plan steps."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


STATUS_ICONS = {
    "pending": "☐",
    "active": "▶",
    "done": "☑",
    "failed": "✗",
}
STATUS_COLORS = {
    "pending": "#71717a",
    "active": "#3b82f6",
    "done": "#22c55e",
    "failed": "#ef4444",
}


class TaskPanel(Static):
    BORDER_TITLE = "Tasks"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._steps: list[dict] = []

    def _refresh(self) -> None:
        lines = []
        for i, s in enumerate(self._steps, 1):
            status = s.get("status", "pending")
            icon = STATUS_ICONS.get(status, "?")
            color = STATUS_COLORS.get(status, "#fafafa")
            desc = s.get("description", "")[:35]
            lines.append(f"[{color}]{icon}[/{color}] {i}. {desc}")
        if not lines:
            lines = ["[#71717a](no tasks)[/#71717a]"]
        self.update("\n".join(lines))

    def set_plan(self, steps: list[str]) -> None:
        self._steps = [{"description": s, "status": "pending"} for s in steps]
        self._refresh()

    def set_step_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._steps):
            self._steps[index]["status"] = status
            self._refresh()

    def clear(self) -> None:
        self._steps.clear()
        self._refresh()
