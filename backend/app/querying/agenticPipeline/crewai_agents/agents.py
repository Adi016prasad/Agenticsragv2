"""
Agent factories.

Each factory builds exactly one CrewAI Agent with a single, narrow responsibility (SRP).
"""
from __future__ import annotations

from crewai import Agent

from .config import OrchestrationConfig, build_llm
from .tools.api_fetcher import FetchMetricsFromAPITool
from .tools.dynamo_sandbox_tool import DynamoDBSandboxInterpreterTool

class MasterOrchestratorAgentFactory:
    """Builds the master classification agent (semantic vs hybrid)."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        return Agent(
            role="Master Query Orchestrator",
            goal=(
                "Decide, from the conversation history and the latest user "
                "message, whether the retrieval step needs pure semantic "
                "(dense vector) search or hybrid (dense + keyword/sparse) "
                "search, and whether the query bundles more than one "
                "distinct information need."
            ),
            backstory=(
                "You are the routing brain in front of a vector database. "
                "You never answer the user directly and you never touch the "
                "database yourself -- you only classify. You favor hybrid "
                "search when the query contains exact identifiers, codes, "
                "product names, invoice/order numbers, units, dates, or "
                "numeric filters that dense embeddings tend to blur. You "
                "favor semantic search for open-ended, conceptual, or "
                "paraphrastic questions. You mark a query for decomposition "
                "when it bundles more than one distinct information need."
            ),
            llm=build_llm(self._config.orchestrator_model),
            allow_delegation=False,
            reasoning=False,
            verbose=self._config.verbose,
        )


class SemanticRewriterAgentFactory:
    """Builds the agent responsible for pure semantic query rewriting."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        return Agent(
            role="Semantic Search Query Rewriter",
            goal=(
                "Rewrite the user's query, using conversation history for "
                "coreference and context, into one or more self-contained, "
                "semantically rich sub-queries optimized for dense vector "
                "retrieval, each paired with an appropriate top_k."
            ),
            backstory=(
                "You specialize in dense retrieval. You expand ambiguous "
                "pronouns and ellipsis using conversation context, resolve "
                "the query into standalone natural-language statements free "
                "of conversational scaffolding, and assign a small top_k "
                "for narrow, specific asks versus a larger top_k for broad, "
                "exploratory asks."
            ),
            llm=build_llm(self._config.rewriter_model),
            allow_delegation=False,
            verbose=self._config.verbose,
        )


class HybridRewriterAgentFactory:
    """Builds the agent responsible for hybrid query rewriting."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        return Agent(
            role="Hybrid Search Query Rewriter",
            goal=(
                "Rewrite the user's query into one or more sub-queries "
                "optimized for hybrid (dense + sparse/keyword) retrieval, "
                "preserving exact keywords, identifiers, codes, and "
                "filters, each paired with an appropriate top_k."
            ),
            backstory=(
                "You specialize in hybrid retrieval. You keep verbatim "
                "keywords, entity names, IDs, units, and numeric filters "
                "intact so the sparse/BM25 side of retrieval can match them "
                "exactly, while still phrasing each sub-query naturally "
                "enough for the dense side. You split multi-intent queries "
                "into separate sub-queries rather than merging them into "
                "one blob."
            ),
            llm=build_llm(self._config.rewriter_model),
            allow_delegation=False,
            verbose=self._config.verbose,
        )


class MetricCollectorAgentFactory:
    """Builds the Metric Collector Agent responsible for telemetry evaluation."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        return Agent(
            role="Production Telemetry & Latency Analyst",
            goal=(
                "Fetch telemetry statistics via the FastAPI service, analyze "
                "latency distributions (avg, p95), token efficiency, and error rates between "
                "Semantic and Hybrid agents, and persist performance insights to memory."
            ),
            backstory=(
                "You are an AI site reliability engineer. You consume REST API telemetry "
                "to evaluate production models and rewriters, identify degradation, "
                "and record actionable improvements into memory."
            ),
            llm=build_llm(self._config.orchestrator_model),
            tools=[FetchMetricsFromAPITool()],
            memory=False,
            allow_delegation=False,
            verbose=self._config.verbose,
        )

# from .tools.dynamo_sandbox_tool import DynamoDBSandboxInterpreterTool

# class DynamoDBQueryEngineerAgentFactory:
#     """Builds the Agent that dynamically writes Boto3 code based on natural language."""

#     def __init__(self, config: OrchestrationConfig) -> None:
#         self._config = config

#     def build(self) -> Agent:
#         schema_prompt = """
# EXACT DYNAMODB TABLE STRUCTURE:
# Table: OrchestrationMetrics
# - Primary Key: `request_id` (String - Partition Key), `timestamp` (Number - Sort Key in epoch ms)
# - GSI: `SearchTypeTimestampIndex` (PK: `search_type` [String], SK: `timestamp` [Number])
# - Attributes:
#   • session_id (String)
#   • current_message (String)
#   • search_type (String: 'semantic' | 'hybrid')
#   • reasoning (String)
#   • requires_decomposition (Boolean)
#   • sub_queries (List of maps: [{'query': str, 'top_k': int}])
#   • total_latency_ms (Number / Decimal)
#   • total_tokens (Number)
#   • total_prompt_tokens (Number)
#   • total_completion_tokens (Number)
#   • total_cached_prompt_tokens (Number)
#   • total_requests (Number)
#   • agent_metrics (Map: nested metrics per agent)
#   • error (String)

# QUERY GUIDELINES:
# 1. When filtering by `search_type` and `timestamp`, ALWAYS prefer querying the GSI `SearchTypeTimestampIndex` using KeyConditionExpression:
#    `table.query(IndexName='SearchTypeTimestampIndex', KeyConditionExpression=Key('search_type').eq(...) & Key('timestamp').gte(...))`
# 2. When searching across attributes (like error, latency, or keywords), use `table.scan(FilterExpression=...)`.
# 3. Handle pagination (`LastEvaluatedKey`) if needed.
# 4. Convert Decimals to float/int when formatting outputs.
# 5. The table variable is already connected to the correct AWS region (ap-south-1). Do NOT call boto3.resource() or specify regions yourself—always query the preloaded table object directly.
# """
#         return Agent(
#             role="Autonomous DynamoDB Query Engineer",
#             goal=(
#                 "Translate any natural language data inquiry into optimized Python/Boto3 "
#                 "query or scan code, execute it in the sandbox, and present the exact data results."
#             ),
#             backstory=(
#                 "You are an expert AWS DynamoDB and Python Boto3 data engineer.\n"
#                 f"{schema_prompt}\n"
#                 "You never guess. You write clean, executable Python scripts using `Key`, `Attr`, "
#                 "`table.query()`, or `table.scan()`, execute it using your sandbox tool, and return the findings."
#             ),
#             llm=build_llm(self._config.orchestrator_model),
#             tools=[DynamoDBSandboxInterpreterTool()],
#             allow_delegation=False,
#             memory=False,
#             verbose=self._config.verbose,
#         )

class DynamoDBQueryEngineerAgentFactory:
    """Builds the Agent that dynamically writes Boto3 code based on natural language."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        schema_prompt = """
EXACT DYNAMODB TABLE STRUCTURE:
Table: OrchestrationMetrics
- Primary Key: `request_id` (String - PK), `timestamp` (Number - SK in epoch ms)
- GSI: `SearchTypeTimestampIndex` (PK: `search_type`, SK: `timestamp`)
- Attributes: session_id, current_message, search_type, reasoning, requires_decomposition,
  sub_queries, total_latency_ms, total_tokens, total_prompt_tokens, total_completion_tokens,
  total_cached_prompt_tokens, total_requests, agent_metrics, error.

IMPORTANT:
- Use the preloaded `table` object directly in the sandbox.
- When answering the user, summarize the retrieved data in pure natural language text. Never return Python code in your final message.
"""
        return Agent(
            role="Autonomous DynamoDB Query Engineer",
            goal=(
                "Retrieve and analyze data from DynamoDB by executing Python code in the sandbox, "
                "then deliver the final answer as a clear, concise natural language text summary."
            ),
            backstory=(
                f"You are an expert AWS DynamoDB data engineer.\n{schema_prompt}\n"
                "You write and execute code in the sandbox behind the scenes, and you present your "
                "final answers in pure, human-readable text without showing the underlying code."
            ),
            llm=build_llm(self._config.orchestrator_model),
            tools=[DynamoDBSandboxInterpreterTool()],
            allow_delegation=False,
            memory=False,
            max_iter=2,               # 👈 HARD CAP: Maximum 2 tool attempts. Never enters infinite loops!
            max_execution_time=15, 
            verbose=self._config.verbose,
        )

DynamoDBAnalyticsAgentFactory = DynamoDBQueryEngineerAgentFactory