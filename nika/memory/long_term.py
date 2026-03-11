"""Long-term memory — SQLite facts/preferences store."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


class LongTermMemory:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'fact',
                    tags TEXT DEFAULT '[]',
                    embedding_id TEXT,
                    created_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0
                )
            """)
            await db.commit()

    async def save(
        self,
        content: str,
        category: str = "fact",
        tags: list[str] | None = None,
        embedding_id: str | None = None,
    ) -> str:
        mem_id = str(uuid.uuid4())[:12]
        now = datetime.now(tz=timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memories (id, content, category, tags, embedding_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (mem_id, content, category, json.dumps(tags or []), embedding_id, now),
            )
            await db.commit()
        return mem_id

    async def keyword_search(self, query: str, top_k: int = 5, category: str | None = None) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if category:
                cursor = await db.execute(
                    "SELECT * FROM memories WHERE category = ? AND content LIKE ? ORDER BY access_count DESC, created_at DESC LIMIT ?",
                    (category, f"%{query}%", top_k),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM memories WHERE content LIKE ? ORDER BY access_count DESC, created_at DESC LIMIT ?",
                    (f"%{query}%", top_k),
                )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def all(self, limit: int = 100) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete(self, content: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM memories WHERE content = ?", (content,))
            await db.commit()
            return cursor.rowcount > 0

    async def bump_access(self, mem_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE memories SET access_count = access_count + 1 WHERE id = ?", (mem_id,)
            )
            await db.commit()
