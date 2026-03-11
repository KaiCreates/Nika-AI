"""FetchPageTool — fetch and extract readable text from a URL."""
from __future__ import annotations

from typing import Any

from nika.tools.base import BaseTool


class FetchPageTool(BaseTool):
    name = "fetch_page"
    description = "Fetch a web page and extract readable text content."
    parameters = {
        "url": {"type": "string", "description": "URL to fetch."},
        "max_chars": {"type": "integer", "description": "Max characters to return (default 4000)."},
    }
    required = ["url"]
    safety_level = "SAFE"

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, url: str, max_chars: int = 4000) -> str:
        try:
            import httpx
            import trafilatura

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 Nika-AI/1.0"},
                )
                resp.raise_for_status()
                html = resp.text

            text = trafilatura.extract(html, include_links=False, include_tables=False)
            if not text:
                # Fallback: return raw stripped text
                import re
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()

            return f"[URL: {url}]\n\n{text[:max_chars]}"
        except ImportError as e:
            return f"[Error] Missing dependency: {e}"
        except Exception as e:
            return f"[Error] Failed to fetch page: {e}"
