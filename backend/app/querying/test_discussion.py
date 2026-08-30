"""
Interactive CLI Runner to test the Multi-Agent Discussion & Email Approval Flow immediately.
"""
from __future__ import annotations

import logging
import os
import sys
from dotenv import load_dotenv

# Ensure the querying root is in Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("TestDiscussionRunner")

from agenticPipeline.crewai_agents.agent_discussion_crew import AgentDiscussionCrew


def main() -> None:
    print("\n" + "=" * 80)
    print("🤖 STARTING MULTI-AGENT DISCUSSION (DynamoDB <---> Firebase)")
    print("=" * 80)
    print("• Agent 1: Audits DynamoDB tokens, latency, cost, and good/bad feedback.")
    print("• Agent 2: Cross-examines with Firestore active prompts & threads, debates model downscaling,")
    print("           stages the proposal in Firestore, and sends the action plan email.")
    print("=" * 80 + "\n")

    try:
        discussion_crew = AgentDiscussionCrew()
        result = discussion_crew.run_discussion()

        print("\n" + "=" * 80)
        print("📊 AGENT DISCUSSION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print(result)
        print("=" * 80 + "\n")
        print("👉 Check your inbox! An action plan email has been sent with 1-click Approve/Reject buttons.\n")

    except Exception as exc:
        logger.error(f"❌ Error during multi-agent discussion: {exc}", exc_info=True)


if __name__ == "__main__":
    main()