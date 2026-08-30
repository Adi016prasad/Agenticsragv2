"""
Stage 2 Service: Executes Live Qdrant RAG, retrieves raw contexts, generates LLM responses,
and uploads the enriched 4-column Ragas dataset to S3.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Optional

from storage import StorageFactory

logger = logging.getLogger(__name__)


class RagEnrichmentService:
    """Enriches Stage-1 dataset with live Qdrant retrieval and LLM responses."""

    def __init__(self) -> None:
        self._storage = StorageFactory.create_storage()

    async def enrich_dataset(self, eval_run_id: str) -> Optional[str]:
        stage1_key = f"benchmarks/run_{eval_run_id}/stage1_dataset.csv"
        stage2_key = f"benchmarks/run_{eval_run_id}/stage2_enriched_dataset.csv"

        logger.info(f"Stage 2: Downloading '{stage1_key}' from S3...")
        csv_text = self._storage.download_csv(stage1_key)

        if not csv_text:
            logger.error(f"Stage 1 dataset not found at key: {stage1_key}")
            return None

        from container import get_container
        container = get_container()

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        logger.info(f"Executing live RAG pipeline across {len(rows)} test queries...")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["user_input", "reference", "retrieved_contexts", "response"])

        for row in rows:
            question = row.get("question", "").strip()
            ground_truth = row.get("ground_truth", "").strip()
            collection_name = row.get("collection_name", "testinghubnew").strip()

            # 1. Retrieve raw context chunks from Qdrant
            retrieved_chunks = container.vector_db.searchInVectorDatabase(
                query=question,
                collectionName=collection_name,
                limit=3
            )

            # 2. Generate LLM response & context filtering
            real_result = await container.llm.filteringresultwithLLM(
                parenttext=retrieved_chunks,
                query=question
            )
            response_text = real_result.output if real_result.isAnswerFound else "Information not found in documents."

            writer.writerow([
                question,
                ground_truth,
                json.dumps(retrieved_chunks),
                response_text
            ])

        success = self._storage.upload_csv(key=stage2_key, csv_content=output.getvalue())
        return stage2_key if success else None