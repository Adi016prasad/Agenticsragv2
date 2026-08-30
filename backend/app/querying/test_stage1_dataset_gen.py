"""
Standalone CLI test runner for Step 1 (S3 Storage) and Step 2 (Synthetic Dataset Generation).
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
logger = logging.getLogger("TestStage1Runner")

from container import build_container, close_container
from storage import StorageFactory
from agenticPipeline.crewai_agents.config import DEFAULT_CONFIG, build_llm
from agenticPipeline.crewai_agents.tools.synthetic_testset_tool import (
    SyntheticTestsetGeneratorTool,
    SaveStage1CSVTool,
)
from crewai import Agent, Crew, Process, Task


async def test_unit_1_storage() -> bool:
    """Test 1: Verifies S3 upload and download capability."""
    print("\n" + "=" * 80)
    print("🧪 UNIT 1 TEST: S3 Object Storage Read/Write")
    print("=" * 80)
    
    storage = StorageFactory.create_storage()
    test_key = "benchmarks/test_connectivity.csv"
    test_content = "test_id,status\n1,s3_connected_successfully"

    print(f"• Uploading test file to S3 (key: '{test_key}')...")
    upload_ok = storage.upload_csv(key=test_key, csv_content=test_content)
    
    if not upload_ok:
        print("❌ S3 Upload Failed. Check AWS credentials or bucket permissions.")
        return False

    print("• Downloading test file from S3...")
    downloaded = storage.download_csv(key=test_key)
    
    if downloaded and "s3_connected_successfully" in downloaded:
        print("✅ UNIT 1 PASSED: S3 Storage upload and download verified successfully!")
        return True
    
    print("❌ S3 Download verification failed.")
    return False


async def test_unit_2_agentic_generation(collection_name: str = "testinghubnew") -> bool:
    """Test 2: Samples Qdrant chunks, generates synthetic questions + ground truths, and uploads CSV."""
    print("\n" + "=" * 80)
    print(f"🤖 UNIT 2 TEST: Autonomous Dataset Generation from Qdrant ('{collection_name}')")
    print("=" * 80)

    eval_run_id = f"eval_{uuid.uuid4().hex[:8]}"

    # Define the Testset Generation Agent
    generator_agent = Agent(
        role="Autonomous Evaluation Testset Engineer",
        goal=(
            "Extract representative policy document chunks from Qdrant, construct high-quality "
            "synthetic questions (Factual, Conditional, Comparative), pair them with exact factual ground-truth answers, "
            "and save the Stage-1 CSV to S3."
        ),
        backstory=(
            "You are an expert in RAG evaluation and testset construction. You extract ground-truth "
            "answers strictly from the provided text without hallucination, format them as JSON, "
            "and call the S3 saving tool."
        ),
        llm=build_llm(DEFAULT_CONFIG.orchestrator_model),
        tools=[SyntheticTestsetGeneratorTool(), SaveStage1CSVTool()],
        allow_delegation=False,
        verbose=True,
    )

    task_generate = Task(
        description=(
            f"1. Call 'Generate Synthetic Benchmark Testset' with collection_name='{collection_name}' and num_questions=3.\n"
            "2. Read the returned sampled document chunks.\n"
            "3. Generate 3 high-quality, realistic user questions:\n"
            "   - Question 1: Factual / Direct lookup\n"
            "   - Question 2: Conditional / Scenario-based\n"
            "   - Question 3: Comparative or Multi-hop\n"
            "4. For each question, extract the exact factual `ground_truth` answer directly from the text.\n"
            f"5. Package the result as JSON: {{\"collection_name\": \"{collection_name}\", \"test_pairs\": [{{\"question\": \"...\", \"ground_truth\": \"...\"}}, ...]}}\n"
            f"6. Call 'Save Stage-1 Testset to S3' with eval_run_id='{eval_run_id}' and your JSON string.\n"
            "7. Return the S3 path confirmation."
        ),
        expected_output="Confirmation of Stage-1 CSV uploaded to S3 with generated questions and ground truth.",
        agent=generator_agent,
    )

    crew = Crew(
        agents=[generator_agent],
        tasks=[task_generate],
        process=Process.sequential,
        verbose=True,
    )

    print(f"• Launching CrewAI Agent for Run ID: {eval_run_id}...")
    result = await asyncio.to_thread(crew.kickoff)

    print("\n" + "-" * 80)
    print("📊 AGENT EXECUTION RESULT:")
    print("-" * 80)
    print(result.raw)

    # Verify that the generated CSV actually exists in S3 and print contents
    s3_key = f"benchmarks/run_{eval_run_id}/stage1_dataset.csv"
    storage = StorageFactory.create_storage()
    csv_content = storage.download_csv(key=s3_key)

    if csv_content:
        print("\n" + "=" * 80)
        print(f"📄 DOWNLOADED STAGE-1 CSV FROM S3 ('{s3_key}'):")
        print("=" * 80)
        print(csv_content)
        print("=" * 80)
        print("✅ UNIT 2 PASSED: Dataset generation and S3 persistence working perfectly!")
        return True
    else:
        print(f"❌ Failed to verify CSV at key '{s3_key}'")
        return False


async def main():
    # Initialize container (Qdrant & Firestore)
    await build_container()

    try:
        storage_ok = await test_unit_1_storage()
        if storage_ok:
            await test_unit_2_agentic_generation(collection_name="testinghubnew")
    finally:
        await close_container()


if __name__ == "__main__":
    asyncio.run(main())