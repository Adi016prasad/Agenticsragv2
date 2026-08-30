"""
Autonomous Web Research Crew: Executes last-resort open web search and citation synthesis.
"""
from __future__ import annotations

import logging
from crewai import Crew, Process, Task

from .agents import ExternalResearcherAgentFactory
from .config import DEFAULT_CONFIG, OrchestrationConfig

logger = logging.getLogger(__name__)


class WebResearchCrew:
    """Orchestrates web research and source citation generation."""

    def __init__(self, config: OrchestrationConfig = DEFAULT_CONFIG) -> None:
        self._config = config
        self._agent_factory = ExternalResearcherAgentFactory(config)

    def execute_research(self, user_query: str) -> str:
        logger.info(f"🌐 Triggering Last-Resort Web Research for: '{user_query}'")
        agent = self._agent_factory.build()

        task = Task(
            description=(
                "INSTRUCTIONS:\n"
                "1. Search the open web using your tool to find official answers and facts.\n"
                "2. Synthesize a comprehensive, clear response.\n"
                "3. Append a dedicated ' Verified Sources & Ground Proof' section at the end "
                "with clickable Markdown links: `[Source Title](URL)`."
                f"USER INQUIRY :\n"
                f"\"{user_query}\"\n\n"
            ),
            expected_output="A comprehensive answer with clickable Markdown source links cited at the bottom.",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self._config.verbose,
        )

        result = crew.kickoff()
        return str(result.raw)