"""Priority task queue backed by SQLite."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


class TaskQueue:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    description TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 5,
                    parent_task_id TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            await db.commit()

    async def add(
        self,
        description: str,
        session_id: str = "",
        priority: int = 5,
        parent_task_id: str | None = None,
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now(tz=timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO tasks (id, session_id, description, priority, parent_task_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, session_id, description, priority, parent_task_id, now, now),
            )
            await db.commit()
        return task_id

    async def update_status(self, task_id: str, status: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            await db.commit()

    async def pending(self, session_id: str = "") -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if session_id:
                cursor = await db.execute(
                    "SELECT * FROM tasks WHERE session_id = ? AND status = 'pending' ORDER BY priority, created_at",
                    (session_id,),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority, created_at"
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def all_for_session(self, session_id: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
