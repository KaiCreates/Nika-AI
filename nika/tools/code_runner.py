"""CodeRunnerTool — execute Python snippets in a subprocess."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from nika.tools.base import BaseTool


class CodeRunnerTool(BaseTool):
    name = "run_code"
    description = "Execute a Python code snippet. Returns stdout, stderr, and exit code."
    parameters = {
        "code": {"type": "string", "description": "Python code to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."},
    }
    required = ["code"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, code: str, timeout: int = 30) -> str:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            tmp_path = f.name
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            code_val = proc.returncode
            parts = [f"Exit code: {code_val}"]
            if out:
                parts.append(f"stdout:\n{out}")
            if err:
                parts.append(f"stderr:\n{err}")
            return "\n".join(parts)
        except asyncio.TimeoutError:
            return f"[Error] Code execution timed out after {timeout}s"
        except Exception as e:
            return f"[Error] Execution failed: {e}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)
