"""asyncio pub/sub event bus for agent events."""
from __future__ import annotations

import asyncio
from enum import auto, StrEnum
from typing import Any, Callable


class EventType(StrEnum):
    LLM_STARTED = "llm_started"
    LLM_CHUNK = "llm_chunk"
    LLM_DONE = "llm_done"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    PLAN_CREATED = "plan_created"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    MEMORY_SAVED = "memory_saved"
    ERROR = "error"


Handler = Callable[[EventType, dict[str, Any]], "asyncio.coroutines"]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        key = str(event_type)
        self._handlers.setdefault(key, []).append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        key = str(event_type)
        if key in self._handlers:
            self._handlers[key] = [h for h in self._handlers[key] if h is not handler]

    async def publish(self, event_type: EventType, data: dict[str, Any] | None = None) -> None:
        key = str(event_type)
        data = data or {}
        for handler in self._handlers.get(key, []):
            try:
                result = handler(event_type, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Don't let handler errors crash the bus
