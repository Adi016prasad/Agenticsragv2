"""
Interactive CLI to ask natural language questions to your Firebase Analytics Agent.
"""
from __future__ import annotations

import logging
from dotenv import load_dotenv
from crewai import Crew, Process

load_dotenv()

from crewai_agents.agents import FirebaseQueryEngineerAgentFactory
from crewai_agents.config import DEFAULT_CONFIG
from crewai_agents.tasks import build_dynamic_firebase_query_task

logging.basicConfig(level=logging.INFO)

def main() -> None:
    config = DEFAULT_CONFIG
    factory = FirebaseQueryEngineerAgentFactory(config)
    agent = factory.build()

    question = "give me the burst limit mentioned for the different tiers"

    task = build_dynamic_firebase_query_task(agent=agent, user_query=question)
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=config.verbose,
    )

    print(f"\n❓ Question:\n\"{question}\"\n")
    result = crew.kickoff()

    print("\n" + "=" * 70)
    print("📊 AGENT A (FIREBASE) ANSWER:")
    print("=" * 70)
    print(result.raw)
    print("=" * 70)


if __name__ == "__main__":
    main()