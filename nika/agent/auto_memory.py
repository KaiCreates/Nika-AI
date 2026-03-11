"""Deterministic personal-info extractor — saves facts to memory without relying on the LLM.

Runs on every user message. Patterns are conservative (high precision, lower recall)
so we don't save garbage. The LLM is still expected to save richer context via save_memory.
"""
from __future__ import annotations

import re
from typing import Any

# Each entry: (regex, template, category, tags)
# The first capture group becomes the value inserted into template.
_PATTERNS: list[tuple[str, str, str, list[str]]] = [
    # Name
    (r"\bmy name(?:'s| is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
     "User's name is {}", "fact", ["name"]),
    (r"\bi(?:'m| am)\s+([A-Z][a-z]+)(?:\s*[,.]|$)",
     "User's name is {}", "fact", ["name"]),

    # Location
    (r"\bi live (?:in|at)\s+(.+?)(?:\s*[,.]|$)",
     "User lives in {}", "fact", ["location"]),
    (r"\bfrom\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)?)\b",
     "User is from {}", "fact", ["location"]),

    # Job / workplace
    (r"\bi work(?:ed)? (?:at|for|@)\s+(.+?)(?:\s*[,.]|$)",
     "User works at {}", "fact", ["work"]),
    (r"\bi(?:'m| am) (?:a|an)\s+(developer|engineer|designer|doctor|teacher|student|"
     r"lawyer|nurse|manager|artist|writer|chef|mechanic|pilot|nurse|analyst|architect)\b",
     "User is a {}", "fact", ["job"]),

    # Relationships
    (r"\bmy (?:wife|girlfriend|partner|fiancée?)\s+(?:is\s+)?([A-Z][a-z]+)\b",
     "User's partner is {}", "person", ["relationship"]),
    (r"\bmy (?:husband|boyfriend|fiancé)\s+(?:is\s+)?([A-Z][a-z]+)\b",
     "User's partner is {}", "person", ["relationship"]),
    (r"\bmy (?:son|daughter|child|kid)\s+(?:is\s+)?([A-Z][a-z]+)\b",
     "User's child is {}", "person", ["family"]),
    (r"\bmy (?:mom|mother|dad|father|brother|sister)\s+(?:is\s+)?([A-Z][a-z]+)\b",
     "User's family member is {}", "person", ["family"]),
    (r"\bmy (?:dog|cat|pet)\s+(?:is\s+|'s\s+)?([A-Z][a-z]+)\b",
     "User's pet is called {}", "fact", ["pet"]),

    # Preferences
    (r"\bi (?:really )?(?:love|enjoy|like)\s+(.{5,50}?)(?:\s*[,.]|$)",
     "User enjoys {}", "preference", ["likes"]),
    (r"\bmy (?:favourite|favorite)\s+(.{4,50}?)\s+is\s+(.{3,40}?)(?:\s*[,.]|$)",
     "User's favourite {} is {}", "preference", ["favourite"]),

    # Projects / apps
    (r"\bi(?:'m| am) (?:building|working on|developing)\s+(.{5,60}?)(?:\s*[,.]|$)",
     "User is working on {}", "project", ["project"]),
    (r"\bi use\s+(.{3,40}?)\s+(?:for|to)\s+",
     "User uses {} regularly", "preference", ["tools"]),

    # Age
    (r"\bi(?:'m| am)\s+(\d{1,2})\s+years? old\b",
     "User is {} years old", "fact", ["age"]),

    # Achievements / Winning
    (r"\bi won (?:a|the)\s+(.+?)(?:\s*[,.]|$)",
     "User won {}", "fact", ["achievement"]),

    # Current Status / Schedule
    (r"\bi(?:'m| am) heading (?:off )?(?:to|for)\s+(.+?)(?:\s*[,.]|$)",
     "User is heading to {}", "fact", ["status", "schedule"]),
    (r"\bi(?:'m| am) going (?:off )?(?:to|for)\s+(.+?)(?:\s*[,.]|$)",
     "User is going to {}", "fact", ["status", "schedule"]),
    (r"\bi(?:'m| am) about to\s+(.+?)(?:\s*[,.]|$)",
     "User is about to {}", "fact", ["status", "schedule"]),
]

# Compiled at import time
_COMPILED = [
    (re.compile(pat, re.IGNORECASE), tmpl, cat, tags)
    for pat, tmpl, cat, tags in _PATTERNS
]


def extract_facts(text: str) -> list[dict]:
    """Return a list of {content, category, tags} dicts found in text."""
    results = []
    seen: set[str] = set()
    for pattern, tmpl, cat, tags in _COMPILED:
        for m in pattern.finditer(text):
            groups = [g.strip() for g in m.groups() if g]
            if not groups:
                continue
            content = tmpl.format(*groups)
            key = content.lower()
            if key not in seen:
                seen.add(key)
                results.append({"content": content, "category": cat, "tags": tags})
    return results


async def auto_save(text: str, memory_manager: Any) -> list[str]:
    """Extract facts from text and persist them. Returns list of saved memory IDs."""
    if memory_manager is None:
        return []
    facts = extract_facts(text)
    saved_ids: list[str] = []
    for fact in facts:
        try:
            mem_id = await memory_manager.save_memory(
                content=fact["content"],
                category=fact["category"],
                tags=fact["tags"],
            )
            saved_ids.append(mem_id)
        except Exception:
            pass
    return saved_ids
