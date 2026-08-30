"""
Standalone CLI Runner: Executes the complete 3-Stage RAGAS Benchmark Pipeline
independently without running the FastAPI server.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

# 👉 RESOLVE UNUSED VERTEXAI IMPORT IN RAGAS PERMANENTLY (Before any other imports)
if "langchain_community.chat_models.vertexai" not in sys.modules:
    mod = types.ModuleType("langchain_community.chat_models.vertexai")
    mod.ChatVertexAI = MagicMock()
    sys.modules["langchain_community.chat_models.vertexai"] = mod

import asyncio
import logging
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RagasStandaloneRunner")

from container import build_container, close_container
from agenticPipeline.crewai_agents.config import DEFAULT_CONFIG
from agenticPipeline.crewai_agents.ragas_eval_crew import RagasEvaluationOrchestrator


async def main():
    print("\n" + "=" * 80)
    print("🚀 RUNNING 3-STAGE RAGAS BENCHMARK PIPELINE (STANDALONE CLI)")
    print("=" * 80)
    print("• Stage 1: Samples Qdrant chunks & creates Stage-1 CSV [question, ground_truth] -> S3")
    print("• Stage 2: Runs live Qdrant RAG & LLM synthesis -> Enriches 4-column CSV -> S3")
    print("• Stage 3: Evaluates Faithfulness, Relevance, Precision & Recall -> Sends Scorecard Email")
    print("=" * 80 + "\n")

    # 1. Initialize dependencies (Qdrant, Firestore, Bedrock LLM)
    await build_container()

    try:
        orchestrator = RagasEvaluationOrchestrator(config=DEFAULT_CONFIG)
        
        # Runs Stage 1 -> Stage 2 -> Stage 3 (0s delay for instant verification)
        await orchestrator.execute_full_benchmark(
            collection_name="testinghubnew",
            delay_seconds=0
        )

        print("\n" + "=" * 80)
        print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print("👉 Check your email for the detailed Ragas Quality Scorecard!")
        print(f"👉 Check S3 bucket '{os.getenv('EVAL_S3_BUCKET_NAME')}' for the generated CSV datasets.\n")

    except Exception as exc:
        logger.error(f"❌ Pipeline execution failed: {exc}", exc_info=True)

    finally:
        await close_container()


if __name__ == "__main__":
    asyncio.run(main())