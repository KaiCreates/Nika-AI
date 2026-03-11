"""Episodic memory — per-session summaries in SQLite."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


class EpisodicMemory:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    summary TEXT,
                    tasks_completed TEXT DEFAULT '[]',
                    key_outputs TEXT DEFAULT '[]',
                    messages TEXT DEFAULT '[]'
                )
            """)
            # Migration: Ensure messages column exists
            try:
                await db.execute("ALTER TABLE episodes ADD COLUMN messages TEXT DEFAULT '[]'")
            except Exception:
                pass # Already exists
            await db.commit()

    async def save(
        self,
        session_id: str,
        summary: str,
        tasks_completed: list[str] | None = None,
        key_outputs: list[str] | None = None,
        messages: list[dict] | None = None,
    ) -> str:
        ep_id = str(uuid.uuid4())[:12]
        now = datetime.now(tz=timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO episodes (id, session_id, started_at, ended_at, summary, tasks_completed, key_outputs, messages) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ep_id, session_id, now, now,
                    summary,
                    json.dumps(tasks_completed or []),
                    json.dumps(key_outputs or []),
                    json.dumps(messages or []),
                ),
            )
            await db.commit()
        return ep_id

    async def recent(self, n: int = 3) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM episodes ORDER BY ended_at DESC LIMIT ?", (n,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_by_session(self, session_id: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM episodes WHERE session_id = ? ORDER BY started_at", (session_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
