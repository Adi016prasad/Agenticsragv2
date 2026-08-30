"""
Interactive CLI to ask natural language questions to your DynamoDB Analytics Agent.
"""
from __future__ import annotations

import logging
from dotenv import load_dotenv

load_dotenv()

from crewai_agents.analytics_crew import DynamoDBQueryCrewForFeedback

logging.basicConfig(level=logging.INFO)


def main() -> None:
    query_crew = DynamoDBQueryCrewForFeedback()

    print("\n" + "=" * 70)
    print("🤖 AUTONOMOUS DYNAMODB QUERY ENGINEER READY")
    print("=" * 70)

    question = "tell me the feedback of semantic agents of last 30 minutes"

    print(f"\n❓ Question:\n\"{question}\"\n")
    answer = query_crew.execute_inquiry(question)

    print("\n" + "=" * 70)
    print("📊 AGENT ANSWER & DATA TABLE:")
    print("=" * 70)
    print(answer)
    print("=" * 70)


if __name__ == "__main__":
    main()