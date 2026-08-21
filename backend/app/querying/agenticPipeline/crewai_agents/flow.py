"""
Production orchestration Flow with end-to-end latency tracking.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

from crewai.flow.flow import Flow, listen, router, start

from .config import DEFAULT_CONFIG, OrchestrationConfig
from .crews import ClassificationFailedError, MasterOrchestratorClassifier, RewriteFailedError
from .models import Message, OrchestrationState, SearchType, SubQueryPlan
from .registry import RewriterRegistry
from .strategies import IQueryClassifier

logger = logging.getLogger(__name__)

_FAILED_LABEL = "failed"


class QueryOrchestrationFlow(Flow[OrchestrationState]):
    """Orchestrates: classify -> route -> rewrite (exactly one branch)."""

    def __init__(
        self,
        config: OrchestrationConfig = DEFAULT_CONFIG,
        classifier: Optional[IQueryClassifier] = None,
        rewriter_registry: Optional[RewriterRegistry] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._classifier: IQueryClassifier = classifier or MasterOrchestratorClassifier(config)
        self._rewriter_registry: RewriterRegistry = rewriter_registry or RewriterRegistry(config)
        self._flow_start_time: float = 0.0

    @start()
    def classify_query(self) -> None:
        self._flow_start_time = time.perf_counter()
        logger.info("Classifying query: %r", self.state.current_message)
        try:
            self.state.decision = self._classifier.classify(self.state)
        except ClassificationFailedError as exc:
            logger.error("Classification failed: %s", exc)
            self.state.error = f"classification_failed: {exc}"

    @router(classify_query)
    def route_to_single_rewriter(self) -> str:
        if self.state.error:
            return _FAILED_LABEL
        if self.state.decision is None:
            self.state.error = "no_decision_produced"
            return _FAILED_LABEL
        return self.state.decision.search_type.value

    @listen(SearchType.SEMANTIC.value)
    def run_semantic_rewrite(self) -> None:
        self._run_rewrite(SearchType.SEMANTIC)

    @listen(SearchType.HYBRID.value)
    def run_hybrid_rewrite(self) -> None:
        self._run_rewrite(SearchType.HYBRID)

    @listen(_FAILED_LABEL)
    def handle_failure(self) -> OrchestrationState:
        logger.error("Orchestration failed: %s", self.state.error)
        self._finalize_flow_metrics()
        return self.state

    def _run_rewrite(self, search_type: SearchType) -> None:
        rewriter = self._rewriter_registry.get(search_type)
        try:
            self.state.plan = rewriter.rewrite(self.state)
        except RewriteFailedError as exc:
            logger.error("Rewrite failed for %s: %s", search_type.value, exc)
            self.state.error = f"rewrite_failed: {exc}"
        finally:
            self._finalize_flow_metrics()

    def _finalize_flow_metrics(self) -> None:
        if self._flow_start_time > 0:
            total_lat = (time.perf_counter() - self._flow_start_time) * 1000.0
            self.state.metrics.total_latency_ms = round(total_lat, 2)
            
            # Calculate latency contribution percentages
            if total_lat > 0:
                for agent_m in self.state.metrics.agent_metrics.values():
                    pct = (agent_m.latency_ms / total_lat) * 100.0
                    agent_m.flow_latency_contribution_pct = round(pct, 2)

    def result(self) -> Optional[SubQueryPlan]:
        return self.state.plan


def run_orchestration(
    current_message: str,
    conversation_history: Optional[List[Message]] = None,
    config: OrchestrationConfig = DEFAULT_CONFIG,
) -> QueryOrchestrationFlow:
    flow = QueryOrchestrationFlow(config=config)
    flow.state.current_message = current_message
    flow.state.conversation_history = conversation_history or []
    flow.kickoff()
    return flow