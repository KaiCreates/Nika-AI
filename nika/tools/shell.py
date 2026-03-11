"""ShellTool — subprocess with timeout and safety gate."""
from __future__ import annotations

import asyncio
import shlex
from typing import Any

from nika.tools.base import BaseTool


class ShellTool(BaseTool):
    name = "shell"
    description = "Run a shell command. Captures stdout, stderr, and exit code."
    parameters = {
        "command": {
            "type": "string",
            "description": "The shell command to run.",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default 30).",
        },
        "workdir": {
            "type": "string",
            "description": "Working directory for the command.",
        },
    }
    required = ["command"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        workdir: str | None = None,
    ) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout)
            )
            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            code = proc.returncode

            parts = [f"Exit code: {code}"]
            if out:
                parts.append(f"stdout:\n{out}")
            if err:
                parts.append(f"stderr:\n{err}")
            return "\n".join(parts)
        except asyncio.TimeoutError:
            return f"[Error] Command timed out after {timeout}s: {command}"
        except Exception as e:
            return f"[Error] Failed to run command: {e}"
