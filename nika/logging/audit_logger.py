"""Append-only JSONL audit log of every agent event."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_path: Path, session_id: str) -> None:
        self.log_path = log_path
        self.session_id = session_id
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def log(self, event_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "payload": payload,
        }
        async with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    async def read_recent(self, n: int = 100) -> list[dict]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text().strip().splitlines()
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return entries
