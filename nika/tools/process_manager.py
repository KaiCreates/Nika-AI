"""ProcessManagerTool — list and kill processes."""
from __future__ import annotations

from typing import Any

from nika.tools.base import BaseTool


class ProcessManagerTool(BaseTool):
    name = "process_manager"
    description = "List running processes or kill a process by PID or name."
    parameters = {
        "action": {"type": "string", "description": "'list', 'kill', or 'check'."},
        "pid": {"type": "integer", "description": "Process ID (for kill/check)."},
        "name": {"type": "string", "description": "Process name filter (for list/kill)."},
        "signal": {"type": "string", "description": "Signal to send for kill (default TERM)."},
    }
    required = ["action"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        action: str,
        pid: int | None = None,
        name: str = "",
        signal: str = "TERM",
    ) -> str:
        try:
            import psutil, signal as sig_module

            if action == "list":
                procs = []
                for p in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_percent"]):
                    if name and name.lower() not in p.info["name"].lower():
                        continue
                    procs.append(
                        f"PID {p.info['pid']:6d} | {p.info['name']:30s} | "
                        f"{p.info['status']:10s} | CPU {p.info.get('cpu_percent', 0):.1f}%"
                    )
                return "\n".join(procs[:50]) if procs else "No matching processes."

            elif action == "kill":
                targets = []
                if pid:
                    targets.append(psutil.Process(pid))
                elif name:
                    for p in psutil.process_iter(["name"]):
                        if name.lower() in p.info["name"].lower():
                            targets.append(p)
                if not targets:
                    return "No matching processes found."
                sig_val = getattr(sig_module, f"SIG{signal.upper()}", sig_module.SIGTERM)
                killed = []
                for p in targets:
                    try:
                        p.send_signal(sig_val)
                        killed.append(str(p.pid))
                    except Exception as e:
                        killed.append(f"{p.pid} (error: {e})")
                return f"Signal {signal} sent to PID(s): {', '.join(killed)}"

            elif action == "check":
                if not pid:
                    return "[Error] pid required for check action."
                try:
                    p = psutil.Process(pid)
                    return f"PID {pid}: {p.name()} | status={p.status()} | cpu={p.cpu_percent():.1f}%"
                except psutil.NoSuchProcess:
                    return f"PID {pid} not found."
            else:
                return f"[Error] Unknown action: {action!r}"
        except ImportError:
            return "[Error] psutil not installed."
        except Exception as e:
            return f"[Error] {e}"
