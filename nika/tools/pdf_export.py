"""PDFExportTool — convert markdown to PDF via weasyprint or pandoc."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from nika.tools.base import BaseTool


class PDFExportTool(BaseTool):
    name = "pdf_export"
    description = "Convert a markdown file to PDF using weasyprint or pandoc."
    parameters = {
        "input_path": {"type": "string", "description": "Path to the markdown file."},
        "output_path": {"type": "string", "description": "Output PDF path (auto-generated if omitted)."},
    }
    required = ["input_path"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, input_path: str, output_path: str = "") -> str:
        src = Path(input_path).expanduser()
        if not src.exists():
            return f"[Error] File not found: {input_path}"

        out = Path(output_path).expanduser() if output_path else src.with_suffix(".pdf")
        out.parent.mkdir(parents=True, exist_ok=True)

        # Try pandoc first (more reliable for markdown)
        try:
            proc = await asyncio.create_subprocess_exec(
                "pandoc", str(src), "-o", str(out),
                "--pdf-engine=weasyprint",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
                return f"PDF created via pandoc: {out}"
            # fallback below
        except (FileNotFoundError, asyncio.TimeoutError):
            pass

        # Try weasyprint directly
        try:
            import markdown as md_lib
            from weasyprint import HTML

            html_content = md_lib.markdown(src.read_text())
            html = f"<html><body>{html_content}</body></html>"
            HTML(string=html).write_pdf(str(out))
            return f"PDF created via weasyprint: {out}"
        except ImportError as e:
            return f"[Error] PDF export requires pandoc or weasyprint+markdown: {e}"
        except Exception as e:
            return f"[Error] PDF export failed: {e}"
