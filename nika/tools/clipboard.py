"""ClipboardTool — read/write system clipboard."""
from __future__ import annotations

from typing import Any

from nika.tools.base import BaseTool


class ClipboardTool(BaseTool):
    name = "clipboard"
    description = "Read from or write to the system clipboard."
    parameters = {
        "action": {"type": "string", "description": "'read' or 'write'."},
        "content": {"type": "string", "description": "Content to write (for write action)."},
    }
    required = ["action"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, action: str, content: str = "") -> str:
        try:
            import pyperclip
            if action == "read":
                text = pyperclip.paste()
                return f"Clipboard contents:\n{text}"
            elif action == "write":
                pyperclip.copy(content)
                return f"Copied to clipboard ({len(content)} chars)."
            else:
                return f"[Error] Unknown action: {action!r}"
        except ImportError:
            return "[Error] pyperclip not installed."
        except Exception as e:
            return f"[Error] Clipboard operation failed: {e}"
