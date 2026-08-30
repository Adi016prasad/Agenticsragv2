"""
Free Web Search & Source Extraction Tool for Last-Resort Research.
Extracts search results along with ground-proof URLs.
"""
from __future__ import annotations

import logging
from typing import Type
import requests
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query to look up on the open web.")


class DuckDuckGoWebSearchTool(BaseTool):
    name: str = "Search Open Web with Source URLs"
    description: str = (
        "Searches the public web for real-time information, policy details, or facts. "
        "Returns snippets along with their direct, clickable source URLs."
    )
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, query: str) -> str:
        logger.info(f"🌐 Executing Open Web Search for: '{query}'")
        try:
            # Free DuckDuckGo HTML search
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            url = "https://html.duckduckgo.com/html/"
            response = requests.post(url, data={"q": query}, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            for result in soup.find_all("div", class_="result", limit=4):
                title_elem = result.find("a", class_="result__a")
                snippet_elem = result.find("a", class_="result__snippet")
                url_elem = result.find("a", class_="result__url")

                if title_elem and snippet_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True)
                    raw_href = title_elem.get("href", "")
                    
                    # Extract clean URL
                    if "uddg=" in raw_href:
                        import urllib.parse
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                        clean_url = parsed.get("uddg", [raw_href])[0]
                    else:
                        clean_url = raw_href

                    results.append({
                        "title": title,
                        "snippet": snippet,
                        "source_url": clean_url
                    })

            if not results:
                return f"No open web results found for query: '{query}'."

            output = "Web Search Results with Ground-Proof Sources:\n\n"
            for r in results:
                output += f"• **Title:** {r['title']}\n"
                output += f"  **Snippet:** {r['snippet']}\n"
                output += f"  **Source Link:** {r['source_url']}\n\n"

            return output

        except Exception as exc:
            logger.error(f"Web search failed: {exc}")
            return f"Web search error: {exc}"