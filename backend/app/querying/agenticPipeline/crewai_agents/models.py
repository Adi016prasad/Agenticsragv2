"""
Domain models for the Query Orchestration system.

Pure data contracts (Pydantic models) shared across the flow, agents,
and crews. This module's only job is describing *shape*, never
*behavior* (SRP).
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A single turn in the conversation history."""

    role: Role
    content: str


class SearchType(str, Enum):
    """The retrieval strategies the master agent can choose between."""

    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SearchDecision(BaseModel):
    """Structured output of the Master Orchestrator's classification task."""

    search_type: SearchType = Field(
        ...,
        description=(
            "Whether the query needs pure semantic (dense vector) search "
            "or hybrid (dense + sparse/keyword) search."
        ),
    )
    reasoning: str = Field(..., description="Short justification for the chosen search type.")
    requires_decomposition: bool = Field(
        ..., description="Whether the query should be broken into multiple sub-queries."
    )


class SubQuery(BaseModel):
    """One rewritten/decomposed query paired with its retrieval depth."""

    query: str = Field(..., min_length=1, description="The rewritten sub-query text.")
    top_k: int = Field(..., ge=1, le=50, description="Number of results to retrieve for this sub-query.")

    @field_validator("query")
    @classmethod
    def _strip_and_validate(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v


class SubQueryPlan(BaseModel):
    """Final structured output: the ordered list of sub-queries to execute."""

    search_type: SearchType
    sub_queries: List[SubQuery] = Field(..., min_length=1, max_length=6)

    def as_tuples(self) -> List[tuple]:
        """Convenience accessor matching the (query, top_k) tuple shape."""
        return [(sq.query, sq.top_k) for sq in self.sub_queries]


class AgentExecutionMetrics(BaseModel):
    """Granular execution and token metrics for a single agent."""

    agent_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0
    total_tokens: int = 0
    successful_requests: int = 0
    latency_ms: float = 0.0
    tokens_per_second: float = 0.0
    token_expansion_ratio: float = 0.0
    flow_latency_contribution_pct: float = 0.0


class OrchestrationMetrics(BaseModel):
    """Aggregated token and latency metrics across the entire Flow."""

    total_latency_ms: float = 0.0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_prompt_tokens: int = 0
    total_requests: int = 0
    agent_metrics: Dict[str, AgentExecutionMetrics] = Field(default_factory=dict)


class OrchestrationState(BaseModel):
    """Execution state container passed through the Flow graph."""

    session_id: Optional[str] = None
    request_id: Optional[str] = None
    conversation_history: List[Message] = Field(default_factory=list)
    current_message: str = ""
    decision: Optional[SearchDecision] = None
    plan: Optional[SubQueryPlan] = None
    error: Optional[str] = None
    metrics: OrchestrationMetrics = Field(default_factory=OrchestrationMetrics)


# ---------------- Evaluation Models (For Metric Collector Agent) ----------------

class StrategyPerformanceSummary(BaseModel):
    strategy_name: str
    total_calls: int
    avg_latency_ms: float
    avg_tokens_per_request: float
    health_status: str = Field(description="'HEALTHY', 'DEGRADED', or 'CRITICAL'")
    bottlenecks_detected: List[str] = Field(default_factory=list)


# class SystemPerformanceEvaluation(BaseModel):
#     """Structured output of the Metric Collector Agent stored in Memory."""

#     evaluation_timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
#     time_window_hours: float
#     overall_health: str = Field(description="'OPTIMAL', 'WARNING', or 'UNSTABLE'")
#     semantic_performance: StrategyPerformanceSummary
#     hybrid_performance: StrategyPerformanceSummary
#     key_findings: List[str] = Field(description="Key observations and anomaly detections.")
#     optimization_recommendations: List[str] = Field(
#         description="Actionable prompt, top_k, or routing adjustments for the orchestrator."
#     )

# class SystemPerformanceEvaluation(BaseModel):
#     """Structured output of the Metric Collector Agent stored in Memory."""

#     evaluation_timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
#     time_window_hours: float
#     overall_health: str = Field(description="'OPTIMAL', 'WARNING', or 'UNSTABLE'")
    
#     # 🌟 THE SYNTHESIZED EXECUTIVE SUMMARY STRING
#     evaluation_summary_narrative: str = Field(
#         description=(
#             "A concise, high-impact narrative summarizing current performance, "
#             "comparing it against historical memory trends (e.g. Turn 1 vs Turn 2), "
#             "and highlighting the primary bottleneck and recommendation."
#         )
#     )
    
#     semantic_performance: StrategyPerformanceSummary
#     hybrid_performance: StrategyPerformanceSummary
#     key_findings: List[str]
#     optimization_recommendations: List[str]

class SystemPerformanceEvaluation(BaseModel):
    """Structured output of the Metric Collector Agent.

    Deliberately minimal: two prose strings the LLM can produce reliably.
    Any internal structure (bullets, sub-sections, numbered items) belongs
    INSIDE the strings, not as additional schema fields.
    """

    evaluation_summary_narrative: str = Field(
        ...,
        min_length=1,
        description=(
            "Prose narrative of current-window performance. Cover what happened "
            "in this window, how it compares to the prior evaluation memory, and "
            "the primary bottleneck. Multi-paragraph is fine; internal bullets "
            "are fine."
        ),
    )
    optimization_recommendations: str = Field(
        ...,
        min_length=1,
        description=(
            "Prose recommendations. Concrete, actionable adjustments to prompts, "
            "top_k, model choice, or routing. Use dashes or numbered lines inside "
            "the string if useful."
        ),
    )