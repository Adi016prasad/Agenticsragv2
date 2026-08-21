"""
Crew for executing dynamic natural-language DynamoDB queries.
"""
from __future__ import annotations

from crewai import Crew, Process

from .agents import DynamoDBQueryEngineerAgentFactory
from .config import DEFAULT_CONFIG, OrchestrationConfig
from .tasks import build_dynamic_dynamo_query_task


class DynamoDBQueryCrew:
    """Orchestrates natural language to DynamoDB query execution."""

    def __init__(self, config: OrchestrationConfig = DEFAULT_CONFIG) -> None:
        self._config = config
        self._agent_factory = DynamoDBQueryEngineerAgentFactory(config)

    def execute_inquiry(self, user_inquiry: str) -> str:
        agent = self._agent_factory.build()
        task = build_dynamic_dynamo_query_task(agent=agent, user_query=user_inquiry)

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self._config.verbose,
        )

        result = crew.kickoff()
        return str(result.raw)