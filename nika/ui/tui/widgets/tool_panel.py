"""ToolPanel — live tool execution status."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


RISK_ICONS = {"SAFE": "✓", "CAUTION": "⚠", "DANGEROUS": "✗"}
RISK_COLORS = {"SAFE": "#22c55e", "CAUTION": "#f59e0b", "DANGEROUS": "#ef4444"}
STATUS_ICONS = {"running": "⟳", "done": "✓", "failed": "✗", "pending": "○"}


class ToolPanel(Static):
    BORDER_TITLE = "Tools"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entries: list[dict] = []

    def _refresh(self) -> None:
        lines = []
        for e in self._entries[-20:]:
            status = e.get("status", "pending")
            risk = e.get("risk", "SAFE")
            icon = STATUS_ICONS.get(status, "○")
            color = RISK_COLORS.get(risk, "#fafafa") if status != "done" else "#22c55e"
            if status == "failed":
                color = "#ef4444"
            elif status == "running":
                color = "#3b82f6"
            lines.append(f"[{color}]{icon}[/{color}] {e['name']}")
        self.update("\n".join(lines))

    def add_tool(self, name: str, risk: str = "SAFE") -> None:
        self._entries.append({"name": name, "status": "running", "risk": risk})
        self._refresh()

    def complete_tool(self, name: str, success: bool = True) -> None:
        for e in reversed(self._entries):
            if e["name"] == name:
                e["status"] = "done" if success else "failed"
                break
        self._refresh()

    def clear(self) -> None:
        self._entries.clear()
        self._refresh()
