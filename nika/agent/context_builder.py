"""Assembles the full message context for each LLM call."""
from __future__ import annotations

from typing import Any

import tiktoken

from nika.llm.prompt_templates import build_system_message


def _count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4  # rough fallback


def build_context(
    messages: list[dict[str, str]],
    tool_manifest: str,
    memories: list[dict],
    episodes: list[dict],
    token_limit: int = 6000,
) -> list[dict[str, str]]:
    """
    Build the message list for the LLM call, respecting token budget.
    Returns [system_msg, ...conversation_messages].
    """
    mem_text = ""
    if memories:
        lines = [f"- [{m.get('category', 'fact')}] {m['content']}" for m in memories]
        mem_text = "\n".join(lines)

    ep_text = ""
    if episodes:
        parts = []
        for ep in episodes:
            parts.append(f"**Session {ep.get('session_id', '?')}** ({ep.get('started_at', '')[:10]}): {ep.get('summary', '')}")
        ep_text = "\n".join(parts)

    system_content = build_system_message(
        tool_descriptions=tool_manifest,
        memories=mem_text,
        episodes=ep_text,
    )
    system_msg = {"role": "system", "content": system_content}

    # Trim conversation to fit budget
    budget = token_limit - _count_tokens(system_content) - 200  # headroom
    trimmed: list[dict[str, str]] = []
    used = 0
    for msg in reversed(messages):
        tokens = _count_tokens(msg["content"])
        if used + tokens > budget:
            break
        trimmed.insert(0, msg)
        used += tokens

    return [system_msg] + trimmed
