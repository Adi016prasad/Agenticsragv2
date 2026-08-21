from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import os
from table_html_parser import parse_complex_html_table  # <<< CHANGED: fixed import, points to real module now
from llama_cloud import LlamaCloud
from dotenv import load_dotenv
import json
from contextAwareChunking import DocumentChunker

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================================
# Domain objects — plain data, no behavior beyond structure
# ============================================================================

@dataclass
class UploadResult:
    file_path: Path
    success: bool
    file_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ImageBlock:
    filename: str
    presigned_url: str
    bbox_y: float
    bbox_x: float


@dataclass
class PageResult:
    page_number: int
    markdown: str  # final rendered markdown, tables cleaned, images placed by position


@dataclass
class ParsedDocument:
    file_path: Path
    job_id: str
    pages: List[PageResult] = field(default_factory=list)
    raw_markdown_pages: List[str] = field(default_factory=list)

    @property
    def full_markdown(self) -> str:
        return "\n\n".join(p.markdown for p in self.pages)

    @property
    def raw_markdown(self) -> str:
        return "\n\n".join(self.raw_markdown_pages)


# ============================================================================
# 1. Upload — single responsibility: talk to the upload API, nothing else
# ============================================================================

class FileUploader(ABC):
    @abstractmethod
    def upload(self, file_path: Path) -> UploadResult:
        pass


class LlamaCloudFileUploader(FileUploader):
    def __init__(self, client: LlamaCloud):
        self._client = client

    def upload(self, file_path: Path) -> UploadResult:
        if not file_path.exists():
            return UploadResult(file_path, success=False, error="File not found on disk")

        try:
            file = self._client.files.create(file=str(file_path), purpose="parse")
            logger.info("Uploaded %s -> file_id=%s", file_path.name, file.id)
            return UploadResult(file_path, success=True, file_id=file.id)
        except Exception as e:
            logger.exception("Upload failed for %s", file_path)
            return UploadResult(file_path, success=False, error=str(e))


class BatchFileUploader:
    """Handles single OR multiple files uniformly — a single file is just a batch of one."""

    def __init__(self, uploader: FileUploader):
        self._uploader = uploader

    def upload_all(self, file_paths: List[Path]) -> List[UploadResult]:
        return [self._uploader.upload(fp) for fp in file_paths]


# ============================================================================
# 2. Parse — single responsibility: submit a parse job for an uploaded file_id
# ============================================================================

class ParseClient(ABC):
    @abstractmethod
    def parse(self, file_id: str) -> Any:
        pass


class LlamaParseClient(ParseClient):
    def __init__(self, client: LlamaCloud, tier: str = "cost_effective"):
        self._client = client
        self._tier = tier

    def parse(self, file_id: str) -> Any:
        return self._client.parsing.parse(
            file_id=file_id,
            tier=self._tier,
            version="latest",
            output_options={"images_to_save": ["embedded"]},  # embedded only, no screenshots
            expand=["markdown", "items", "images_content_metadata"],
        )


class ParseJobValidator:
    @staticmethod
    def ensure_completed(result) -> None:
        status = result.job.status
        if status != "COMPLETED":
            raise RuntimeError(
                f"Parse job {result.job.id} failed: status={status} error={result.job.error_message}"
            )


# ============================================================================
# 3. Table inspection — kept for logging/QA visibility only.
# No longer used to GATE whether restructuring happens (see TableRenderer below) —
# HtmlTableRestructurer resolves spans correctly regardless of parse_concerns.
# ============================================================================

class TableInspector:
    @staticmethod
    def page_has_tables(page_items: List[Any]) -> bool:
        return any(getattr(item, "type", None) == "table" for item in page_items)

    @staticmethod
    def table_has_concerns(table_item: Any) -> bool:
        return bool(getattr(table_item, "parse_concerns", None))


# ============================================================================
# 4. Table restructuring — single responsibility: clean up a table's markup
# ============================================================================

class TableRestructurer(ABC):
    @abstractmethod
    def restructure(self, table_item: Any) -> str:
        pass


# <<< CHANGED: SentenceTableRestructurer (rows-based, forward-fill) REMOVED —
# it silently dropped data whenever a HEADER had a colspan (e.g. "GSV Factor"
# spanning "Single Pay" / "Other than Single Pay"), since it only forward-filled
# a single column and had no concept of multi-level headers or column-spans.
# Replaced by HtmlTableRestructurer below, which works off the real HTML
# rowspan/colspan attributes via parse_complex_html_table — the ground truth.

class HtmlTableRestructurer(TableRestructurer):
    """Uses the real HTML rowspan/colspan attributes (via parse_complex_html_table)
    to correctly resolve merged cells across BOTH rows and columns, including
    multi-level headers. No |, no ---, and no silently dropped columns."""

    def restructure(self, table_item: Any) -> str:
        html = getattr(table_item, "html", None)
        if not html:
            return getattr(table_item, "md", "")  # fallback if html missing

        rows = parse_complex_html_table(html)
        if not rows:
            return getattr(table_item, "md", "")

        sentences = []
        for row in rows:
            parts = [f"{header}: {value}" for header, value in row.items() if header and value]
            if parts:
                sentences.append("; ".join(parts) + ".")

        return "\n".join(sentences)


class TableRenderer:
    """Always delegates to the injected TableRestructurer — the parse_concerns
    gate was removed since HtmlTableRestructurer resolves spans correctly
    whether or not LlamaParse flagged concerns on the table."""

    def __init__(self, restructurer: TableRestructurer):
        self._restructurer = restructurer

    def render(self, table_item: Any) -> str:
        # <<< CHANGED: was `if TableInspector.table_has_concerns(...): restructure else: raw md`
        # now always restructures via the injected strategy
        return self._restructurer.restructure(table_item)


# ============================================================================
# 5. Image handling — single responsibility: filter + position embedded images
# ============================================================================

class EmbeddedImageFilter:
    @staticmethod
    def filter(images_content_metadata: Any) -> List[ImageBlock]:
        if not images_content_metadata:
            return []

        return [
            ImageBlock(
                filename=img.filename,
                presigned_url=img.presigned_url,
                bbox_x=img.bbox.x,
                bbox_y=img.bbox.y,
            )
            for img in images_content_metadata.images
            if img.category == os.getenv("IMAGETYPE")
        ]


# ============================================================================
# Page assembly — single responsibility: order text/table/image blocks by
# their vertical position (bbox.y) and render final per-page markdown
# NOTE: unchanged — it just calls table_renderer.render(item), so the
# HtmlTableRestructurer swap needed zero changes here.
# ============================================================================

class PageAssembler:
    def __init__(self, table_renderer: TableRenderer):
        self._table_renderer = table_renderer

    def assemble(
        self,
        page_number: int,
        page_items: List[Any],
        page_images: List[ImageBlock],
    ) -> PageResult:

        blocks = []  # list of (y_position, markdown_str)

        for item in page_items:
            y = item.bbox[0].y if getattr(item, "bbox", None) else 0
            if item.type == "table":
                blocks.append((y, self._table_renderer.render(item)))
            else:
                blocks.append((y, item.md))

        if os.getenv("ANALYZE", "false").lower() == "true":
            print(os.getenv("ANALYZE"))
            for img in page_images:
                # Placeholder carries the link inline — a later step finds this
                # marker, runs LLM vision analysis, and str_replaces it with the
                # real analysis text, at the exact position the image occupied.
                placeholder = f"![IMAGE_TO_ANALYZE]({img.presigned_url})"
                blocks.append((img.bbox_y, placeholder))

        blocks.sort(key=lambda b: b[0])
        page_markdown = "\n\n".join(b[1] for b in blocks)

        return PageResult(page_number=page_number, markdown=page_markdown)


# ============================================================================
# Orchestrator — wires everything together. Depends on abstractions (DIP),
# not concrete classes, so every collaborator is swappable/mockable.
# NOTE: unchanged — no edits needed here at all.
# ============================================================================

class DocumentParsingPipeline:
    def __init__(
        self,
        uploader: BatchFileUploader,
        parse_client: ParseClient,
        validator: ParseJobValidator,
        page_assembler: PageAssembler,
    ):
        self._uploader = uploader
        self._parse_client = parse_client
        self._validator = validator
        self._page_assembler = page_assembler

    def process(self, file_paths: List[Path]) -> List[ParsedDocument] | str:
        upload_results = self._uploader.upload_all(file_paths)

        documents: List[ParsedDocument] = []

        for upload in upload_results:
            if not upload.success:
                logger.error("Skipping %s — upload failed: %s", upload.file_path, upload.error)
                continue

            result = self._parse_client.parse(upload.file_id)
            self._validator.ensure_completed(result)

            images_by_page: Dict[int, List[ImageBlock]] = {}
            all_images = EmbeddedImageFilter.filter(
                getattr(result, "images_content_metadata", None)
            )
            # NOTE: page-level image association assumes your SDK's image
            # entries carry a page reference; if not present, associate via
            # matching filename convention (e.g. "img_pN_*") or via each
            # page's own item list if images appear there too.
            for img in all_images:
                page_num = self._infer_page_number(img.filename)
                images_by_page.setdefault(page_num, []).append(img)

            pages = []
            raw_pages = []
            for items_page, md_page in zip(result.items.pages, result.markdown.pages):
                if not items_page.items and not md_page.success:
                    continue

                raw_pages.append(md_page.markdown)

                page_number = items_page.page_number
                page_result = self._page_assembler.assemble(
                    page_number=page_number,
                    page_items=items_page.items,
                    page_images=images_by_page.get(page_number, []),
                )
                pages.append(page_result)

            documents.append(
                ParsedDocument(
                    file_path=upload.file_path,
                    job_id=result.job.id,
                    pages=pages,
                    raw_markdown_pages=raw_pages,
                )
            )

        return documents

    @staticmethod
    def _infer_page_number(filename: str) -> int:
        # e.g. "img_p1_1.jpg" -> page 1
        import re
        match = re.search(r"_p(\d+)_", filename)
        return int(match.group(1)) if match else 0


# ============================================================================
# Composition root — build the pipeline (this is the only place concrete
# classes get instantiated together)
# ============================================================================

def build_pipeline() -> DocumentParsingPipeline:
    api_key = os.getenv("API_KEY_LLAMAPARSE", "")
    client = LlamaCloud(api_key=api_key)

    uploader = BatchFileUploader(LlamaCloudFileUploader(client))
    parse_client = LlamaParseClient(client, tier="cost_effective")
    validator = ParseJobValidator()
    table_renderer = TableRenderer(HtmlTableRestructurer())  # <<< CHANGED: was SentenceTableRestructurer()
    page_assembler = PageAssembler(table_renderer)

    return DocumentParsingPipeline(uploader, parse_client, validator, page_assembler)


# ============================================================================
# Usage — works identically for one file or many
# ============================================================================

if __name__ == "__main__":
    pipeline = build_pipeline()
    chunker = DocumentChunker()
    try:
        docs = pipeline.process([Path("testingllamaparseoriginal.pdf")])

        for doc in docs:
            output_path = doc.file_path.with_suffix(".md")
            output_path.write_text(doc.full_markdown, encoding="utf-8")
            print(f"Written: {output_path}")

            raw_output_path = doc.file_path.with_name(doc.file_path.stem + "_raw.md")
            raw_output_path.write_text(doc.raw_markdown, encoding="utf-8")
            print(f"Written: {raw_output_path}")

            # NEW: chunk + write
            chunks = chunker.chunk(doc.full_markdown)
            chunks_output_path = doc.file_path.with_name(doc.file_path.stem + "_chunks.json")


            # Recommended standard approach
            chunks_data = [
                {
                    "chunk_type": c.chunk_type,
                    "heading_path": c.heading_path,
                    "text": c.contextual_text,
                }
                for c in chunks
            ]

            with chunks_output_path.open("w", encoding="utf-8") as f:
                json.dump(chunks_data, f, indent=2, ensure_ascii=False)

            print(f"Written: {chunks_output_path}")

            # chunks_output_path.write_text(
            #     json.dumps(
            #         [{"chunk_type": c.chunk_type, "heading_path": c.heading_path, "text": c.contextual_text} for c in chunks],
            #         indent = 2, ensure_ascii=False,
            #     ),
            #     encoding = "utf-8",
            # )
            # print(f"Written: {chunks_output_path}")

    except Exception as e:
        raise e