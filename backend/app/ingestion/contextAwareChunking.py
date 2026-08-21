# import re
# from dataclasses import dataclass
# from typing import List


# @dataclass
# class Chunk:
#     text: str
#     chunk_type: str          # "text" | "table" | "code" | "list"
#     heading_path: List[str]  # breadcrumb, e.g. ["Eligibility Criteria", "Age Criteria"]

#     @property
#     def contextual_text(self) -> str:
#         """Prepends the heading breadcrumb so the chunk is self-contained —
#         a reader (or embedding model) doesn't need surrounding chunks to know
#         what section this content belongs to."""
#         if not self.heading_path:
#             return self.text
#         breadcrumb = " > ".join(self.heading_path)
#         return f"[Context: {breadcrumb}]\n{self.text}"


# class MarkdownLayoutChunker:
#     """
#     Universal markdown-aware chunker.
#     Rules:
#       - Headings define chunk boundaries AND hierarchical context (breadcrumb)
#         attached to every chunk under them. A heading is NEVER separated from
#         the content that follows it — flush happens before the heading is
#         added to the next chunk's buffer, not after.
#       - Tables (pipe rows + --- separator) are ALWAYS one atomic chunk.
#       - Fenced code blocks (```...```) are ALWAYS atomic.
#       - Lists (bulleted/numbered) are ALWAYS one atomic chunk — a run of
#         consecutive list-item lines (including wrapped continuation lines)
#         is captured as a single unit, never split mid-list. Because chunking
#         runs over the FULL joined document text (all pages concatenated),
#         a list that spans a page break is naturally kept together too —
#         there's no page-boundary cut inside this function.
#       - Everything else (paragraphs) groups into text chunks between
#         boundaries.
#       - Overlap applies only between consecutive TEXT chunks — table, code,
#         and list chunks are hard walls: they neither give nor receive overlap.
#     """

#     HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)')
#     TABLE_ROW_RE = re.compile(r'^\s*\|.*\|\s*$')
#     TABLE_SEP_RE = re.compile(r'^\s*\|?[\s:|-]+\|[\s:|-]*\|?\s*$')
#     CODE_FENCE_RE = re.compile(r'^\s*```')
#     LIST_ITEM_RE = re.compile(r'^\s*([-*+]|\d+\.)\s+')

#     def __init__(self, overlap_sentences: int = 2, max_chunk_chars: int = 1500):
#         self._overlap_sentences = overlap_sentences
#         self._max_chunk_chars = max_chunk_chars

#     def chunk(self, markdown_text: str) -> List[Chunk]:
#         lines = markdown_text.split("\n")
#         raw_chunks: List[Chunk] = []
#         heading_stack: List[tuple] = []   # (level, text)
#         buffer: List[str] = []
#         i = 0

#         def current_path() -> List[str]:
#             return [h[1] for h in heading_stack]

#         def flush_text():
#             nonlocal buffer
#             text = "\n".join(buffer).strip()
#             buffer = []
#             if not text:
#                 return
#             for piece in self._split_if_too_long(text):
#                 raw_chunks.append(Chunk(text=piece, chunk_type="text", heading_path=current_path()))

#         while i < len(lines):
#             line = lines[i]

#             # ---- Heading: closes current section, updates breadcrumb ----
#             # Flushing here (before appending the heading) guarantees the
#             # heading is never split away from the paragraph that follows it —
#             # both land in the SAME next chunk.
#             heading_match = self.HEADING_RE.match(line)
#             if heading_match:
#                 flush_text()
#                 level = len(heading_match.group(1))
#                 title = heading_match.group(2).strip()
#                 while heading_stack and heading_stack[-1][0] >= level:
#                     heading_stack.pop()
#                 heading_stack.append((level, title))
#                 buffer.append(line)
#                 i += 1
#                 continue

#             # ---- Fenced code block: atomic, consume until closing fence ----
#             if self.CODE_FENCE_RE.match(line):
#                 flush_text()
#                 code_lines = [line]
#                 i += 1
#                 while i < len(lines) and not self.CODE_FENCE_RE.match(lines[i]):
#                     code_lines.append(lines[i])
#                     i += 1
#                 if i < len(lines):
#                     code_lines.append(lines[i])
#                     i += 1
#                 raw_chunks.append(Chunk(
#                     text="\n".join(code_lines), chunk_type="code", heading_path=current_path()
#                 ))
#                 continue

#             # ---- Table: atomic, consume all contiguous pipe rows ----
#             if self.TABLE_ROW_RE.match(line):
#                 flush_text()
#                 table_lines = [line]
#                 i += 1
#                 while i < len(lines) and (self.TABLE_ROW_RE.match(lines[i]) or self.TABLE_SEP_RE.match(lines[i])):
#                     table_lines.append(lines[i])
#                     i += 1
#                 raw_chunks.append(Chunk(
#                     text="\n".join(table_lines), chunk_type="table", heading_path=current_path()
#                 ))
#                 continue

#             # ---- List: atomic, consume the whole list including wrapped ----
#             # continuation lines and blank lines between items, stopping only
#             # at a heading, table, code fence, or two consecutive blank lines
#             # (a genuine end-of-list signal).
#             if self.LIST_ITEM_RE.match(line):
#                 flush_text()
#                 list_lines = [line]
#                 i += 1
#                 blank_run = 0
#                 while i < len(lines):
#                     nxt = lines[i]
#                     if self.HEADING_RE.match(nxt) or self.CODE_FENCE_RE.match(nxt) or self.TABLE_ROW_RE.match(nxt):
#                         break
#                     if nxt.strip() == "":
#                         blank_run += 1
#                         if blank_run >= 2:
#                             break
#                         list_lines.append(nxt)
#                         i += 1
#                         continue
#                     blank_run = 0
#                     list_lines.append(nxt)
#                     i += 1
#                 raw_chunks.append(Chunk(
#                     text="\n".join(list_lines).strip(), chunk_type="list", heading_path=current_path()
#                 ))
#                 continue

#             # ---- Plain content line ----
#             buffer.append(line)
#             i += 1

#         flush_text()
#         return self._apply_overlap(raw_chunks)

#     def _split_if_too_long(self, text: str) -> List[str]:
#         """Only splits a TEXT block, and only at sentence boundaries, and only
#         if it exceeds max_chunk_chars — a soft safety cap, not the primary
#         chunking mechanism. Tables/code/lists are never touched by this."""
#         if len(text) <= self._max_chunk_chars:
#             return [text]

#         sentences = re.split(r'(?<=[.!?])\s+', text)
#         pieces, current = [], ""
#         for sentence in sentences:
#             if len(current) + len(sentence) > self._max_chunk_chars and current:
#                 pieces.append(current.strip())
#                 current = sentence
#             else:
#                 current += (" " if current else "") + sentence
#         if current:
#             pieces.append(current.strip())
#         return pieces

#     def _apply_overlap(self, chunks: List[Chunk]) -> List[Chunk]:
#         result: List[Chunk] = []
#         for idx, chunk in enumerate(chunks):
#             if chunk.chunk_type != "text":
#                 result.append(chunk)  # table/code/list pass through untouched — hard walls
#                 continue

#             prev = chunks[idx - 1] if idx > 0 else None
#             if prev and prev.chunk_type == "text":
#                 overlap = self._last_n_sentences(prev.text, self._overlap_sentences)
#                 merged = f"{overlap}\n{chunk.text}".strip() if overlap else chunk.text
#                 result.append(Chunk(text=merged, chunk_type="text", heading_path=chunk.heading_path))
#             else:
#                 result.append(chunk)
#         return result

#     @staticmethod
#     def _last_n_sentences(text: str, n: int) -> str:
#         sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
#         return " ".join(sentences[-n:]) if sentences else ""
import re
from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    text: str
    chunk_type: str          # "text" | "list"
    heading_path: List[str]  # breadcrumb, e.g. ["Eligibility Criteria", "Age Criteria"]

    @property
    def contextual_text(self) -> str:
        """Prepends the heading breadcrumb so the chunk is self-contained."""
        if not self.heading_path:
            return self.text
        breadcrumb = " > ".join(self.heading_path)
        return f"[Context: {breadcrumb}]\n{self.text}"


class DocumentChunker:
    """
    Chunker optimized for text, lists, and headings, omitting pipe/code boundaries.
    """

    HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)')
    LIST_ITEM_RE = re.compile(r'^\s*([-*+]|\d+\.)\s+')

    def __init__(self, overlap_sentences: int = 2, max_chunk_chars: int = 1500):
        self._overlap_sentences = overlap_sentences
        self._max_chunk_chars = max_chunk_chars

    def chunk(self, text: str) -> List[Chunk]:
        lines = text.split("\n")
        raw_chunks: List[Chunk] = []
        heading_stack: List[tuple] = []   # (level, text)
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
                raw_chunks.append(Chunk(text=piece, chunk_type="text", heading_path=current_path()))

        while i < len(lines):
            line = lines[i]

            # ---- Heading: closes current section, updates breadcrumb ----
            heading_match = self.HEADING_RE.match(line)
            if heading_match:
                flush_text()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Update breadcrumb stack based on heading level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                
                # Buffer the heading so it attaches to the text that follows
                buffer.append(line)
                i += 1
                continue

            # ---- List: atomic, consume the whole list including wrapped ----
            if self.LIST_ITEM_RE.match(line):
                flush_text()
                list_lines = [line]
                i += 1
                blank_run = 0
                while i < len(lines):
                    nxt = lines[i]
                    if self.HEADING_RE.match(nxt):
                        break
                    
                    if nxt.strip() == "":
                        blank_run += 1
                        if blank_run >= 2: # Two blank lines break a list
                            break
                        list_lines.append(nxt)
                        i += 1
                        continue
                    
                    blank_run = 0
                    list_lines.append(nxt)
                    i += 1
                
                raw_chunks.append(Chunk(
                    text="\n".join(list_lines).strip(), 
                    chunk_type="list", 
                    heading_path=current_path()
                ))
                continue

            # ---- Plain content / Sentence-based Tables ----
            # If we hit an empty line, flush the buffer ONLY IF it contains actual text.
            # This ensures headings aren't flushed prematurely if separated by a blank line.
            if line.strip() == "":
                has_text = any(not self.HEADING_RE.match(l) and l.strip() for l in buffer)
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
        """Soft safety cap: splits a TEXT block at sentence boundaries if it exceeds max_chunk_chars."""
        if len(text) <= self._max_chunk_chars:
            return [text]

        sentences = re.split(r'(?<=[.!?])\s+', text)
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
        """Applies sliding window overlap only between consecutive text chunks."""
        result: List[Chunk] = []
        for idx, chunk in enumerate(chunks):
            if chunk.chunk_type != "text":
                result.append(chunk)  # Lists pass through untouched
                continue

            prev = chunks[idx - 1] if idx > 0 else None
            if prev and prev.chunk_type == "text":
                overlap = self._last_n_sentences(prev.text, self._overlap_sentences)
                merged = f"{overlap}\n{chunk.text}".strip() if overlap else chunk.text
                result.append(Chunk(text=merged, chunk_type="text", heading_path=chunk.heading_path))
            else:
                result.append(chunk)
        return result

    @staticmethod
    def _last_n_sentences(text: str, n: int) -> str:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        return " ".join(sentences[-n:]) if sentences else ""