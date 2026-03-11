"""WebSearchTool — DuckDuckGo search, no API key."""
from __future__ import annotations

from typing import Any

from nika.tools.base import BaseTool


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web using DuckDuckGo. Returns titles, URLs, and snippets."
    parameters = {
        "query": {"type": "string", "description": "Search query."},
        "max_results": {"type": "integer", "description": "Max results to return (default 5)."},
    }
    required = ["query"]
    safety_level = "SAFE"

    latest_results: list[dict] = []

    def __init__(self, config: Any = None) -> None:
        self.config = config

    async def execute(self, query: str, max_results: int = 5) -> str:
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    from duckduckgo_search import DDGS
                except ImportError:
                    return "[Error] ddgs package not installed. Run: pip install duckduckgo-search"
            
            WebSearchTool.latest_results = []
            text_results = []
            
            # Using the context manager is the correct modern way
            with DDGS() as ddgs:
                # Use the 'text' method which is the most reliable for general search
                search_gen = ddgs.text(query, max_results=max_results)
                if not search_gen:
                    return "No results found."
                    
                for r in search_gen:
                    item = {
                        "title": r.get("title", "No title"),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")
                    }
                    WebSearchTool.latest_results.append(item)
                    text_results.append(
                        f"### {item['title']}\n"
                        f"**SOURCE**: {item['href']}\n"
                        f"**CONTENT**: {item['body']}"
                    )
            
            if not text_results:
                return "No results found for your query, honey. Maybe try different keywords?"
                
            return "## WEB SEARCH RESULTS\n\n" + "\n\n---\n\n".join(text_results)
        except Exception as e:
            return f"[Error] Search failed: {e}"
