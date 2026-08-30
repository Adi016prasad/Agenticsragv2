"""
Orchestrator for the 3-Stage RAGAS Continuous Benchmark Pipeline.
Executes Stage 1, Stage 2, and Stage 3 with built-in asynchronous delays.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from crewai import Agent, Crew, Process, Task

from .config import DEFAULT_CONFIG, OrchestrationConfig, build_llm
from .tools.synthetic_testset_tool import SampleQdrantChunksTool, SaveStage1DatasetTool
from rag_enrichment_service import RagEnrichmentService
from ragas_benchmark_engine import RagasBenchmarkEngine

logger = logging.getLogger(__name__)


class RagasEvaluationOrchestrator:
    """Orchestrates Stage 1 (Generation) -> Stage 2 (RAG) -> Stage 3 (Ragas Scorecard)."""

    def __init__(self, config: OrchestrationConfig = DEFAULT_CONFIG) -> None:
        self._config = config

    def _build_testset_agent(self) -> Agent:
        return Agent(
            role="Autonomous RAG Testset Engineer",
            goal=(
                "Extract document chunks from Qdrant, generate realistic questions "
                "(Factual, Conditional, Comparative, Multi-Hop), pair with exact ground-truth answers, "
                "and save the Stage-1 CSV to S3."
            ),
            backstory=(
                "You are a benchmark dataset engineer. You extract factual ground-truth answers "
                "directly from the sampled document chunks without hallucination and save the dataset to S3."
            ),
            llm=build_llm(self._config.discussion_model),
            tools=[SampleQdrantChunksTool(), SaveStage1DatasetTool()],
            allow_delegation=False,
            memory=False,
            verbose=self._config.verbose,
        )

    async def execute_stage_1_generation(self, eval_run_id: str, collection_name: str = "testinghubnew", num_questions: int = 5) -> bool:
        """Stage 1: Generates synthetic questions and ground-truth answers."""
        logger.info(f"🚀 [Stage 1] Generating synthetic dataset for collection: '{collection_name}'...")
        agent = self._build_testset_agent()

        task = Task(
            description=(
                f"1. Sample document chunks using 'Sample Qdrant Document Chunks' with collection_name='{collection_name}'.\n"
                f"2. Formulate {num_questions} diverse questions (Factual, Conditional, Comparative, Multi-Hop).\n"
                "3. Extract the exact factual ground_truth answer for each question directly from the text.\n"
                f"4. Format payload as JSON: {{\"collection_name\": \"{collection_name}\", \"test_pairs\": [{{\"question\": \"...\", \"ground_truth\": \"...\"}}]}}\n"
                f"5. Upload to S3 using 'Save Stage 1 Dataset to S3' with eval_run_id='{eval_run_id}'."
            ),
            expected_output="Confirmation of Stage 1 CSV uploaded to S3.",
            agent=agent,
        )

        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=self._config.verbose)
        result = await asyncio.to_thread(crew.kickoff)
        return "SUCCESS" in str(result.raw).upper()

    async def execute_full_benchmark(self, collection_name: str = "testinghubnew", delay_seconds: int = 300) -> None:
        """
        Executes the full 3-Stage Pipeline with configurable delay (default 5 minutes between stages).
        """
        eval_run_id = f"eval_{uuid.uuid4().hex[:8]}"
        logger.info(f"🏁 Starting Continuous RAG Benchmark Run: {eval_run_id}")

        # Stage 1
        stage1_ok = await self.execute_stage_1_generation(eval_run_id=eval_run_id, collection_name=collection_name)
        if not stage1_ok:
            logger.error("❌ Stage 1 failed. Aborting benchmark run.")
            return

        # 5-Minute Delay between Stage 1 and Stage 2
        if delay_seconds > 0:
            logger.info(f"⏳ Waiting {delay_seconds}s before Stage 2 RAG execution...")
            await asyncio.sleep(delay_seconds)

        # Stage 2
        enricher = RagEnrichmentService()
        stage2_key = await enricher.enrich_dataset(eval_run_id=eval_run_id)
        if not stage2_key:
            logger.error("❌ Stage 2 enrichment failed. Aborting benchmark run.")
            return

        # 5-Minute Delay between Stage 2 and Stage 3
        if delay_seconds > 0:
            logger.info(f"⏳ Waiting {delay_seconds}s before Stage 3 Ragas scoring...")
            await asyncio.sleep(delay_seconds)

        # Stage 3
        evaluator = RagasBenchmarkEngine()
        await asyncio.to_thread(evaluator.run_ragas_evaluation, eval_run_id=eval_run_id)
        logger.info(f"🎉 Complete 3-Stage RAGAS Benchmark completed for {eval_run_id}!")