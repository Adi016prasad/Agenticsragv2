import re
from abc import ABC, abstractmethod
from typing import Any
from .table_html_parser import parse_complex_html_table

class TableRestructurer(ABC):
    @abstractmethod
    def restructure(self, table_item: Any) -> str:
        pass


class HtmlTableRestructurer(TableRestructurer):
    """
    Uses real HTML rowspan/colspan attributes via parse_complex_html_table
    to resolve merged cells into sentence blocks, wrapped in atomic markers.
    Automatically filters out auto-generated 'Column_N' labels.
    """

    # Regex to catch auto-generated header names like Column_0, Column_1, etc.
    COLUMN_HEADER_RE = re.compile(r"^Column_\d+$", re.IGNORECASE)

    def restructure(self, table_item: Any) -> str:
        html = getattr(table_item, "html", None)

        # Fallback if no HTML is available
        if not html:
            md_fallback = getattr(table_item, "md", "")
            if md_fallback:
                return f"[TABLE_START]\n{md_fallback}\n[TABLE_END]"
            return ""

        rows = parse_complex_html_table(html)
        if not rows:
            md_fallback = getattr(table_item, "md", "")
            if md_fallback:
                return f"[TABLE_START]\n{md_fallback}\n[TABLE_END]"
            return ""

        sentences = []
        for row in rows:
            parts = []
            for header, value in row.items():
                if not header or not value:
                    continue

                header_str = str(header).strip()
                value_str = str(value).strip()

                if not value_str:
                    continue

                # If the header is a dummy generated name (Column_0, Column_1...),
                # output only the cell value. Otherwise, keep "Header: Value".
                if self.COLUMN_HEADER_RE.match(header_str):
                    parts.append(value_str)
                else:
                    parts.append(f"{header_str}: {value_str}")

            if parts:
                sentences.append("; ".join(parts) + ".")

        joined_sentences = "\n".join(sentences)

        if joined_sentences:
            return f"[TABLE_START]\n{joined_sentences}\n[TABLE_END]"

        return ""


class TableRenderer:
    def __init__(self, restructurer: TableRestructurer):
        self._restructurer = restructurer

    def render(self, table_item: Any) -> str:
        return self._restructurer.restructure(table_item)