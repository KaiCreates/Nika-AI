"""ChatView widget — streaming message history using VerticalScroll."""
from __future__ import annotations

from rich.markup import escape
from textual.containers import VerticalScroll
from textual.widgets import Static

ROLE_MAP: dict[str, tuple[str, str]] = {
    "user":   ("you",  "#3b82f6"),
    "nika":   ("nika", "#a78bfa"),
    "tool":   ("tool", "#f59e0b"),
    "error":  ("err",  "#ef4444"),
    "plan":   ("plan", "#22c55e"),
    "system": ("sys",  "#71717a"),
}


class ChatView(VerticalScroll):
    """Scrollable chat history with live streaming support."""

    BORDER_TITLE = "Chat"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._streaming_widget: Static | None = None

    def _make_line(self, role: str, content: str) -> str:
        label, color = ROLE_MAP.get(role, ("?", "#fafafa"))
        return f"[bold {color}][{label}][/bold {color}] {escape(content)}"

    def add_message(self, role: str, content: str) -> None:
        """Add a complete message; cancels any in-progress stream widget."""
        self._streaming_widget = None
        widget = Static(self._make_line(role, content))
        self.mount(widget)
        self.call_after_refresh(self.scroll_end, animate=False)

    # ── Streaming support ────────────────────────────────────────────────────

    def start_streaming(self) -> None:
        """Mount a placeholder that will be filled with streamed tokens."""
        widget = Static(self._make_line("nika", "⟳ generating..."))
        self.mount(widget)
        self._streaming_widget = widget
        self.call_after_refresh(self.scroll_end, animate=False)

    def update_stream(self, full_text: str) -> None:
        """Replace the streaming placeholder text in-place."""
        if self._streaming_widget is not None:
            self._streaming_widget.update(self._make_line("nika", full_text or "⟳"))
            self.call_after_refresh(self.scroll_end, animate=False)

    def finish_streaming(self, final_text: str) -> None:
        """Commit the final text into the streaming widget."""
        if self._streaming_widget is not None:
            self._streaming_widget.update(self._make_line("nika", final_text))
            self._streaming_widget = None
        else:
            self.add_message("nika", final_text)
        self.call_after_refresh(self.scroll_end, animate=False)

    def clear_messages(self) -> None:
        self._streaming_widget = None
        self.remove_children()
