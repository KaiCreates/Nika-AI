"""SystemInfoTool — CPU, RAM, disk, battery, uptime via psutil."""
from __future__ import annotations

from typing import Any

from nika.tools.base import BaseTool


class SystemInfoTool(BaseTool):
    name = "system_info"
    description = "Get a snapshot of system resources: CPU, RAM, disk, battery, uptime."
    parameters = {}
    required = []
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self) -> str:
        try:
            import psutil, datetime

            cpu = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            boot = datetime.datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.datetime.now() - boot

            lines = [
                f"CPU: {cpu}% ({cpu_count} cores)",
                f"RAM: {ram.used / 1e9:.1f} GB used / {ram.total / 1e9:.1f} GB total ({ram.percent}%)",
                f"Disk (/): {disk.used / 1e9:.1f} GB used / {disk.total / 1e9:.1f} GB total ({disk.percent}%)",
                f"Uptime: {str(uptime).split('.')[0]}",
            ]

            try:
                battery = psutil.sensors_battery()
                if battery:
                    status = "charging" if battery.power_plugged else "discharging"
                    lines.append(f"Battery: {battery.percent:.0f}% ({status})")
            except Exception:
                pass

            # Top 5 CPU processes
            procs = sorted(
                psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get("cpu_percent", 0) or 0,
                reverse=True,
            )[:5]
            lines.append("\nTop processes by CPU:")
            for p in procs:
                lines.append(
                    f"  {p.info['name']}: CPU {p.info.get('cpu_percent', 0):.1f}%, "
                    f"RAM {p.info.get('memory_percent', 0):.1f}%"
                )
            return "\n".join(lines)
        except ImportError:
            return "[Error] psutil not installed."
        except Exception as e:
            return f"[Error] Could not get system info: {e}"
