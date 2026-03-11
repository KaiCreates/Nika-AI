"""DocumentWriterTool — create formatted markdown reports."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from nika.tools.base import BaseTool


class DocumentWriterTool(BaseTool):
    name = "document_writer"
    description = (
        "Create a formatted markdown document and save it to the documents directory. "
        "Returns the path of the created file."
    )
    parameters = {
        "title": {"type": "string", "description": "Document title."},
        "content": {"type": "string", "description": "Markdown content body."},
        "filename": {"type": "string", "description": "Filename (without extension). Auto-generated if omitted."},
        "tags": {"type": "array", "description": "Optional list of tag strings."},
    }
    required = ["title", "content"]
    safety_level = "CAUTION"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(
        self,
        title: str,
        content: str,
        filename: str = "",
        tags: list[str] | None = None,
    ) -> str:
        from nika.config import resolve
        today = date.today().isoformat()
        out_dir = resolve(self.config.documents.output_dir) / today if self.config else Path(f"data/documents/{today}")
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_name = filename or title.lower().replace(" ", "_").replace("/", "_")[:60]
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
        filepath = out_dir / f"{safe_name}.md"

        tag_line = ""
        if tags:
            tag_line = f"\n**Tags:** {', '.join(tags)}\n"

        full_content = f"# {title}\n\n_Created: {today}_\n{tag_line}\n---\n\n{content}\n"
        filepath.write_text(full_content)
        return f"Document created: {filepath}"
