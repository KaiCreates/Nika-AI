"""Session manager — create, resume, and close sessions."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionManager:
    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_id: str | None = None
        self._transcript: list[dict] = []

    def new_session(self) -> str:
        session_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:6]
        self.current_session_id = session_id
        self._transcript = []
        return session_id

    def log_event(self, event_type: str, payload: Any) -> None:
        if self.current_session_id is None:
            return
        self._transcript.append({
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        })

    def save_session(self) -> Path | None:
        if not self.current_session_id:
            return None
        path = self.sessions_dir / f"{self.current_session_id}.json"
        path.write_text(json.dumps(self._transcript, indent=2))
        return path

    def load_session(self, session_id: str) -> list[dict]:
        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def list_sessions(self) -> list[str]:
        return sorted(
            [p.stem for p in self.sessions_dir.glob("*.json")],
            reverse=True,
        )
