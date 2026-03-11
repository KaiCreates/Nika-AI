"""DiffTool — unified diff between two files or strings."""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from nika.tools.base import BaseTool


class DiffTool(BaseTool):
    name = "diff"
    description = "Show a unified diff between two files or two strings."
    parameters = {
        "a": {"type": "string", "description": "First file path or text string."},
        "b": {"type": "string", "description": "Second file path or text string."},
        "from_files": {"type": "boolean", "description": "If true, treat a and b as file paths (default true)."},
        "context_lines": {"type": "integer", "description": "Context lines around changes (default 3)."},
    }
    required = ["a", "b"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        a: str,
        b: str,
        from_files: bool = True,
        context_lines: int = 3,
    ) -> str:
        try:
            if from_files:
                pa, pb = Path(a).expanduser(), Path(b).expanduser()
                if not pa.exists():
                    return f"[Error] File not found: {a}"
                if not pb.exists():
                    return f"[Error] File not found: {b}"
                lines_a = pa.read_text(errors="replace").splitlines(keepends=True)
                lines_b = pb.read_text(errors="replace").splitlines(keepends=True)
                label_a, label_b = a, b
            else:
                lines_a = [l + "\n" for l in a.splitlines()]
                lines_b = [l + "\n" for l in b.splitlines()]
                label_a, label_b = "a", "b"

            diff = list(difflib.unified_diff(
                lines_a, lines_b,
                fromfile=label_a, tofile=label_b,
                n=context_lines,
            ))
            if not diff:
                return "No differences found."
            return "".join(diff)
        except Exception as e:
            return f"[Error] Diff failed: {e}"
