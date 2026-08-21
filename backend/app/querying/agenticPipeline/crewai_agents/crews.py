"""
Crew implementations of the strategy interfaces with granular metrics capture.
"""
from __future__ import annotations

import time

from crewai import Crew, Process

from .agents import (
    HybridRewriterAgentFactory,
    MasterOrchestratorAgentFactory,
    SemanticRewriterAgentFactory,
)
from .config import OrchestrationConfig
from .models import (
    AgentExecutionMetrics,
    OrchestrationState,
    SearchDecision,
    SearchType,
    SubQueryPlan,
)
from .strategies import IQueryClassifier, IQueryRewriter
from .tasks import build_classification_task, build_rewrite_task


class ClassificationFailedError(RuntimeError):
    """Raised when the classifier crew does not produce a valid SearchDecision."""


class RewriteFailedError(RuntimeError):
    """Raised when a rewriter crew does not produce a valid SubQueryPlan."""


def _record_agent_metrics(
    state: OrchestrationState,
    agent_name: str,
    crew_metrics,
    latency_ms: float,
    input_text: str,
    output_text: str,
) -> None:
    """Computes and registers granular metrics for an executed agent."""
    p_tokens = getattr(crew_metrics, "prompt_tokens", 0) or 0
    c_tokens = getattr(crew_metrics, "completion_tokens", 0) or 0
    cached = getattr(crew_metrics, "cached_prompt_tokens", 0) or 0
    total = getattr(crew_metrics, "total_tokens", 0) or 0
    reqs = getattr(crew_metrics, "successful_requests", 0) or 0

    # Throughput (Tokens per second)
    seconds = latency_ms / 1000.0
    tps = (c_tokens / seconds) if seconds > 0 else 0.0

    # Token / Word Expansion Ratio (Output length vs input query length)
    in_len = max(1, len(input_text.split()))
    out_len = len(output_text.split())
    expansion = out_len / in_len

    agent_metric = AgentExecutionMetrics(
        agent_name=agent_name,
        prompt_tokens=p_tokens,
        completion_tokens=c_tokens,
        cached_prompt_tokens=cached,
        total_tokens=total,
        successful_requests=reqs,
        latency_ms=round(latency_ms, 2),
        tokens_per_second=round(tps, 2),
        token_expansion_ratio=round(expansion, 2),
    )

    state.metrics.agent_metrics[agent_name] = agent_metric
    state.metrics.total_tokens += total
    state.metrics.total_prompt_tokens += p_tokens
    state.metrics.total_completion_tokens += c_tokens
    state.metrics.total_cached_prompt_tokens += cached
    state.metrics.total_requests += reqs


class MasterOrchestratorClassifier(IQueryClassifier):
    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config
        self._agent_factory = MasterOrchestratorAgentFactory(config)

    def classify(self, state: OrchestrationState) -> SearchDecision:
        agent = self._agent_factory.build()
        task = build_classification_task(
            agent=agent,
            current_message=state.current_message,
            history=state.conversation_history,
            config=self._config,
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=self._config.verbose)
        
        start_time = time.perf_counter()
        result = crew.kickoff()
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if result.pydantic is None:
            raise ClassificationFailedError("Classifier crew did not return a valid SearchDecision.")

        _record_agent_metrics(
            state=state,
            agent_name="Master Query Orchestrator",
            crew_metrics=crew.usage_metrics,
            latency_ms=latency_ms,
            input_text=state.current_message,
            output_text=result.pydantic.reasoning,
        )

        return result.pydantic


class _SingleAgentRewriter(IQueryRewriter):
    _search_type: SearchType

    def __init__(self, config: OrchestrationConfig, agent_factory) -> None:
        self._config = config
        self._agent_factory = agent_factory

    def rewrite(self, state: OrchestrationState) -> SubQueryPlan:
        agent = self._agent_factory.build()
        task = build_rewrite_task(
            agent=agent,
            current_message=state.current_message,
            history=state.conversation_history,
            search_type_label=self._search_type.value,
            config=self._config,
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=self._config.verbose)
        
        start_time = time.perf_counter()
        result = crew.kickoff()
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if result.pydantic is None:
            raise RewriteFailedError(f"{self._search_type.value} rewriter crew did not return a valid SubQueryPlan.")

        agent_name = f"{self._search_type.value.capitalize()} Search Query Rewriter"
        all_sub_queries = " ".join([sq.query for sq in result.pydantic.sub_queries])

        _record_agent_metrics(
            state=state,
            agent_name=agent_name,
            crew_metrics=crew.usage_metrics,
            latency_ms=latency_ms,
            input_text=state.current_message,
            output_text=all_sub_queries,
        )

        return result.pydantic


class SemanticQueryRewriter(_SingleAgentRewriter):
    _search_type = SearchType.SEMANTIC

    def __init__(self, config: OrchestrationConfig) -> None:
        super().__init__(config, SemanticRewriterAgentFactory(config))


class HybridQueryRewriter(_SingleAgentRewriter):
    _search_type = SearchType.HYBRID

    def __init__(self, config: OrchestrationConfig) -> None:
        super().__init__(config, HybridRewriterAgentFactory(config))