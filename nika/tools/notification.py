"""NotificationTool — desktop notify-send alerts."""
from __future__ import annotations

import asyncio
from typing import Any

from nika.tools.base import BaseTool


class NotificationTool(BaseTool):
    name = "notify"
    description = "Send a desktop notification via notify-send."
    parameters = {
        "title": {"type": "string", "description": "Notification title."},
        "body": {"type": "string", "description": "Notification body text."},
        "urgency": {"type": "string", "description": "'low', 'normal', or 'critical' (default normal)."},
        "timeout": {"type": "integer", "description": "Timeout in ms (default 5000)."},
    }
    required = ["title"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        title: str,
        body: str = "",
        urgency: str = "normal",
        timeout: int = 5000,
    ) -> str:
        try:
            cmd = ["notify-send", "-u", urgency, "-t", str(timeout), title]
            if body:
                cmd.append(body)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip()
                return f"[Error] notify-send failed: {err}"
            return f"Notification sent: {title!r}"
        except FileNotFoundError:
            return "[Error] notify-send not available on this system."
        except asyncio.TimeoutError:
            return "[Error] Notification timed out."
        except Exception as e:
            return f"[Error] Notification failed: {e}"
