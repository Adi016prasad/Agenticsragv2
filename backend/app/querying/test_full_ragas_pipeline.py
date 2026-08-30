"""
Interactive CLI Runner to execute the Full 3-Stage RAGAS Benchmark Pipeline immediately.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RagasPipelineRunner")

from container import build_container, close_container
from test_stage1_dataset_gen import test_unit_2_agentic_generation
from rag_enrichment_service import RagEnrichmentService
from ragas_benchmark_engine import RagasBenchmarkEngine


async def run_full_pipeline(collection_name: str = "testinghubnew"):
    print("\n" + "=" * 80)
    print("🚀 STARTING COMPLETE 3-STAGE RAGAS BENCHMARK PIPELINE")
    print("=" * 80)

    # 1. Initialize Containers & Clients
    await build_container()

    try:
        eval_run_id = f"eval_{uuid.uuid4().hex[:8]}"

        # =====================================================================
        # STAGE 1: Synthetic Dataset Generation & S3 Upload
        # =====================================================================
        print("\n" + "-" * 80)
        print("🤖 STAGE 1: Generating Synthetic Questions & Ground Truth from Qdrant...")
        print("-" * 80)
        stage1_ok = await test_unit_2_agentic_generation(collection_name=collection_name)

        if not stage1_ok:
            print("❌ Stage 1 failed. Aborting pipeline.")
            return

        # =====================================================================
        # STAGE 2: Live RAG Execution & CSV Enrichment
        # =====================================================================
        print("\n" + "-" * 80)
        print("⚡ STAGE 2: Executing Live Qdrant RAG & LLM Synthesis...")
        print("-" * 80)
        enricher = RagEnrichmentService()
        stage2_key = await enricher.enrich_dataset(eval_run_id=eval_run_id)

        if not stage2_key:
            print("❌ Stage 2 enrichment failed. Aborting pipeline.")
            return

        # =====================================================================
        # STAGE 3: Mathematical RAGAS Scoring & Email Dispatch
        # =====================================================================
        print("\n" + "-" * 80)
        print("📊 STAGE 3: Running Ragas Metric Scoring & Emailing Scorecard...")
        print("-" * 80)
        evaluator = RagasBenchmarkEngine()
        scores = evaluator.run_ragas_evaluation(eval_run_id=eval_run_id)

        print("\n" + "=" * 80)
        print("🎉 COMPLETE 3-STAGE RAGAS PIPELINE FINISHED SUCCESSFULLY!")
        print("=" * 80)
        print(f"• Run ID: {eval_run_id}")
        print(f"• Final Ragas Scores: {scores}")
        print("👉 Check your email for the detailed RAG Quality Scorecard!\n")

    finally:
        await close_container()


if __name__ == "__main__":
    asyncio.run(run_full_pipeline(collection_name="testinghubnew"))