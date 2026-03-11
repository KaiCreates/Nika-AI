"""Multi-step task decomposition — generates a numbered plan from a goal."""
from __future__ import annotations

from typing import Any

from nika.llm.client import OllamaClient

PLANNER_PROMPT = """You are a task planner. Given the user's goal, break it into 3-7 concrete, numbered steps.
Each step should be a specific action Nika can take. Output ONLY the numbered list, no other text.

Example:
1. Check current CPU and memory usage
2. Identify top resource-consuming processes
3. Write a system health report to documents/health_report.md
4. Send a desktop notification when done

Goal: {goal}
"""


async def create_plan(
    goal: str,
    client: OllamaClient,
    model: str,
) -> list[str]:
    """Return a list of step strings for the given goal."""
    prompt = PLANNER_PROMPT.format(goal=goal)
    response = await client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    steps = []
    for line in response.strip().splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            # Strip leading "1. " etc.
            step = line.split(".", 1)[-1].strip()
            if step:
                steps.append(step)
    return steps


def needs_planning(task: str) -> bool:
    """Heuristic: does this task need multi-step planning?"""
    multi_signals = [
        "and then", "after that", "first", "then", "finally",
        "step", "report", "multiple", "analyze and", "create and",
        "check and", "research and", "find and write",
    ]
    lower = task.lower()
    return any(s in lower for s in multi_signals) or len(task.split()) > 20
