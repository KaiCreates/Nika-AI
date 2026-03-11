"""Semantic memory — ChromaDB vector store with Ollama embeddings."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


class SemanticMemory:
    def __init__(self, chroma_path: Path, embed_fn: Any) -> None:
        self.chroma_path = chroma_path
        self.embed_fn = embed_fn  # async fn(text: str) -> list[float]
        self._client = None
        self._memories_col = None
        self._episodes_col = None
        self._knowledge_col = None

    async def initialize(self) -> None:
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.chroma_path))
            self._memories_col = self._client.get_or_create_collection("memories")
            self._episodes_col = self._client.get_or_create_collection("episodes")
            self._knowledge_col = self._client.get_or_create_collection("knowledge_base")
            logger.info("ChromaDB initialized")
        except Exception as e:
            logger.warning(f"ChromaDB unavailable: {e}. Semantic search disabled.")

    async def add_memory(self, mem_id: str, content: str, metadata: dict | None = None) -> None:
        if self._memories_col is None:
            return
        try:
            embedding = await self.embed_fn(content)
            self._memories_col.add(
                ids=[mem_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata or {}],
            )
        except Exception as e:
            logger.debug(f"Failed to add memory embedding: {e}")

    async def delete_memory_by_content(self, content: str) -> None:
        if self._memories_col is None:
            return
        try:
            # Chroma doesn't support 'where' on document text easily.
            # We must find the ID first.
            results = self._memories_col.get(where_document={"$contains": content})
            if results and results["ids"]:
                self._memories_col.delete(ids=results["ids"])
        except Exception as e:
            logger.debug(f"Failed to delete semantic memory: {e}")

    async def search_memories(self, query: str, top_k: int = 5) -> list[dict]:
        if self._memories_col is None:
            return []
        try:
            embedding = await self.embed_fn(query)
            results = self._memories_col.query(
                query_embeddings=[embedding],
                n_results=min(top_k, self._memories_col.count()),
                include=["documents", "metadatas", "distances"],
            )
            out = []
            for doc, meta in zip(
                results["documents"][0], results["metadatas"][0]
            ):
                out.append({"content": doc, **meta})
            return out
        except Exception as e:
            logger.debug(f"Semantic search failed: {e}")
            return []

    async def add_episode(self, ep_id: str, summary: str, metadata: dict | None = None) -> None:
        if self._episodes_col is None:
            return
        try:
            embedding = await self.embed_fn(summary)
            self._episodes_col.add(
                ids=[ep_id],
                embeddings=[embedding],
                documents=[summary],
                metadatas=[metadata or {}],
            )
        except Exception as e:
            logger.debug(f"Failed to add episode embedding: {e}")

    async def ingest_document(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        if self._knowledge_col is None:
            return
        try:
            # Chunk into 500-char segments
            chunks = [text[i:i+500] for i in range(0, len(text), 400)]
            for i, chunk in enumerate(chunks):
                embedding = await self.embed_fn(chunk)
                self._knowledge_col.add(
                    ids=[f"{doc_id}_{i}"],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{**(metadata or {}), "chunk": i}],
                )
        except Exception as e:
            logger.debug(f"Document ingest failed: {e}")

    async def search_knowledge(self, query: str, top_k: int = 5) -> list[str]:
        if self._knowledge_col is None:
            return []
        try:
            count = self._knowledge_col.count()
            if count == 0:
                return []
            embedding = await self.embed_fn(query)
            results = self._knowledge_col.query(
                query_embeddings=[embedding],
                n_results=min(top_k, count),
                include=["documents"],
            )
            return results["documents"][0]
        except Exception as e:
            logger.debug(f"Knowledge search failed: {e}")
            return []
