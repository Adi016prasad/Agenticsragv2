import re
from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    text: str
    chunk_type: str  # "text" | "list" | "table"
    heading_path: List[str]  # e.g., ["Eligibility Criteria", "Age Criteria"]

    @property
    def contextual_text(self) -> str:
        """Prepends the heading breadcrumb so the chunk is self-contained."""
        if not self.heading_path:
            return self.text
        breadcrumb = " > ".join(self.heading_path)
        return f"[Context: {breadcrumb}]\n{self.text}"


class DocumentChunker:
    """
    Universal markdown-aware chunker.
    Rules:
      - Headings define chunk boundaries AND hierarchical context (breadcrumb).
      - Content wrapped in [TABLE_START]...[TABLE_END] is ALWAYS one atomic table chunk.
      - Bulleted and numbered lists are ALWAYS one atomic list chunk.
      - Lists stop immediately at headings, table markers, or two blank lines.
      - Tables bypass character limits and sliding-window overlap.
    """

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
    LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+\.)\s+")

    TABLE_START_MARKER = "[TABLE_START]"
    TABLE_END_MARKER = "[TABLE_END]"

    def __init__(
        self, overlap_sentences: int = 2, max_chunk_chars: int = 1500
    ):
        self._overlap_sentences = overlap_sentences
        self._max_chunk_chars = max_chunk_chars

    def chunk(self, text: str) -> List[Chunk]:
        lines = text.split("\n")
        raw_chunks: List[Chunk] = []
        heading_stack: List[tuple] = []  # (level, title)
        buffer: List[str] = []
        i = 0

        def current_path() -> List[str]:
            return [h[1] for h in heading_stack]

        def flush_text():
            nonlocal buffer
            text_content = "\n".join(buffer).strip()
            buffer = []
            if not text_content:
                return
            for piece in self._split_if_too_long(text_content):
                raw_chunks.append(
                    Chunk(
                        text=piece,
                        chunk_type="text",
                        heading_path=current_path(),
                    )
                )

        while i < len(lines):
            line = lines[i]

            # ---- Table Chunking: Atomic consumption between markers ----
            if line.strip() == self.TABLE_START_MARKER:
                flush_text()
                table_lines = []
                i += 1
                while (
                    i < len(lines)
                    and lines[i].strip() != self.TABLE_END_MARKER
                ):
                    table_lines.append(lines[i])
                    i += 1

                if i < len(lines) and lines[i].strip() == self.TABLE_END_MARKER:
                    i += 1  # Skip past the closing marker

                table_text = "\n".join(table_lines).strip()
                if table_text:
                    raw_chunks.append(
                        Chunk(
                            text=table_text,
                            chunk_type="table",
                            heading_path=current_path(),
                        )
                    )
                continue

            # ---- Heading Chunking: Preserves hierarchy and updates stack ----
            heading_match = self.HEADING_RE.match(line)
            if heading_match:
                flush_text()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))

                # Fixed Point 3: Line is NOT appended to buffer here to prevent heading duplication
                i += 1
                continue

            # ---- List Chunking: Atomic list block, stops at table/heading ----
            if self.LIST_ITEM_RE.match(line):
                flush_text()
                list_lines = [line]
                i += 1
                blank_run = 0
                while i < len(lines):
                    nxt = lines[i]

                    # Stop conditions to prevent swallowing tables or headings
                    if (
                        self.HEADING_RE.match(nxt)
                        or nxt.strip() == self.TABLE_START_MARKER
                    ):
                        break

                    if nxt.strip() == "":
                        blank_run += 1
                        if blank_run >= 2:  # Double blank line signals end of list
                            break
                        list_lines.append(nxt)
                        i += 1
                        continue

                    blank_run = 0
                    list_lines.append(nxt)
                    i += 1

                raw_chunks.append(
                    Chunk(
                        text="\n".join(list_lines).strip(),
                        chunk_type="list",
                        heading_path=current_path(),
                    )
                )
                continue

            # ---- Plain Paragraph Content ----
            if line.strip() == "":
                has_text = any(
                    not self.HEADING_RE.match(l) and l.strip() for l in buffer
                )
                if has_text:
                    flush_text()
                else:
                    buffer.append(line)
            else:
                buffer.append(line)

            i += 1

        flush_text()
        return self._apply_overlap(raw_chunks)

    def _split_if_too_long(self, text: str) -> List[str]:
        """Safety split for TEXT blocks exceeding max_chunk_chars."""
        if len(text) <= self._max_chunk_chars:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        pieces, current = [], ""
        for sentence in sentences:
            if len(current) + len(sentence) > self._max_chunk_chars and current:
                pieces.append(current.strip())
                current = sentence
            else:
                current += (" " if current else "") + sentence

        if current:
            pieces.append(current.strip())
        return pieces

    def _apply_overlap(self, chunks: List[Chunk]) -> List[Chunk]:
        """Applies sliding window overlap only between consecutive TEXT chunks."""
        result: List[Chunk] = []
        for idx, chunk in enumerate(chunks):
            # Tables and Lists are hard boundaries (never receive/give overlap)
            if chunk.chunk_type != "text":
                result.append(chunk)
                continue

            prev = chunks[idx - 1] if idx > 0 else None
            if prev and prev.chunk_type == "text":
                overlap = self._last_n_sentences(
                    prev.text, self._overlap_sentences
                )
                merged = (
                    f"{overlap}\n{chunk.text}".strip()
                    if overlap
                    else chunk.text
                )
                result.append(
                    Chunk(
                        text=merged,
                        chunk_type="text",
                        heading_path=chunk.heading_path,
                    )
                )
            else:
                result.append(chunk)
        return result

    @staticmethod
    def _last_n_sentences(text: str, n: int) -> str:
        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()
        ]
        return " ".join(sentences[-n:]) if sentences else ""