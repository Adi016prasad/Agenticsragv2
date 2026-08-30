"""
Stage 1 Tool: Samples Qdrant parent chunks and serializes generated testsets to S3.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any, Dict, List, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from storage import StorageFactory

logger = logging.getLogger(__name__)


class SampleChunksInput(BaseModel):
    collection_name: str = Field(
        default="testinghubnew",
        description="Target Qdrant collection name to sample."
    )
    sample_limit: int = Field(
        default=10,
        description="Number of document chunks to sample from vector database."
    )


class SampleQdrantChunksTool(BaseTool):
    name: str = "Sample Qdrant Document Chunks"
    description: str = (
        "Samples representative document chunks from a Qdrant collection to provide "
        "context for synthetic question and ground-truth generation."
    )
    args_schema: Type[BaseModel] = SampleChunksInput

    def _run(self, collection_name: str = "testinghubnew", sample_limit: int = 10) -> str:
        try:
            from container import get_container
            container = get_container()
        except Exception as exc:
            return f"Error connecting to container: {exc}"

        if not container.vector_db.ensure_collection_exists(collectionName=collection_name):
            return f"Error: Qdrant collection '{collection_name}' does not exist."

        try:
            sample_points = container.vector_db.client.scroll(
                collection_name=collection_name,
                limit=sample_limit * 2,
                with_payload=True
            )[0]

            parent_chunks = [
                p.payload.get("parent_text")
                for p in sample_points
                if p.payload and p.payload.get("parent_text")
            ]

            unique_chunks = list(set(parent_chunks))[:sample_limit]

            if not unique_chunks:
                return f"No parent_text chunks found in '{collection_name}'."

            return json.dumps({
                "collection_name": collection_name,
                "document_chunks": unique_chunks
            })

        except Exception as exc:
            logger.error(f"Failed to scroll Qdrant chunks: {exc}", exc_info=True)
            return f"Error sampling chunks: {exc}"


class SaveStage1DatasetTool(BaseTool):
    name: str = "Save Stage 1 Dataset to S3"
    description: str = (
        "Saves the generated question, ground_truth, and collection_name entries into a CSV "
        "and uploads it to AWS S3 at 'benchmarks/run_{eval_run_id}/stage1_dataset.csv'."
    )

    def _run(self, eval_run_id: str, test_pairs_json: str) -> str:
        try:
            data = json.loads(test_pairs_json) if isinstance(test_pairs_json, str) else test_pairs_json
            pairs = data.get("test_pairs", [])
            collection_name = data.get("collection_name", "testinghubnew")

            if not pairs:
                return "Error: No test pairs provided."

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["question", "ground_truth", "collection_name"])

            for item in pairs:
                writer.writerow([
                    item.get("question", "").strip(),
                    item.get("ground_truth", "").strip(),
                    collection_name
                ])

            s3_key = f"benchmarks/run_{eval_run_id}/stage1_dataset.csv"
            storage = StorageFactory.create_storage()
            success = storage.upload_csv(key=s3_key, csv_content=output.getvalue())

            if success:
                return f"SUCCESS: Uploaded Stage-1 dataset ({len(pairs)} rows) to S3 at '{s3_key}'"
            return "Error: S3 upload failed."

        except Exception as exc:
            return f"Error saving Stage-1 dataset: {exc}"