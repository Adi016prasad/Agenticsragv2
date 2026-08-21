import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .contextAwareChunking import Chunk, DocumentChunker

# ============================================================================
# Domain objects
# ============================================================================


@dataclass
class ChildChunk:
    chunk_id: str
    parent_id: str
    parent_text: str
    text: str
    chunk_type: str  # "text" | "list" | "table"
    heading_path: List[str]

    @property
    def contextual_text(self) -> str:
        if not self.heading_path:
            return self.text
        breadcrumb = " > ".join(self.heading_path)
        return f"[Context: {breadcrumb}]\n{self.text}"


@dataclass
class ParentChunk:
    parent_id: str
    heading_path: List[str]
    text: str
    children: List[ChildChunk] = field(default_factory=list)

    @property
    def contextual_text(self) -> str:
        if not self.heading_path:
            return self.text
        breadcrumb = " > ".join(self.heading_path)
        return f"[Context: {breadcrumb}]\n{self.text}"


# ============================================================================
# Hierarchical Chunker
# ============================================================================


class HierarchicalChunker:
    """
    Produces ParentChunk objects, each holding the full parent text plus
    the ChildChunk objects that were derived from it.

    Args:
        parent_heading_level: headings at or above this level (e.g. 2 ->
            H1 and H2) start a new parent section.
        max_parent_chars: soft cap on parent chunk size. If a heading
            section is bigger than this, it gets split further at safe
            (non-table) line boundaries.
        child_overlap_sentences / max_child_chars: passed straight through
            to the underlying DocumentChunker for child-level splitting.
    """

    def __init__(
        self,
        parent_heading_level: int = 2,
        max_parent_chars: int = 6000,
        child_overlap_sentences: int = 4,
        max_child_chars: int = 1500,
    ):
        self._parent_heading_level = parent_heading_level
        self._max_parent_chars = max_parent_chars
        self._child_chunker = DocumentChunker(
            overlap_sentences=child_overlap_sentences,
            max_chunk_chars=max_child_chars,
        )

    def chunk(self, text: str) -> List[ParentChunk]:
        sections = self._split_into_heading_sections(text)

        parent_chunks: List[ParentChunk] = []
        parent_counter = 0

        for heading_path, section_text in sections:
            # 1. ADD ENUMERATE HERE
            for piece_idx, piece in enumerate(self._split_section_if_too_long(section_text)):
                piece = piece.strip("\n")
                if not piece.strip():
                    continue

                # 2. ADD THESE 3 LINES HERE (Re-injects heading for split pieces)
                if piece_idx > 0 and heading_path:
                    injected_heading = f"# {' > '.join(heading_path)}"
                    piece = f"{injected_heading}\n\n{piece}"

                parent_counter += 1
                parent_id = f"parent_{parent_counter:04d}"

                child_raw_chunks: List[Chunk] = self._child_chunker.chunk(piece)
                
                # The full parent text block representing this piece
                parent_text_for_this_piece = piece.strip()

                children: List[ChildChunk] = []
                for idx, c in enumerate(child_raw_chunks):
                    
                    # FIX APPLIED: We no longer restrict tables/lists to only 
                    # holding their own text. ALL children now inherit the FULL
                    # parent piece they were extracted from.
                    
                    children.append(
                        ChildChunk(
                            chunk_id=f"{parent_id}_child_{idx + 1:03d}",
                            parent_id=parent_id,
                            parent_text=parent_text_for_this_piece,
                            text=c.text,
                            chunk_type=c.chunk_type,
                            heading_path=c.heading_path or heading_path,
                        )
                    )

                parent_chunks.append(
                    ParentChunk(
                        parent_id=parent_id,
                        heading_path=heading_path,
                        text=parent_text_for_this_piece,
                        children=children,
                    )
                )

        return parent_chunks

    # ------------------------------------------------------------------
    # Step 1: split into heading-bounded parent sections
    # ------------------------------------------------------------------

    def _split_into_heading_sections(
        self, text: str
    ) -> List[Tuple[List[str], str]]:
        lines = text.split("\n")
        heading_stack: List[Tuple[int, str]] = []
        sections: List[Tuple[List[str], str]] = []
        current_lines: List[str] = []
        current_path: List[str] = []

        def flush():
            nonlocal current_lines
            content = "\n".join(current_lines).strip("\n")
            if content.strip():
                sections.append((list(current_path), content))
            current_lines = []

        for line in lines:
            heading_match = DocumentChunker.HEADING_RE.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                if level <= self._parent_heading_level:
                    # New parent boundary — close out the previous section.
                    flush()
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, title))
                    current_path = [h[1] for h in heading_stack]
                    current_lines.append(line)
                    continue

            current_lines.append(line)

        flush()

        if not sections:
            sections = [([], text)]

        return sections

    # ------------------------------------------------------------------
    # Step 2: if a section is still too big, split at SAFE boundaries only
    # (never inside a [TABLE_START]...[TABLE_END] block)
    # ------------------------------------------------------------------

    def _split_section_if_too_long(self, text: str) -> List[str]:
        if len(text) <= self._max_parent_chars:
            return [text]

        lines = text.split("\n")
        pieces: List[str] = []
        current_lines: List[str] = []
        current_len = 0
        in_table = False
        safe_break_idx = None  # index into current_lines safe to cut at

        for line in lines:
            stripped = line.strip()

            if stripped == DocumentChunker.TABLE_START_MARKER:
                in_table = True

            current_lines.append(line)
            current_len += len(line) + 1

            if stripped == DocumentChunker.TABLE_END_MARKER:
                in_table = False

            if not in_table and stripped == "":
                safe_break_idx = len(current_lines)

            if current_len >= self._max_parent_chars and not in_table:
                if safe_break_idx is not None and 0 < safe_break_idx < len(
                    current_lines
                ):
                    piece = "\n".join(current_lines[:safe_break_idx])
                    remainder = current_lines[safe_break_idx:]
                else:
                    # No safe boundary found yet (e.g. still inside one
                    # long paragraph) — keep growing until we find one,
                    # rather than risk cutting a table/list in half.
                    continue

                if piece.strip():
                    pieces.append(piece)
                current_lines = remainder
                current_len = sum(len(l) + 1 for l in current_lines)
                safe_break_idx = None

        if current_lines:
            remainder_text = "\n".join(current_lines)
            if remainder_text.strip():
                pieces.append(remainder_text)

        return pieces if pieces else [text]

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    @staticmethod
    def to_export_dicts(
        parent_chunks: List[ParentChunk],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Returns (child_dicts, parent_dicts):
          - child_dicts: what you embed / index in the vector DB.
          - parent_dicts: a lookup table (parent_id -> full context) you
            fetch from once a child chunk is retrieved.
        """
        parent_dicts = [
            {
                "parent_id": p.parent_id,
                "heading_path": p.heading_path,
                "text": p.contextual_text,
            }
            for p in parent_chunks
        ]

        child_dicts = [
            {
                "chunk_id": c.chunk_id,
                "chunk_type": c.chunk_type,
                "heading_path": c.heading_path,
                "text": c.contextual_text,
                "parent_text": c.parent_text,
            }
            for p in parent_chunks
            for c in p.children
        ]

        return child_dicts, parent_dicts


def build_hierarchical_chunker(
    parent_heading_level: int = 2,
    max_parent_chars: int = 6000,
    child_overlap_sentences: int = 4,
    max_child_chars: int = 1500,
) -> HierarchicalChunker:
    return HierarchicalChunker(
        parent_heading_level=parent_heading_level,
        max_parent_chars=max_parent_chars,
        child_overlap_sentences=child_overlap_sentences,
        max_child_chars=max_child_chars,
    )


if __name__ == "__main__":
    import json
    from pathlib import Path

    sample_path = Path("test1/HDFC-SAMPOORNA-JEEVAN-BROCHURE.md")
    if sample_path.exists():
        text = sample_path.read_text(encoding="utf-8")
        hchunker = build_hierarchical_chunker()
        parents = hchunker.chunk(text)
        child_dicts, _parent_dicts = HierarchicalChunker.to_export_dicts(parents)

        Path("test1/newhierarchical_chunks.json").write_text(
            json.dumps(child_dicts, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print(f"Chunks written: {len(child_dicts)} -> newhierarchical_chunks.json")