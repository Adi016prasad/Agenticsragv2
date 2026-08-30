"""
Prometheus Custom Metrics for the CrewAI Agentic Pipeline.
Tracks search type routing, token consumption, cache hits, latencies, and feedback.
"""
from prometheus_client import Counter, Gauge, Histogram

# 1. Total Requests Routed through Agentic Pipeline
AGENTIC_REQUESTS_TOTAL = Counter(
    "agentic_requests_total",
    "Total requests handled by the agentic pipeline",
    ["search_type"],  # 'semantic' or 'hybrid'
)

# 2. End-to-End Flow Latency
AGENTIC_FLOW_LATENCY_SECONDS = Histogram(
    "agentic_flow_latency_seconds",
    "End-to-end latency of the CrewAI flow in seconds",
    ["search_type"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0],
)

# 3. Latency Per Individual Agent (Orchestrator, Semantic Rewriter, Hybrid Rewriter)
AGENTIC_AGENT_LATENCY_SECONDS = Histogram(
    "agentic_agent_latency_seconds",
    "Latency of individual agents in the pipeline",
    ["agent_name"],
    buckets=[0.2, 0.5, 1.0, 2.0, 4.0, 8.0],
)

# 4. Token Consumption Breakdown
AGENTIC_TOKENS_TOTAL = Counter(
    "agentic_tokens_total",
    "Total token consumption across agentic pipeline",
    ["search_type", "token_type"],  # token_type: 'prompt', 'completion', 'cached'
)

# 5. Live Prompt Cache Hit Ratio Gauge
AGENTIC_CACHE_HIT_RATIO = Gauge(
    "agentic_prompt_cache_hit_ratio_pct",
    "Real-time prompt cache hit percentage (cached / prompt * 100)",
    ["search_type"],
)

# 6. User Feedback Counter
AGENTIC_FEEDBACK_TOTAL = Counter(
    "agentic_feedback_total",
    "User feedback count for semantic and hybrid agents",
    ["agent_name", "sentiment"],  # sentiment: 'good', 'bad'
)


def record_agentic_flow_metrics(state) -> None:
    """Helper called at the end of every CrewAI flow to push metrics into Prometheus."""
    decision = getattr(state, "decision", None)
    search_type = decision.search_type.value if decision else "unknown"
    metrics = getattr(state, "metrics", None)

    if not metrics:
        return

    # Increment request count
    AGENTIC_REQUESTS_TOTAL.labels(search_type=search_type).inc()

    # Record total flow latency
    flow_latency_sec = getattr(metrics, "total_latency_ms", 0.0) / 1000.0
    AGENTIC_FLOW_LATENCY_SECONDS.labels(search_type=search_type).observe(flow_latency_sec)

    # Record tokens
    p_tok = getattr(metrics, "total_prompt_tokens", 0)
    c_tok = getattr(metrics, "total_completion_tokens", 0)
    cached_tok = getattr(metrics, "total_cached_prompt_tokens", 0)

    AGENTIC_TOKENS_TOTAL.labels(search_type=search_type, token_type="prompt").inc(p_tok)
    AGENTIC_TOKENS_TOTAL.labels(search_type=search_type, token_type="completion").inc(c_tok)
    AGENTIC_TOKENS_TOTAL.labels(search_type=search_type, token_type="cached").inc(cached_tok)

    # Compute & record cache hit ratio %
    if p_tok > 0:
        hit_ratio = (cached_tok / p_tok) * 100.0
        AGENTIC_CACHE_HIT_RATIO.labels(search_type=search_type).set(round(hit_ratio, 2))

    # Record per-agent latencies
    for agent_name, agent_m in getattr(metrics, "agent_metrics", {}).items():
        agent_lat_sec = getattr(agent_m, "latency_ms", 0.0) / 1000.0
        AGENTIC_AGENT_LATENCY_SECONDS.labels(agent_name=agent_name).observe(agent_lat_sec)