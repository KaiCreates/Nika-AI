"""Unified facade over all three memory tiers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from nika.memory.long_term import LongTermMemory
from nika.memory.episodic import EpisodicMemory
from nika.memory.semantic import SemanticMemory
from nika.memory.short_term import ShortTermMemory


class MemoryManager:
    def __init__(
        self,
        db_path: Path,
        chroma_path: Path,
        embed_fn: Any,
        short_term_limit: int = 20,
        session_id: str = "default",
    ) -> None:
        self.session_id = session_id
        self.short_term = ShortTermMemory(limit=short_term_limit)
        self.long_term = LongTermMemory(db_path)
        self.episodic = EpisodicMemory(db_path)
        self.semantic = SemanticMemory(chroma_path, embed_fn)

    async def initialize(self) -> None:
        await self.long_term.initialize()
        await self.episodic.initialize()
        await self.semantic.initialize()
        logger.info("Memory manager initialized")

    async def save_memory(
        self,
        content: str,
        category: str = "fact",
        tags: list[str] | None = None,
    ) -> str:
        # Deduplication: if identical or near-identical content exists, return existing ID
        content_norm = content.strip().lower()
        existing = await self.long_term.keyword_search(content[:40], top_k=5)
        for e in existing:
            if e.get("content", "").strip().lower() == content_norm:
                return e["id"]   # already stored — skip duplicate

        mem_id = await self.long_term.save(content, category, tags)
        await self.semantic.add_memory(
            mem_id, content, metadata={"category": category, "tags": ",".join(tags or [])}
        )
        return mem_id

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[dict]:
        # Try semantic search first
        semantic_results = await self.semantic.search_memories(query, top_k)
        if semantic_results:
            # Tag with category from long-term if available
            return semantic_results[:top_k]
        # Fallback to keyword search
        return await self.long_term.keyword_search(query, top_k, category)

    async def all_memories(self, limit: int = 50) -> list[dict]:
        return await self.long_term.all(limit)

    async def delete_memory(self, content: str) -> bool:
        # Delete from long-term (keyword) and semantic
        await self.semantic.delete_memory_by_content(content)
        return await self.long_term.delete(content)

    async def save_episode(
        self,
        summary: str,
        tasks_completed: list[str] | None = None,
        key_outputs: list[str] | None = None,
        messages: list[dict] | None = None,
    ) -> str:
        ep_id = await self.episodic.save(
            session_id=self.session_id,
            summary=summary,
            tasks_completed=tasks_completed,
            key_outputs=key_outputs,
            messages=messages,
        )
        await self.semantic.add_episode(ep_id, summary, metadata={"session_id": self.session_id})
        return ep_id

    async def recent_episodes(self, n: int = 3) -> list[dict]:
        return await self.episodic.recent(n)

    async def ingest_document(
        self, doc_id: str, text: str, metadata: dict | None = None
    ) -> None:
        await self.semantic.ingest_document(doc_id, text, metadata)

    async def search_knowledge(self, query: str, top_k: int = 5) -> list[str]:
        return await self.semantic.search_knowledge(query, top_k)
