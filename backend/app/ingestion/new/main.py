import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from llama_cloud import LlamaCloud

from .contextAwareChunking import DocumentChunker
from .hirarchicalChunker import build_hierarchical_chunker, HierarchicalChunker
from .table_restructurer import HtmlTableRestructurer, TableRenderer

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================================
# Dataclasses & Domain Contracts
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
    markdown: str


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
# Core Pipeline Services
# ============================================================================


class FileUploader:
    def __init__(self, client: LlamaCloud):
        self._client = client

    def upload(self, file_path: Path) -> UploadResult:
        if not file_path.exists():
            return UploadResult(
                file_path, success=False, error="File not found on disk"
            )

        try:
            file = self._client.files.create(
                file=str(file_path), purpose="parse"
            )
            logger.info("Uploaded %s -> file_id=%s", file_path.name, file.id)
            return UploadResult(file_path, success=True, file_id=file.id)
        except Exception as e:
            logger.exception("Upload failed for %s", file_path)
            return UploadResult(file_path, success=False, error=str(e))


class BatchFileUploader:
    def __init__(self, uploader: FileUploader):
        self._uploader = uploader

    def upload_all(self, file_paths: List[Path]) -> List[UploadResult]:
        return [self._uploader.upload(fp) for fp in file_paths]


class LlamaParseClient:
    def __init__(self, client: LlamaCloud, tier: str = "cost_effective"):
        self._client = client
        self._tier = tier

    def parse(self, file_id: str) -> Any:
        return self._client.parsing.parse(
            file_id=file_id,
            tier=self._tier,
            version="latest",
            output_options={"images_to_save": ["embedded"]},
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


class PageAssembler:
    def __init__(self, table_renderer: TableRenderer):
        self._table_renderer = table_renderer

    def assemble(
        self,
        page_number: int,
        page_items: List[Any],
        page_images: List[ImageBlock],
    ) -> PageResult:
        blocks = []

        for item in page_items:
            y = item.bbox[0].y if getattr(item, "bbox", None) else 0
            if item.type == "table":
                blocks.append((y, self._table_renderer.render(item)))
            else:
                blocks.append((y, item.md))

        if os.getenv("ANALYZE", "false").lower() == "true":
            for img in page_images:
                placeholder = f"![IMAGE_TO_ANALYZE]({img.presigned_url})"
                blocks.append((img.bbox_y, placeholder))

        blocks.sort(key=lambda b: b[0])
        page_markdown = "\n\n".join(b[1] for b in blocks)

        return PageResult(page_number=page_number, markdown=page_markdown)


class DocumentParsingPipeline:
    def __init__(
        self,
        uploader: BatchFileUploader,
        parse_client: LlamaParseClient,
        validator: ParseJobValidator,
        page_assembler: PageAssembler,
    ):
        self._uploader = uploader
        self._parse_client = parse_client
        self._validator = validator
        self._page_assembler = page_assembler

    def process(self, file_paths: List[Path]) -> List[ParsedDocument]:
        upload_results = self._uploader.upload_all(file_paths)
        documents: List[ParsedDocument] = []

        for upload in upload_results:
            if not upload.success:
                logger.error(
                    "Skipping %s — upload failed: %s",
                    upload.file_path,
                    upload.error,
                )
                continue

            result = self._parse_client.parse(upload.file_id)
            self._validator.ensure_completed(result)

            images_by_page: Dict[int, List[ImageBlock]] = {}
            all_images = EmbeddedImageFilter.filter(
                getattr(result, "images_content_metadata", None)
            )
            for img in all_images:
                page_num = self._infer_page_number(img.filename)
                images_by_page.setdefault(page_num, []).append(img)

            pages = []
            raw_pages = []
            for items_page, md_page in zip(
                result.items.pages, result.markdown.pages
            ):
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
        match = re.search(r"_p(\d+)_", filename)
        return int(match.group(1)) if match else 0


def build_pipeline() -> DocumentParsingPipeline:
    api_key = os.getenv("API_KEY_LLAMAPARSE", "")
    client = LlamaCloud(api_key=api_key)

    uploader = BatchFileUploader(FileUploader(client))
    parse_client = LlamaParseClient(client, tier="cost_effective")
    validator = ParseJobValidator()
    table_renderer = TableRenderer(HtmlTableRestructurer())
    page_assembler = PageAssembler(table_renderer)

    return DocumentParsingPipeline(
        uploader, parse_client, validator, page_assembler
    )


# ============================================================================
# Chunking Strategy Switch (env-var driven)
# ============================================================================

# Set CHUNKING_STRATEGY=hierarchical in your .env / environment to switch;
# anything else (or unset) falls back to the existing simple/flat chunker.
CHUNKING_STRATEGY = os.getenv("CHUNKING_STRATEGY", "simple").strip().lower()

def get_chunks_data(full_markdown: str) -> List[Dict[str, Any]]:
    """
    Dispatches to simple (flat) or hierarchical (parent/child) chunking
    based on CHUNKING_STRATEGY. Always returns a flat list of dicts ready
    for json.dump, so nothing downstream of this function needs to change
    regardless of which strategy ran.
    """
    if CHUNKING_STRATEGY == "hierarchical":
        hchunker = build_hierarchical_chunker(
            parent_heading_level=2,
            max_parent_chars=6000,
            child_overlap_sentences=4,
            max_child_chars=1500,
        )
        parents = hchunker.chunk(full_markdown)
        child_dicts, _parent_dicts = HierarchicalChunker.to_export_dicts(parents)
        return child_dicts

    chunker = DocumentChunker(overlap_sentences=4, max_chunk_chars=1500)
    chunks = chunker.chunk(full_markdown)
    return [
        {
            "chunk_type": c.chunk_type,
            "heading_path": c.heading_path,
            "text": c.contextual_text,
        }
        for c in chunks
    ]

# ============================================================================
# Execution Entry Point
# ============================================================================

def process_single_file(pipeline: DocumentParsingPipeline, file_path: Path):
    docs = pipeline.process([file_path])
    return docs

# def initiateChunking(docs):
#     try:
#         for doc in docs:
#             # # 1. Save Transformed Markdown (with [TABLE_START] and [TABLE_END])
#             # output_path = doc.file_path.with_suffix(".md")
#             # output_path.write_text(doc.full_markdown, encoding="utf-8")
#             # print(f"Written: {output_path}")

#             # # 2. Save Raw LlamaParse Output
#             # raw_output_path = doc.file_path.with_name(
#             #     doc.file_path.stem + "_raw.md"
#             # )
#             # raw_output_path.write_text(doc.raw_markdown, encoding = "utf-8")
#             # print(f"Written: {raw_output_path}")

#             # 3. Chunk Transformed Markdown (simple or hierarchical) and output JSON
#             chunks_data = get_chunks_data(doc.full_markdown)
#             chunks_output_path = doc.file_path.with_name(
#                 doc.file_path.stem + "_chunks.json"
#             )

#             with chunks_output_path.open("w", encoding = "utf-8") as f:
#                 json.dump(chunks_data, f, indent = 2, ensure_ascii = False)

#             print(f"Written: {chunks_output_path}")

#     except Exception as e:
#         raise e

if __name__ == "__main__":

    pipeline = build_pipeline()
    logger.info("Chunking strategy: %s", CHUNKING_STRATEGY)

    try:
        docs = pipeline.process([Path("testingpdf2/HDFC-Life-Group-Health-Shield.pdf")])

        for doc in docs:
            # 1. Save Transformed Markdown (with [TABLE_START] and [TABLE_END])
            output_path = doc.file_path.with_suffix(".md")
            output_path.write_text(doc.full_markdown, encoding="utf-8")
            print(f"Written: {output_path}")

            # 2. Save Raw LlamaParse Output
            raw_output_path = doc.file_path.with_name(
                doc.file_path.stem + "_raw.md"
            )
            raw_output_path.write_text(doc.raw_markdown, encoding = "utf-8")
            print(f"Written: {raw_output_path}")

            # 3. Chunk Transformed Markdown (simple or hierarchical) and output JSON
            chunks_data = get_chunks_data(doc.full_markdown)
            chunks_output_path = doc.file_path.with_name(
                doc.file_path.stem + "_chunks.json"
            )

            with chunks_output_path.open("w", encoding = "utf-8") as f:
                json.dump(chunks_data, f, indent = 2, ensure_ascii = False)

            print(f"Written: {chunks_output_path}")

    except Exception as e:
        raise e
