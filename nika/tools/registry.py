"""Tool registry — auto-registers tools and dispatches calls."""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from nika.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def manifest(self) -> str:
        return "\n\n".join(t.to_manifest() for t in self._tools.values())

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"[Error] Unknown tool: {name!r}. Available: {', '.join(self.names())}"
        try:
            result = await tool.execute(**args)
            return result
        except TypeError as e:
            return f"[Error] Bad arguments for tool '{name}': {e}"
        except Exception as e:
            logger.exception(f"Tool '{name}' raised an exception")
            return f"[Error] Tool '{name}' failed: {e}"

    def load_builtin_tools(self, config: Any) -> None:
        """Load all built-in tool modules."""
        from nika.tools.shell import ShellTool
        from nika.tools.filesystem import (
            ReadFileTool, WriteFileTool, ListDirectoryTool,
            SearchFilesTool, MoveDeleteFileTool, GetPathInfoTool,
            ListRecentChangesTool, LocatePathTool, ExploreHomeTool,
            ReadMultipleFilesTool,
        )
        from nika.tools.document_writer import DocumentWriterTool
        from nika.tools.web_search import WebSearchTool
        from nika.tools.web_fetch import FetchPageTool
        from nika.tools.code_runner import CodeRunnerTool
        from nika.tools.system_info import SystemInfoTool
        from nika.tools.process_manager import ProcessManagerTool
        from nika.tools.scheduler import CronSchedulerTool
        from nika.tools.clipboard import ClipboardTool
        from nika.tools.diff import DiffTool
        from nika.tools.notification import NotificationTool
        from nika.tools.pdf_export import PDFExportTool
        from nika.tools.memory_tools import SaveMemoryTool, RecallMemoryTool, SummarizeSessionTool, RecallChatHistoryTool
        from nika.tools.screen import ScreenshotTool, ScreenControlTool, OpenAppTool

        for tool_cls in [
            ShellTool, ReadFileTool, WriteFileTool, ListDirectoryTool,
            SearchFilesTool, MoveDeleteFileTool, GetPathInfoTool,
            ListRecentChangesTool, LocatePathTool, ExploreHomeTool,
            ReadMultipleFilesTool, DocumentWriterTool,
            WebSearchTool, FetchPageTool, CodeRunnerTool, SystemInfoTool,
            ProcessManagerTool, CronSchedulerTool, ClipboardTool, DiffTool,
            NotificationTool, PDFExportTool, SaveMemoryTool, RecallMemoryTool,
            SummarizeSessionTool, RecallChatHistoryTool, ScreenshotTool, ScreenControlTool, OpenAppTool,
        ]:
            self.register(tool_cls(config=config))

    def load_plugins(self, plugins_dir: Path) -> None:
        """Scan plugins dir and load any BaseTool subclasses found."""
        if not plugins_dir.exists():
            return
        for py_file in plugins_dir.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[py_file.stem] = module
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, BaseTool)
                        and obj is not BaseTool
                        and obj.name
                    ):
                        self.register(obj())
                        logger.info(f"Plugin loaded: {obj.name} from {py_file.name}")
            except Exception as e:
                logger.warning(f"Failed to load plugin {py_file}: {e}")
