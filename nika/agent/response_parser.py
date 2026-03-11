"""Parse <tool_call> and <final_answer> blocks from LLM output."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    raw: str


@dataclass
class ParseResult:
    tool_calls: list[ToolCall]
    final_answer: str | None
    thinking: str   # combined thinking blocks


_THINKING_RE = re.compile(
    r"<thinking>\s*(.*?)\s*</thinking>",
    re.DOTALL | re.IGNORECASE,
)
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_FINAL_ANSWER_RE = re.compile(
    r"<final_answer>\s*(.*?)\s*</final_answer>",
    re.DOTALL | re.IGNORECASE,
)


def parse_response(text: str) -> ParseResult:
    """Extract <thinking>, <tool_call>, and <final_answer> blocks, handling unclosed tags."""
    tool_calls: list[ToolCall] = []
    final_answer: str | None = None
    thinking_parts: list[str] = []

    # Helper to find blocks even if they aren't closed
    def get_blocks(tag_name, content):
        open_tag = f"<{tag_name}>"
        close_tag = f"</{tag_name}>"
        results = []
        start = 0
        while True:
            idx = content.find(open_tag, start)
            if idx == -1: break
            end_idx = content.find(close_tag, idx)
            if end_idx != -1:
                results.append(content[idx + len(open_tag):end_idx].strip())
                start = end_idx + len(close_tag)
            else:
                # Unclosed tag: take everything to the end
                results.append(content[idx + len(open_tag):].strip())
                break
        return results

    # 1. Extract thinking
    thinking_parts = get_blocks("thinking", text)

    # 2. Extract tool calls
    tc_blocks = get_blocks("tool_call", text)
    for raw in tc_blocks:
        try:
            data = json.loads(raw)
            tool_calls.append(ToolCall(
                tool=data.get("tool", ""),
                args=data.get("args", {}),
                raw=raw,
            ))
        except json.JSONDecodeError:
            tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', raw)
            if tool_match:
                tool_calls.append(ToolCall(tool=tool_match.group(1), args={}, raw=raw))

    # Fallback: if no tool_call tags, but there's something that looks like a tool JSON
    if not tool_calls:
        raw_json_match = re.search(r'\{\s*"tool"\s*:\s*"[^"]+".*?\}', text, re.DOTALL)
        if raw_json_match:
            try:
                raw = raw_json_match.group(0)
                data = json.loads(raw)
                tool_calls.append(ToolCall(tool=data.get("tool", ""), args=data.get("args", {}), raw=raw))
            except Exception:
                pass

    # 3. Extract final answer
    fa_blocks = get_blocks("final_answer", text)
    if fa_blocks:
        final_answer = fa_blocks[-1] # take the last one

    # 4. Fallback for no tags at all
    if not thinking_parts and not tool_calls and not final_answer:
        return ParseResult(tool_calls=[], final_answer=None, thinking=text.strip())

    return ParseResult(
        tool_calls=tool_calls,
        final_answer=final_answer,
        thinking="\n---\n".join(thinking_parts),
    )
