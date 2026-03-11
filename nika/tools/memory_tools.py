"""Memory tools — SaveMemory, RecallMemory, SummarizeSession."""
from __future__ import annotations

from typing import Any

from nika.tools.base import BaseTool

# Memory manager is injected after init to avoid circular imports
_memory_manager = None


def set_memory_manager(mm: Any) -> None:
    global _memory_manager
    _memory_manager = mm


class SaveMemoryTool(BaseTool):
    name = "save_memory"
    description = "Persist a fact, preference, or rule to long-term memory."
    parameters = {
        "content": {"type": "string", "description": "The fact or preference to remember."},
        "category": {"type": "string", "description": "Category (e.g. 'preference', 'fact', 'rule')."},
        "tags": {"type": "array", "description": "Optional tags for retrieval."},
    }
    required = ["content"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        content: str,
        category: str = "fact",
        tags: list[str] | None = None,
    ) -> str:
        if _memory_manager is None:
            return "[Error] Memory manager not initialized."
        try:
            mem_id = await _memory_manager.save_memory(
                content=content,
                category=category,
                tags=tags or [],
            )
            return f"Memory saved (id={mem_id}): {content[:80]}"
        except Exception as e:
            return f"[Error] Could not save memory: {e}"


class RecallMemoryTool(BaseTool):
    name = "recall_memory"
    description = "Query long-term memory by keyword or semantic search."
    parameters = {
        "query": {"type": "string", "description": "Search query or keyword."},
        "top_k": {"type": "integer", "description": "Max results to return (default 5)."},
        "category": {"type": "string", "description": "Filter by category."},
    }
    required = ["query"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self, query: str, top_k: int = 5, category: str = ""
    ) -> str:
        if _memory_manager is None:
            return "[Error] Memory manager not initialized."
        try:
            results = await _memory_manager.recall(
                query=query, top_k=top_k, category=category or None
            )
            if not results:
                return "No memories found matching that query."
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r.get('category', 'fact')}] {r['content']}")
            return "\n".join(lines)
        except Exception as e:
            return f"[Error] Memory recall failed: {e}"


class SummarizeSessionTool(BaseTool):
    name = "summarize_session"
    description = (
        "Summarize the current session and save it to episodic memory. "
        "This now automatically saves the full conversation history to permanent SQLite storage."
    )
    parameters = {
        "summary": {"type": "string", "description": "Summary text to save."},
        "tasks_completed": {"type": "array", "description": "List of completed task descriptions."},
        "key_outputs": {"type": "array", "description": "List of key files or results produced."},
    }
    required = ["summary"]
    safety_level = "SAFE"

    # Global reference to the current loop, injected at runtime
    current_loop: Any = None

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        summary: str,
        tasks_completed: list[str] | None = None,
        key_outputs: list[str] | None = None,
    ) -> str:
        if _memory_manager is None:
            return "[Error] Memory manager not initialized."
        
        # Get messages from the active loop if available
        messages = []
        if SummarizeSessionTool.current_loop:
            messages = SummarizeSessionTool.current_loop.messages

        try:
            ep_id = await _memory_manager.save_episode(
                summary=summary,
                tasks_completed=tasks_completed or [],
                key_outputs=key_outputs or [],
                messages=messages,
            )
            return f"Session summary and full chat history saved (episode id={ep_id})."
        except Exception as e:
            return f"[Error] Could not save episode: {e}"


class RecallChatHistoryTool(BaseTool):
    name = "recall_chat_history"
    description = (
        "Search through the transcript of the entire current conversation and past sessions. "
        "Use this if you need to remember exactly what the user said earlier or past tool outputs."
    )
    parameters = {
        "query": {"type": "string", "description": "Text or keywords to search for in past chat messages and events."},
        "limit": {"type": "integer", "description": "Number of past events to retrieve. Default 10."},
    }
    required = ["query"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, query: str, limit: int = 10) -> str:
        if _memory_manager is None:
            return "[Error] Memory manager not initialized."
        try:
            import json
            import glob
            from pathlib import Path
            
            # Find the sessions directory based on db_path parent (data/memory -> data/sessions)
            sessions_dir = Path(_memory_manager.db_path).parent.parent / "sessions"
            if not sessions_dir.exists():
                return "[Error] Sessions directory not found."
                
            matches = []
            q_lower = query.lower()
            
            # Scan all session JSONs, newest first
            session_files = sorted(glob.glob(str(sessions_dir / "*.json")), reverse=True)
            for f_path in session_files:
                try:
                    with open(f_path, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                        for ev in reversed(events):
                            ev_str = json.dumps(ev.get("payload", {}))
                            if q_lower in ev_str.lower():
                                matches.append(f"[{ev.get('timestamp', '')[:16]}] {ev.get('event_type')}: {ev_str[:300]}...")
                                if len(matches) >= limit:
                                    break
                except Exception:
                    pass
                if len(matches) >= limit:
                    break
                    
            if not matches:
                return f"No chat history matches found for '{query}'."
                
            return "Found past chat/events:\n" + "\n".join(matches)
        except Exception as e:
            return f"[Error] Failed to search chat history: {e}"

