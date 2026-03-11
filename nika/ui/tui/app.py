"""Main Textual TUI App for Nika AI."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from nika.agent.loop import AgentEvent, AgentLoop
from nika.ui.tui.widgets.chat_view import ChatView
from nika.ui.tui.widgets.memory_panel import MemoryPanel
from nika.ui.tui.widgets.status_bar import StatusBar
from nika.ui.tui.widgets.task_panel import TaskPanel
from nika.ui.tui.widgets.tool_panel import ToolPanel


class SafetyModal(ModalScreen):
    """Modal confirmation for DANGEROUS operations."""

    def __init__(self, tool_name: str, args: dict, **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.args = args
        self._future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

    def compose(self) -> ComposeResult:
        with Container(id="safety-modal"):
            yield Static(f"[bold #ef4444]⚠ DANGEROUS OPERATION[/bold #ef4444]")
            yield Static(f"Tool: [bold]{self.tool_name}[/bold]")
            yield Static(f"Args: {self.args}")
            yield Static("\nThis operation is [bold #ef4444]DANGEROUS[/bold #ef4444]. Proceed?")
            with Horizontal():
                yield Button("✗ Cancel", id="modal-cancel", variant="error")
                yield Button("✓ Confirm", id="modal-confirm", variant="primary")

    @on(Button.Pressed, "#modal-confirm")
    def confirm(self) -> None:
        if not self._future.done():
            self._future.set_result(True)
        self.dismiss()

    @on(Button.Pressed, "#modal-cancel")
    def cancel(self) -> None:
        if not self._future.done():
            self._future.set_result(False)
        self.dismiss()

    async def wait_for_result(self) -> bool:
        return await self._future


class NikaApp(App):
    """Nika AI — main TUI application."""

    CSS_PATH = Path(__file__).parent / "themes" / "nika_dark.tcss"

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=True),
        Binding("ctrl+p", "toggle_tasks", "Tasks", show=True),
        Binding("ctrl+m", "toggle_memory", "Memory", show=True),
        Binding("ctrl+l", "show_logs", "Logs", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("escape", "clear_input", "Clear", show=False),
    ]

    def __init__(
        self,
        agent_loop: AgentLoop,
        memory_manager: Any,
        session_id: str,
        model: str,
        safety: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.agent_loop = agent_loop
        self.memory_manager = memory_manager
        self.session_id = session_id
        self.model = model
        self.safety = safety
        self._running_task: asyncio.Task | None = None
        self._llm_buffer: str = ""
        self._stream_started: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="app-body"):
            with Horizontal(id="main-row"):
                yield ChatView(id="chat-view")

                with Vertical(id="right-col"):
                    yield ToolPanel(id="tool-panel")
                    yield TaskPanel(id="task-panel")
                    yield MemoryPanel(id="memory-panel")

            with Horizontal(id="input-row"):
                yield Input(placeholder="> Ask Nika anything...", id="main-input")

            yield StatusBar(
                model=self.model,
                session_id=self.session_id,
                safety=self.safety,
                id="status-bar",
            )

        yield Footer()

    async def on_mount(self) -> None:
        await self._refresh_memories()
        self.query_one("#chat-view", ChatView).add_message(
            "system",
            f"Nika AI ready — model: {self.model} | safety: {self.safety} | session: {self.session_id[:12]}",
        )
        self.query_one("#main-input", Input).focus()

    async def _refresh_memories(self) -> None:
        if self.memory_manager:
            try:
                memories = await self.memory_manager.all_memories(limit=10)
                self.query_one("#memory-panel", MemoryPanel).set_memories(memories)
            except Exception:
                pass

    @on(Input.Submitted, "#main-input")
    async def handle_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        # Slash commands
        if text.startswith("/model "):
            new_model = text[7:].strip()
            self.agent_loop.config.model = new_model
            self.model = new_model
            self.query_one("#status-bar", StatusBar).update_model(new_model)
            self.query_one("#chat-view", ChatView).add_message(
                "system", f"Switched model to: {new_model}"
            )
            event.input.clear()
            return

        if text == "/clear":
            self.query_one("#chat-view", ChatView).clear_messages()
            event.input.clear()
            return

        # Don't start a second task if one is running
        if self._running_task and not self._running_task.done():
            self.query_one("#chat-view", ChatView).add_message(
                "system", "Still running — press Ctrl+C to interrupt first."
            )
            event.input.clear()
            return

        event.input.clear()
        self._run_agent_task(text)

    def _run_agent_task(self, task: str) -> None:
        """Fire-and-forget: start agent loop in background task."""
        chat = self.query_one("#chat-view", ChatView)
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        task_panel = self.query_one("#task-panel", TaskPanel)
        status_bar = self.query_one("#status-bar", StatusBar)

        chat.add_message("user", task)
        tool_panel.clear()
        status_bar.set_running(True)
        self._llm_buffer = ""
        self._stream_started = False

        async def run() -> None:
            try:
                async for event in self.agent_loop.run(task):
                    self._handle_agent_event(event, chat, tool_panel, task_panel, status_bar)
                    # Yield to the Textual event loop so the UI can refresh
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                chat.add_message("system", "Interrupted.")
            except Exception as e:
                chat.add_message("error", f"Agent error: {e}")
            finally:
                # Flush any unfinished stream
                if self._stream_started:
                    chat.finish_streaming(self._llm_buffer or "(no response)")
                    self._stream_started = False
                    self._llm_buffer = ""
                status_bar.set_running(False)
                self.call_later(self._refresh_memories)

        self._running_task = asyncio.create_task(run())

    def _handle_agent_event(
        self,
        event: AgentEvent,
        chat: ChatView,
        tool_panel: ToolPanel,
        task_panel: TaskPanel,
        status_bar: StatusBar,
    ) -> None:
        if event.type == "llm_chunk":
            self._llm_buffer += event.content
            if not self._stream_started:
                self._stream_started = True
                chat.start_streaming()
            # Update the streaming widget every ~50 chars to avoid hammering the UI
            if len(self._llm_buffer) % 50 < len(event.content):
                chat.update_stream(self._llm_buffer)

        elif event.type == "thinking":
            if event.content:
                # Flush any partial stream first
                if self._stream_started:
                    chat.finish_streaming(self._llm_buffer)
                    self._stream_started = False
                    self._llm_buffer = ""
                chat.add_message("nika", event.content)

        elif event.type == "plan":
            task_panel.set_plan(event.plan_steps)
            steps_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(event.plan_steps))
            chat.add_message("plan", f"Planning {len(event.plan_steps)} steps:\n{steps_str}")

        elif event.type == "tool_start":
            # Flush stream before tool output
            if self._stream_started:
                chat.finish_streaming(self._llm_buffer)
                self._stream_started = False
                self._llm_buffer = ""
            tool_panel.add_tool(event.tool_name, event.risk)
            chat.add_message("tool", f"Running {event.tool_name}...")

        elif event.type == "tool_end":
            success = not event.tool_result.startswith(("[Error]", "[Blocked]"))
            tool_panel.complete_tool(event.tool_name, success)
            result = event.tool_result[:300] + ("..." if len(event.tool_result) > 300 else "")
            chat.add_message("tool", f"{event.tool_name} → {result}")

        elif event.type == "final":
            if self._stream_started:
                chat.finish_streaming(event.content)
                self._stream_started = False
                self._llm_buffer = ""
            else:
                chat.add_message("nika", event.content)

        elif event.type == "error":
            if self._stream_started:
                chat.finish_streaming(self._llm_buffer or "")
                self._stream_started = False
                self._llm_buffer = ""
            chat.add_message("error", event.content)

        elif event.type == "safety" and event.risk == "DANGEROUS":
            chat.add_message("error", f"⚠ DANGEROUS: {event.tool_name} — requires confirmation")

    def action_interrupt(self) -> None:
        self.agent_loop.interrupt()
        if self._running_task:
            self._running_task.cancel()
        self.query_one("#status-bar", StatusBar).set_running(False)

    def action_toggle_tasks(self) -> None:
        panel = self.query_one("#task-panel", TaskPanel)
        panel.display = not panel.display

    def action_toggle_memory(self) -> None:
        panel = self.query_one("#memory-panel", MemoryPanel)
        panel.display = not panel.display

    def action_show_logs(self) -> None:
        self.query_one("#chat-view", ChatView).add_message(
            "system", "Audit log: data/logs/audit.jsonl"
        )

    def action_clear_input(self) -> None:
        self.query_one("#main-input", Input).clear()

    async def confirm_dangerous(self, tool_name: str, risk: str, args: dict) -> bool:
        modal = SafetyModal(tool_name=tool_name, args=args)
        await self.push_screen_wait(modal)
        return await modal.wait_for_result()
