"""
Interactive CLI to ask natural language questions to your DynamoDB Analytics Agent.
"""
from __future__ import annotations

import logging
from dotenv import load_dotenv

load_dotenv()

from crewai_agents.analytics_crew import DynamoDBQueryCrew

logging.basicConfig(level=logging.INFO)


def main() -> None:
    query_crew = DynamoDBQueryCrew()

    print("\n" + "=" * 70)
    print("🤖 AUTONOMOUS DYNAMODB QUERY ENGINEER READY")
    print("=" * 70)

    # question = (
    #     "Give me a breakdown of all queries in the database: "
    #     "average latency, total token usage per search type, "
    #     "and how many times sub-query decomposition was triggered."
    # )

    question = "tell me the number of columns present in the database and check which request id has largest tokens consumption"

    print(f"\n❓ Question:\n\"{question}\"\n")
    answer = query_crew.execute_inquiry(question)

    print("\n" + "=" * 70)
    print("📊 AGENT ANSWER & DATA TABLE:")
    print("=" * 70)
    print(answer)
    print("=" * 70)


if __name__ == "__main__":
    main()