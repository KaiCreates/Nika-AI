"""StatusBar — model, session, safety mode, token count."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


SAFETY_COLORS = {
    "SAFE": "#22c55e",
    "NORMAL": "#f59e0b",
    "STRICT": "#ef4444",
    "YOLO": "#ef4444",
}


class StatusBar(Static):
    def __init__(self, model: str = "llama3.1:8b", session_id: str = "", safety: str = "NORMAL", **kwargs):
        super().__init__(**kwargs)
        self._model = model
        self._session_id = session_id[:12]
        self._safety = safety
        self._tokens = 0
        self._running = False

    def _update_status(self) -> None:
        safety_color = SAFETY_COLORS.get(self._safety, "#f59e0b")
        running_indicator = " [#3b82f6]●[/#3b82f6]" if self._running else " [#71717a]○[/#71717a]"
        status = (
            f"[#3b82f6]{self._model}[/#3b82f6]"
            f"  [#71717a]session:[/#71717a][#a1a1aa]{self._session_id}[/#a1a1aa]"
            f"  [{safety_color}]{self._safety}[/{safety_color}]"
            f"  [#71717a]tokens:[/#71717a][#a1a1aa]{self._tokens}[/#a1a1aa]"
            f"{running_indicator}"
        )
        self.update(status)

    def update_model(self, model: str) -> None:
        self._model = model
        self._update_status()

    def update_safety(self, safety: str) -> None:
        self._safety = safety
        self._update_status()

    def update_tokens(self, tokens: int) -> None:
        self._tokens = tokens
        self._update_status()

    def set_running(self, running: bool) -> None:
        self._running = running
        self._update_status()

    def on_mount(self) -> None:
        self._update_status()
