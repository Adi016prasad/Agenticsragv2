"""
Agent factories with dynamic prompt retrieval, multi-tool access, and bidirectional collaboration.
Each factory builds exactly one CrewAI Agent with a single, narrow responsibility (SRP).
"""
from __future__ import annotations

from crewai import Agent

from .config import OrchestrationConfig, build_llm
from .prompt_loader import prompt_loader
from .tools import (
    DynamoDBSandboxInterpreterTool,
    FetchMetricsFromAPITool,
    FetchMetricsOfFeedbackFromAPITool,
    FirebaseSandboxInterpreterTool,
    ReadHumanOptimizationFeedbackTool,
    ReadRollbackIncidentsTool,
    SendOptimizationEmailTool,
    StageOptimizationProposalTool,
    DuckDuckGoWebSearchTool
)

class MasterOrchestratorAgentFactory:
    """Builds the master classification agent (semantic vs hybrid)."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        role, goal, backstory = prompt_loader.get_agent_prompt(
            template_id="agent_master_orchestrator",
            default_role="Master Query Orchestrator",
            default_goal=(
                "Decide, from the latest user "
                "message, whether the retrieval step needs pure semantic "
                "(dense vector) search or hybrid (dense + keyword/sparse) "
                "search, and whether the query bundles more than one "
                "distinct information need."
            ),
            default_backstory=(
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
        )

        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
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
        role, goal, backstory = prompt_loader.get_agent_prompt(
            template_id="agent_semantic_rewriter",
            default_role="Semantic Search Query Rewriter",
            default_goal=(
                "Rewrite the user's query, using conversation history for "
                "coreference and context, into one or more self-contained, "
                "semantically rich sub-queries optimized for dense vector "
                "retrieval, each paired with an appropriate top_k."
            ),
            default_backstory=(
                "You specialize in dense retrieval. You expand ambiguous "
                "pronouns and ellipsis using conversation context, resolve "
                "the query into standalone natural-language statements free "
                "of conversational scaffolding, and assign a small top_k "
                "for narrow, specific asks versus a larger top_k for broad, "
                "exploratory asks."
            ),
        )

        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=build_llm(self._config.rewriter_model),
            allow_delegation=False,
            verbose=self._config.verbose,
        )


class HybridRewriterAgentFactory:
    """Builds the agent responsible for hybrid query rewriting."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        role, goal, backstory = prompt_loader.get_agent_prompt(
            template_id="agent_hybrid_rewriter",
            default_role="Hybrid Search Query Rewriter",
            default_goal=(
                "Rewrite the user's query into one or more sub-queries "
                "optimized for hybrid (dense + sparse/keyword) retrieval, "
                "preserving exact keywords, identifiers, codes, and "
                "filters, each paired with an appropriate top_k."
            ),
            default_backstory=(
                "You specialize in hybrid retrieval. You keep verbatim "
                "keywords, entity names, IDs, units, and numeric filters "
                "intact so the sparse/BM25 side of retrieval can match them "
                "exactly, while still phrasing each sub-query naturally "
                "enough for the dense side. You split multi-intent queries "
                "into separate sub-queries rather than merging them into "
                "one blob"
            ),
        )

        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=build_llm(self._config.rewriter_model),
            allow_delegation=False,
            verbose=self._config.verbose,
        )


class MetricCollectorAgentFactory:
    """Builds the Metric Collector Agent responsible for telemetry evaluation."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        role, goal, backstory = prompt_loader.get_agent_prompt(
            template_id="agent_metric_collector",
            default_role="Production Telemetry & Latency Analyst",
            default_goal=(
                "Fetch telemetry statistics via the FastAPI service, analyze "
                "latency distributions (avg, p95), token efficiency, and error rates between "
                "Semantic and Hybrid agents "
                "Also fetch the feedback metrics via FastAPI service, analyze the feedback of the agents based on the good and bad feedback count"
            ),
            default_backstory=(
                "You are an AI site reliability engineer. You consume REST API telemetry "
                "to evaluate production models and rewriters, identify degradation, "
                "and record actionable improvements into memory"
            ),
        )

        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=build_llm(self._config.orchestrator_model),
            tools=[FetchMetricsFromAPITool(), FetchMetricsOfFeedbackFromAPITool()],
            memory=False,
            allow_delegation=False,
            verbose=self._config.verbose,
        )


class DynamoDBQueryEngineerAgentFactory:
    """Builds the Agent that dynamically writes Boto3 code for Orchestration and Feedback metrics."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        default_schema = """
EXACT DYNAMODB TABLES AND ATTRIBUTES:
1. `metrics_table` (Table: OrchestrationMetrics)
   - Primary Key: `request_id` (String - PK), `timestamp` (Number - SK in epoch ms)
   - GSI: `SearchTypeTimestampIndex` (PK: `search_type`, SK: `timestamp`)
   - Attributes: session_id, current_message, search_type, reasoning, requires_decomposition,
     sub_queries, total_latency_ms, total_tokens, total_prompt_tokens, total_completion_tokens,
     total_cached_prompt_tokens, cost, model_used, total_requests, agent_metrics, error.
2. `feedback_table` (Table: FeedbackMetrics)
   - Primary Key: `agentName` (String - PK) [Values: 'semanticAgent', 'hybridAgent']
   - Attributes: feedbackGoodCount (Number), feedbackBadCount (Number)
"""
        role, goal, backstory = prompt_loader.get_agent_prompt(
            template_id="agent_dynamo_query_engineer",
            default_role="Autonomous DynamoDB Telemetry & Feedback Engineer",
            default_goal=(
                "Retrieve, correlate, and analyze telemetry and feedback data across both "
                "OrchestrationMetrics and FeedbackMetrics tables by executing Python code in the sandbox, "
                "then deliver the final answer as a clear, concise natural language text summary."
            ),
            default_backstory=(
                f"You are an expert AWS DynamoDB telemetry engineer.\n{default_schema}\n"
                "You write and execute code in the sandbox behind the scenes, and you present your "
                "final answers in pure, human-readable text with exact numbers and metrics."
            ),
        )

        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=build_llm(self._config.orchestrator_model),
            tools=[DynamoDBSandboxInterpreterTool()],
            allow_delegation=True,
            memory=False,
            max_iter=6,
            max_execution_time=120,
            verbose=self._config.verbose,
        )

DynamoDBAnalyticsAgentFactory = DynamoDBQueryEngineerAgentFactory


class FirebaseQueryEngineerAgentFactory:
    """Builds the Lead Optimizer Agent that inspects Firestore, stages proposals, and sends action emails."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        candidate_models_context = """
5 CANDIDATE LLM MODELS AVAILABLE ON AWS BEDROCK (PRICING PER 1M TOKENS):
1. `Voxtral Mini 3B 2507`: $0.05 / $0.05 (Lowest cost, ultra-lightweight)
2. `Nemotron Nano 3 30B`: $0.07 / $0.28 (Ultra-low cost reasoning)
3. `GPT OSS Safeguard 20B`: $0.08 / $0.24 (Recommended balanced model, 65% cheaper than 120B)
4. `Ministral 3B`: $0.12 / $0.12 (Cost-efficient general model)
5. `GPT OSS Safeguard 120B`: $0.18 / $0.71 (Flagship model, high reasoning, highest cost)

FIRESTORE SCHEMA & ENVIRONMENT RULES:
- The Firestore client `db` is ALREADY PRELOADED. Do NOT import `firebase_admin`.
- In `prompt_template` collection, the prompt fields (`role`, `goal`, `backstory`, `description_template`, `expected_output`) 
  are stored INSIDE the `payload` map attribute!
"""
        role, goal, backstory = prompt_loader.get_agent_prompt(
            template_id="agent_firebase_query_engineer",
            default_role="Principal Systems Architect & Optimization Lead",
            default_goal=(
                "Lead system optimization: inspect Firestore, debate with DynamoDB Agent, "
                "stage approved prompt/model changes, and email concise action plans to the administrator."
            ),
            default_backstory=(
                f"You are the Lead Systems Architect.\n{candidate_models_context}\n"
                "You inspect Firestore, cross-examine DynamoDB telemetry, stage proposals, and trigger action emails."
            ),
        )

        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=build_llm(self._config.orchestrator_model),
            tools=[
                FirebaseSandboxInterpreterTool(),
                ReadHumanOptimizationFeedbackTool(),
                ReadRollbackIncidentsTool(),
                StageOptimizationProposalTool(),
                SendOptimizationEmailTool(),
            ],
            allow_delegation=True,
            memory=False,
            max_iter=8,
            max_execution_time=180,
            verbose=self._config.verbose
        )

class ExternalResearcherAgentFactory:
    """Builds the Agent that performs last-resort web research and cites clickable source URLs."""

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config

    def build(self) -> Agent:
        researcher_prompt = """
YOU ARE AN ELITE RESEARCHER & FACT-CHECKING JOURNALIST:
Your job is to find the ground truth for user questions when internal company documents lack the answer.

GROUND-PROOF & CITATION RULES:
1. Search the open web using 'Search Open Web with Source URLs'.
2. Synthesize a clean, accurate natural language answer.
3. MANDATORY: You MUST cite your sources at the bottom of your response in clickable Markdown format:
   Example:
   ---
   🔗 **Verified Sources & Ground Proof:**
   - [HDFC Life Official Portal](https://www.hdfclife.com/...)
   - [IRDAI Policy Guidelines](https://www.irdai.gov.in/...)
4. Never invent or hallucinate fake links—only cite the actual URLs returned by your search tool.
"""
        return Agent(
            role="Autonomous Senior Web Researcher & Source Fact-Checker",
            goal=(
                "Search the public internet to answer the user's question and deliver "
                "a verified, comprehensive response with direct clickable markdown source links."
            ),
            backstory=researcher_prompt,
            llm=build_llm(self._config.orchestrator_model),
            tools=[DuckDuckGoWebSearchTool()],
            allow_delegation=False,
            memory=False,
            max_iter=2,
            max_execution_time=60,
            verbose=self._config.verbose,
        )