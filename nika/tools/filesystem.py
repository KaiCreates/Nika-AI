"""Filesystem tools: Read, Write, List, Search, Move/Delete."""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nika.tools.base import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Supports optional line offset and limit."
    parameters = {
        "path": {"type": "string", "description": "Path to the file."},
        "offset": {"type": "integer", "description": "Line number to start from (1-indexed)."},
        "limit": {"type": "integer", "description": "Maximum number of lines to return."},
    }
    required = ["path"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, path: str, offset: int = 1, limit: int = 0) -> str:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[Error] File not found: {path}"
        if not p.is_file():
            return f"[Error] Not a file: {path}"
        try:
            lines = p.read_text(errors="replace").splitlines()
            start = max(0, offset - 1)
            end = (start + limit) if limit > 0 else len(lines)
            selected = lines[start:end]
            total = len(lines)
            header = f"[File: {path} | Lines {start+1}-{min(end, total)} of {total}]\n"
            return header + "\n".join(selected)
        except Exception as e:
            return f"[Error] Could not read file: {e}"


class WriteFileTool(BaseTool):
    name = "write_file"
    description = (
        "Write or append content to a file. Creates parent directories automatically. "
        "Backs up existing files if configured."
    )
    parameters = {
        "path": {"type": "string", "description": "Destination file path."},
        "content": {"type": "string", "description": "Content to write."},
        "mode": {"type": "string", "description": "'write' (default) or 'append'."},
        "backup": {"type": "boolean", "description": "Create .bak before overwriting (default true)."},
    }
    required = ["path", "content"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        path: str,
        content: str,
        mode: str = "write",
        backup: bool = True,
    ) -> str:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and mode == "write" and backup:
            bak = p.with_suffix(p.suffix + ".bak")
            shutil.copy2(p, bak)
        try:
            flag = "a" if mode == "append" else "w"
            p.write_text(content) if flag == "w" else open(p, "a").write(content)
            size = p.stat().st_size
            return f"File {'appended' if mode == 'append' else 'written'}: {path} ({size} bytes)"
        except Exception as e:
            return f"[Error] Could not write file: {e}"


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List directory contents with sizes, dates, and optional glob pattern."
    parameters = {
        "path": {"type": "string", "description": "Directory path."},
        "pattern": {"type": "string", "description": "Glob pattern to filter (e.g. '*.py')."},
        "recursive": {"type": "boolean", "description": "List recursively (default false)."},
    }
    required = ["path"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self, path: str, pattern: str = "*", recursive: bool = False
    ) -> str:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[Error] Path not found: {path}"
        if not p.is_dir():
            return f"[Error] Not a directory: {path}"
        try:
            glob_fn = p.rglob if recursive else p.glob
            entries = sorted(glob_fn(pattern), key=lambda x: (x.is_file(), x.name))
            if not entries:
                return f"No files matching '{pattern}' in {path}"
            lines = [f"{'TYPE':6} {'SIZE':>10}  {'NAME'}"]
            lines.append("-" * 50)
            for e in entries:
                t = "FILE" if e.is_file() else "DIR "
                sz = e.stat().st_size if e.is_file() else 0
                sz_str = f"{sz:,}" if e.is_file() else "-"
                rel = e.relative_to(p)
                lines.append(f"{t}   {sz_str:>10}  {rel}")
            return "\n".join(lines)
        except Exception as e:
            return f"[Error] Could not list directory: {e}"


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Find files by name pattern or search file contents recursively."
    parameters = {
        "path": {"type": "string", "description": "Root directory to search."},
        "name_pattern": {"type": "string", "description": "Filename glob pattern (e.g. '*.py')."},
        "content_pattern": {"type": "string", "description": "Text to search for inside files."},
        "max_results": {"type": "integer", "description": "Maximum results to return (default 50)."},
    }
    required = ["path"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        path: str,
        name_pattern: str = "*",
        content_pattern: str = "",
        max_results: int = 50,
    ) -> str:
        root = Path(path).expanduser()
        if not root.exists():
            return f"[Error] Path not found: {path}"
        results: list[str] = []
        try:
            for entry in root.rglob(name_pattern):
                if len(results) >= max_results:
                    break
                if entry.is_dir():
                    continue
                if content_pattern:
                    try:
                        text = entry.read_text(errors="replace")
                        if content_pattern.lower() in text.lower():
                            # Find matching lines
                            for i, line in enumerate(text.splitlines(), 1):
                                if content_pattern.lower() in line.lower():
                                    results.append(f"{entry}:{i}: {line.strip()}")
                                    if len(results) >= max_results:
                                        break
                    except Exception:
                        pass
                else:
                    results.append(str(entry))
            if not results:
                return "No results found."
            return "\n".join(results)
        except Exception as e:
            return f"[Error] Search failed: {e}"


class MoveDeleteFileTool(BaseTool):
    name = "move_delete_file"
    description = "Move, copy, or delete files and directories."
    parameters = {
        "action": {"type": "string", "description": "'move', 'copy', or 'delete'."},
        "source": {"type": "string", "description": "Source path."},
        "destination": {"type": "string", "description": "Destination path (for move/copy)."},
    }
    required = ["action", "source"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self, action: str, source: str, destination: str = ""
    ) -> str:
        src = Path(source).expanduser()
        if not src.exists():
            return f"[Error] Source not found: {source}"
        try:
            if action == "delete":
                if src.is_dir():
                    shutil.rmtree(src)
                else:
                    src.unlink()
                return f"Deleted: {source}"
            elif action in ("move", "copy"):
                if not destination:
                    return "[Error] Destination required for move/copy."
                dst = Path(destination).expanduser()
                dst.parent.mkdir(parents=True, exist_ok=True)
                if action == "move":
                    shutil.move(str(src), str(dst))
                    return f"Moved: {source} → {destination}"
                else:
                    if src.is_dir():
                        shutil.copytree(str(src), str(dst))
                    else:
                        shutil.copy2(str(src), str(dst))
                    return f"Copied: {source} → {destination}"
            else:
                return f"[Error] Unknown action: {action!r}. Use 'move', 'copy', or 'delete'."
        except Exception as e:
            return f"[Error] {action} failed: {e}"


class GetPathInfoTool(BaseTool):
    name = "get_path_info"
    description = "Get detailed information about a path (file vs directory, size, exists, etc.)."
    parameters = {
        "path": {"type": "string", "description": "Path to check."},
    }
    required = ["path"]
    safety_level = "SAFE"

    _cache: dict[str, tuple[float, str]] = {}  # path -> (timestamp, json_info)
    _CACHE_TTL = 5.0  # 5 seconds

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, path: str) -> str:
        p = Path(path).expanduser()
        p_str = str(p)
        
        # Check cache
        import time
        now = time.time()
        if p_str in self._cache:
            ts, info_json = self._cache[p_str]
            if now - ts < self._CACHE_TTL:
                return info_json

        if not p.exists():
            res = f"Path does not exist: {path}"
            self._cache[p_str] = (now, res)
            return res
        
        info = {
            "path": p_str,
            "exists": True,
            "type": "directory" if p.is_dir() else "file" if p.is_file() else "other",
            "size_bytes": p.stat().st_size if p.is_file() else 0,
            "modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        res = json.dumps(info, indent=2)
        self._cache[p_str] = (now, res)
        return res


class ListRecentChangesTool(BaseTool):
    name = "list_recent_changes"
    description = "List the most recently modified files and directories in a path."
    parameters = {
        "path": {"type": "string", "description": "Directory to scan."},
        "limit": {"type": "integer", "description": "Max number of items to return (default 10)."},
    }
    required = ["path"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, path: str, limit: int = 10) -> str:
        p = Path(path).expanduser()
        if not p.exists() or not p.is_dir():
            return f"[Error] Valid directory not found: {path}"
        
        try:
            entries = []
            for entry in p.rglob("*"):
                if entry.name.startswith(".") or ".venv" in str(entry):
                    continue
                mtime = entry.stat().st_mtime
                entries.append((entry, mtime))
            
            # Sort by modification time descending
            entries.sort(key=lambda x: x[1], reverse=True)
            
            top = entries[:limit]
            if not top:
                return f"No changes found in {path}"
            
            lines = [f"Recent changes in {path}:"]
            for entry, mtime in top:
                dt = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                t = "DIR " if entry.is_dir() else "FILE"
                lines.append(f"[{dt}] {t} {entry.relative_to(p)}")
            
            return "\n".join(lines)
        except Exception as e:
            return f"[Error] Failed to list changes: {e}"


class LocatePathTool(BaseTool):
    name = "locate_path"
    description = (
        "Search for a file or directory by name in common user locations "
        "(Documents, Downloads, Desktop, etc.) when the exact path is unknown. "
        "Highly efficient for finding projects or files by name."
    )
    parameters = {
        "name": {"type": "string", "description": "The name or fragment of the file/directory to find."},
        "search_type": {"type": "string", "description": "'all', 'file', or 'directory'. Default 'all'."},
        "depth": {"type": "integer", "description": "Max search depth per root. Default 3."},
    }
    required = ["name"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, name: str, search_type: str = "all", depth: int = 3) -> str:
        import asyncio
        import shlex

        home = Path.home()
        # Common locations to check
        roots = [
            home,
            home / "Documents",
            home / "Downloads",
            home / "Desktop",
            home / "Projects",
            home / "workspace",
        ]
        # Filter to existing directories
        roots = [r for r in roots if r.exists() and r.is_dir()]
        
        # Build find command
        type_flag = ""
        if search_type == "file":
            type_flag = "-type f"
        elif search_type == "directory":
            type_flag = "-type d"

        # Search for exact name first, then fragment
        patterns = [name, f"*{name}*"]
        results = set()

        async def _search_root(root: Path) -> None:
            for pattern in patterns:
                cmd = (
                    f"find {shlex.quote(str(root))} -maxdepth {depth} "
                    f"-name {shlex.quote(pattern)} {type_flag} -not -path '*/.*' "
                    f"-not -path '*/node_modules/*' -not -path '*/.venv/*' "
                    f"2>/dev/null | head -n 10"
                )
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                for line in stdout.decode().splitlines():
                    if line.strip():
                        results.add(line.strip())
                if len(results) >= 20:
                    break

        # Run searches in parallel
        await asyncio.gather(*[_search_root(r) for r in roots])

        if not results:
            return f"No matches found for '{name}' in common directories."
        
        sorted_res = sorted(list(results), key=len) # Prefer shorter paths
        return "Found the following matches:\n" + "\n".join(sorted_res[:20])


class ExploreHomeTool(BaseTool):
    name = "explore_home"
    description = (
        "Quickly list the top-level contents of all common user directories "
        "(Documents, Downloads, Desktop, Projects, etc.) to get an overview of where things are."
    )
    parameters = {}
    required = []
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self) -> str:
        home = Path.home()
        dirs = ["Documents", "Downloads", "Desktop", "Projects", "workspace", "Pictures", "Videos"]
        
        output = []
        for d_name in dirs:
            p = home / d_name
            if p.exists() and p.is_dir():
                try:
                    # List top 5 items in each
                    items = sorted([item.name for item in p.iterdir() if not item.name.startswith(".")])
                    if items:
                        display = ", ".join(items[:8])
                        if len(items) > 8:
                            display += f", ... (+{len(items)-8} more)"
                        output.append(f"~/{d_name}: {display}")
                    else:
                        output.append(f"~/{d_name}: (empty)")
                except Exception:
                    output.append(f"~/{d_name}: (could not list)")
        
        # Also list home root
        try:
            home_items = sorted([item.name for item in home.iterdir() if not item.name.startswith(".") and item.is_dir()])
            output.insert(0, f"~/: {', '.join(home_items[:10])}")
        except Exception:
            pass

        return "\n".join(output)


class ReadMultipleFilesTool(BaseTool):
    name = "read_multiple_files"
    description = (
        "Read the first few lines of multiple files at once. "
        "Useful for quickly scanning several files in a directory."
    )
    parameters = {
        "paths": {"type": "array", "items": {"type": "string"}, "description": "List of file paths."},
        "limit": {"type": "integer", "description": "Max lines per file (default 10)."},
    }
    required = ["paths"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, paths: list[str], limit: int = 10) -> str:
        results = []
        for path in paths:
            p = Path(path).expanduser()
            if not p.exists() or not p.is_file():
                results.append(f"--- {path} (Not found) ---")
                continue
            try:
                lines = p.read_text(errors="replace").splitlines()
                content = "\n".join(lines[:limit])
                results.append(f"--- {path} (showing first {limit} lines) ---\n{content}")
            except Exception as e:
                results.append(f"--- {path} (Error: {e}) ---")
        
        return "\n\n".join(results)
