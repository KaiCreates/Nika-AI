"""CronSchedulerTool — add/list/remove crontab entries."""
from __future__ import annotations

import asyncio
from typing import Any

from nika.tools.base import BaseTool


class CronSchedulerTool(BaseTool):
    name = "cron_scheduler"
    description = "Add, list, or remove crontab entries for scheduled tasks."
    parameters = {
        "action": {"type": "string", "description": "'list', 'add', or 'remove'."},
        "schedule": {"type": "string", "description": "Cron expression (e.g. '0 9 * * *')."},
        "command": {"type": "string", "description": "Command to schedule."},
        "comment": {"type": "string", "description": "Comment tag to identify the entry."},
    }
    required = ["action"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def _get_crontab(self) -> str:
        proc = await asyncio.create_subprocess_exec(
            "crontab", "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace")

    async def _set_crontab(self, content: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "crontab", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=content.encode())

    async def execute(
        self,
        action: str,
        schedule: str = "",
        command: str = "",
        comment: str = "nika",
    ) -> str:
        try:
            if action == "list":
                ct = await self._get_crontab()
                return ct.strip() or "No crontab entries."

            elif action == "add":
                if not schedule or not command:
                    return "[Error] schedule and command are required for add."
                ct = await self._get_crontab()
                new_line = f"{schedule} {command} # {comment}"
                ct = ct.rstrip("\n") + f"\n{new_line}\n"
                await self._set_crontab(ct)
                return f"Cron entry added: {new_line}"

            elif action == "remove":
                ct = await self._get_crontab()
                lines = [l for l in ct.splitlines() if f"# {comment}" not in l]
                await self._set_crontab("\n".join(lines) + "\n")
                return f"Removed cron entries with comment '{comment}'."

            else:
                return f"[Error] Unknown action: {action!r}"
        except FileNotFoundError:
            return "[Error] crontab command not available."
        except Exception as e:
            return f"[Error] Cron operation failed: {e}"
