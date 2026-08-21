"""
Evaluation Crew for periodic performance monitoring.
"""
from __future__ import annotations

import logging

from crewai import Crew, Process

from .agents import MetricCollectorAgentFactory, DynamoDBAnalyticsAgentFactory
from .config import OrchestrationConfig, DEFAULT_CONFIG
from .models import SystemPerformanceEvaluation
from .tasks import build_metric_evaluation_task, extract_json_object, build_dynamo_analytics_task

logger = logging.getLogger(__name__)


class MetricEvaluationCrew:
    """Executes telemetry evaluation and returns a SystemPerformanceEvaluation."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config
        self._agent_factory = MetricCollectorAgentFactory(config)

    def evaluate(self, lookback_hours: float = 0.25) -> SystemPerformanceEvaluation:
        agent = self._agent_factory.build()
        task = build_metric_evaluation_task(agent=agent, lookback_hours=lookback_hours)

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            memory=False,
            verbose=self._config.verbose,
        )

        result = crew.kickoff()

        # 1) Fast path — CrewOutput.pydantic populated directly
        if isinstance(getattr(result, "pydantic", None), SystemPerformanceEvaluation):
            logger.info("✅ Metric evaluation ready (CrewOutput.pydantic).")
            return result.pydantic

        # 2) Same object, one level deeper — TaskOutput.pydantic on the last task
        tasks_output = getattr(result, "tasks_output", None) or []
        if tasks_output:
            last_pyd = getattr(tasks_output[-1], "pydantic", None)
            if isinstance(last_pyd, SystemPerformanceEvaluation):
                logger.info("✅ Metric evaluation ready (TaskOutput.pydantic).")
                return last_pyd

        # 3) Fallback — parse from raw. Guardrail already validated this JSON,
        #    so this path is safe; it only exists because CrewAI's internal
        #    propagation of a guardrail-returned BaseModel is unreliable.
        raw = ""
        if tasks_output and getattr(tasks_output[-1], "raw", None):
            raw = tasks_output[-1].raw
        elif getattr(result, "raw", None):
            raw = result.raw

        if raw:
            extracted = extract_json_object(raw)
            if extracted:
                try:
                    obj = SystemPerformanceEvaluation.model_validate_json(extracted)
                    logger.info("✅ Metric evaluation ready (raw JSON re-parse).")
                    return obj
                except Exception as exc:
                    logger.error("Re-parse of guardrail-validated raw failed: %s", exc)

        raise RuntimeError(
            "Metric Collector Agent did not return a valid "
            f"SystemPerformanceEvaluation. Raw prefix: {raw[:300]!r}"
        )

class DynamoDBAnalyticsCrew:
    def __init__(self, config: OrchestrationConfig = DEFAULT_CONFIG) -> None:
        self._config = config
        self._agent_factory = DynamoDBAnalyticsAgentFactory(config)

    def ask(self, user_query: str) -> str:
        agent = self._agent_factory.build()
        task = build_dynamo_analytics_task(agent=agent, user_query=user_query)

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self._config.verbose,
        )

        result = crew.kickoff()
        return str(result.raw)