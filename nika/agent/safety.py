"""Safety gate — classify risk of tool calls as SAFE / CAUTION / DANGEROUS."""
from __future__ import annotations

import re
from typing import Any

# Patterns that trigger DANGEROUS classification
_DANGEROUS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"rm\s+-rf\s+[/~]",         # rm -rf /
        r"rm\s+-rf\s+\*",            # rm -rf *
        r"shutdown",
        r"reboot",
        r"halt\s",
        r"dd\s+if=",                 # disk wipe
        r"mkfs\.",                   # format filesystem
        r"curl.+\|.+bash",           # curl | bash
        r"wget.+\|.+sh",
        r"chmod\s+777\s+/",
        r"chown\s+.+\s+/",
        r":()\{.*\}",                # fork bomb
        r">\s*/dev/sda",             # write to disk device
        r"truncate.*--size\s*0\s+/", # truncate system files
    ]
]

# Patterns that are always SAFE regardless of tool
_SAFE_COMMANDS = re.compile(
    r"^(ls|cat|head|tail|grep|find|echo|pwd|whoami|id|uname|df|du|ps|top|date|cal|which|type|env|printenv|history)(\s|$)",
    re.IGNORECASE,
)


def classify_tool_call(tool_name: str, args: dict[str, Any]) -> str:
    """Return 'SAFE', 'CAUTION', or 'DANGEROUS'."""
    # Read-only tools are always SAFE
    if tool_name in {
        "system_info", "read_file", "list_directory", "search_files",
        "diff", "recall_memory", "web_search", "fetch_page", "clipboard",
    }:
        return "SAFE"

    # Shell and delete operations need deeper inspection
    if tool_name == "shell":
        command = args.get("command", "")
        # Robustness: ensure command is a string (LLM sometimes hallucinates a list)
        if isinstance(command, list):
            command = " ".join(str(c) for c in command)
        elif not isinstance(command, str):
            command = str(command)

        for pattern in _DANGEROUS_PATTERNS:
            if pattern.search(command):
                return "DANGEROUS"
        if _SAFE_COMMANDS.match(command.strip()):
            return "SAFE"
        return "CAUTION"

    if tool_name == "move_delete_file":
        action = args.get("action", "")
        source = args.get("source", "")
        if action == "delete" and ("/" == source or source.startswith("/etc") or source.startswith("/usr")):
            return "DANGEROUS"
        if action == "delete":
            return "CAUTION"
        return "CAUTION"

    if tool_name in {"write_file", "run_code", "cron_scheduler", "process_manager"}:
        return "CAUTION"

    return "SAFE"


def is_allowed(risk: str, mode: str) -> bool:
    """Return True if this risk level is auto-approved in the given mode."""
    if mode == "YOLO":
        return True
    if mode == "STRICT":
        return risk == "SAFE"
    # NORMAL mode
    return risk in ("SAFE", "CAUTION")
