"""
Production-Ready Prompt Seeding Engine for Firebase / Firestore.
Adheres strictly to SOLID principles, uses atomic batch writes, and Pydantic validation.
"""
from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google.cloud import firestore
from pydantic import BaseModel, Field

# Ensure querying root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("PromptSeeder")


# ==============================================================================
# 1. DOMAIN MODELS (Single Responsibility: Data Validation)
# ==============================================================================

class PromptType(str, Enum):
    AGENT = "agent"
    TASK = "task"


class PromptTemplateSchema(BaseModel):
    """Pydantic entity representing a validated Prompt Template."""
    template_id: str = Field(..., description="Unique document ID in Firestore")
    prompt_type: PromptType = Field(..., description="Type of prompt: agent or task")
    version: int = Field(default=1, description="Version number of the prompt template")
    is_active: bool = Field(default=True, description="Whether this prompt is currently active")
    payload: Dict[str, Any] = Field(..., description="The prompt body (role/goal/backstory or description/expected_output)")
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of creation/update",
    )
    updated_by: str = Field(default="system_seeder", description="Author of the mutation")


# ==============================================================================
# 2. REPOSITORY ABSTRACTIONS & IMPLEMENTATION (Liskov & Interface Segregation)
# ==============================================================================

class IPromptRepository(ABC):
    """Interface for Prompt Persistence."""

    @abstractmethod
    def save_batch(self, templates: List[PromptTemplateSchema]) -> int:
        """Persists a list of prompt templates atomically. Returns count of saved items."""
        pass


class FirestorePromptRepository(IPromptRepository):
    """Firestore implementation of prompt storage using atomic batches."""

    def __init__(self, client: firestore.Client, collection_name: str = "prompt_template") -> None:
        self._db = client
        self._collection_name = collection_name

    def save_batch(self, templates: List[PromptTemplateSchema]) -> int:
        batch = self._db.batch()
        collection_ref = self._db.collection(self._collection_name)

        for item in templates:
            doc_ref = collection_ref.document(item.template_id)
            batch.set(doc_ref, item.model_dump(), merge=True)

        batch.commit()
        return len(templates)


# ==============================================================================
# 3. PROMPT REGISTRY (Open/Closed Principle: Catalog of Prompts)
# ==============================================================================

class IPromptRegistry(ABC):
    """Interface for prompt catalogs."""

    @abstractmethod
    def get_all_templates(self) -> List[PromptTemplateSchema]:
        pass


class CodebasePromptRegistry(IPromptRegistry):
    """Catalog of all Agent and Task prompts extracted directly from your codebase."""

    def get_all_templates(self) -> List[PromptTemplateSchema]:
        raw_definitions: List[Dict[str, Any]] = [
            # ------------------------------------------------------------------
            # AGENT PROMPTS (from agents.py)
            # ------------------------------------------------------------------
            {
                "template_id": "agent_master_orchestrator",
                "prompt_type": PromptType.AGENT,
                "payload": {
                    "role": "Master Query Orchestrator",
                    "goal": (
                        "Decide, from the conversation history and the latest user "
                        "message, whether the retrieval step needs pure semantic "
                        "(dense vector) search or hybrid (dense + keyword/sparse) "
                        "search, and whether the query bundles more than one "
                        "distinct information need."
                    ),
                    "backstory": (
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
                },
            },
            {
                "template_id": "agent_semantic_rewriter",
                "prompt_type": PromptType.AGENT,
                "payload": {
                    "role": "Semantic Search Query Rewriter",
                    "goal": (
                        "Rewrite the user's query, using conversation history for "
                        "coreference and context, into one or more self-contained, "
                        "semantically rich sub-queries optimized for dense vector "
                        "retrieval, each paired with an appropriate top_k."
                    ),
                    "backstory": (
                        "You specialize in dense retrieval. You expand ambiguous "
                        "pronouns and ellipsis using conversation context, resolve "
                        "the query into standalone natural-language statements free "
                        "of conversational scaffolding, and assign a small top_k "
                        "for narrow, specific asks versus a larger top_k for broad, "
                        "exploratory asks."
                    ),
                },
            },
            {
                "template_id": "agent_hybrid_rewriter",
                "prompt_type": PromptType.AGENT,
                "payload": {
                    "role": "Hybrid Search Query Rewriter",
                    "goal": (
                        "Rewrite the user's query into one or more sub-queries "
                        "optimized for hybrid (dense + sparse/keyword) retrieval, "
                        "preserving exact keywords, identifiers, codes, and "
                        "filters, each paired with an appropriate top_k."
                    ),
                    "backstory": (
                        "You specialize in hybrid retrieval. You keep verbatim "
                        "keywords, entity names, IDs, units, and numeric filters "
                        "intact so the sparse/BM25 side of retrieval can match them "
                        "exactly, while still phrasing each sub-query naturally "
                        "enough for the dense side. You split multi-intent queries "
                        "into separate sub-queries rather than merging them into "
                        "one blob"
                    ),
                },
            },
            {
                "template_id": "agent_metric_collector",
                "prompt_type": PromptType.AGENT,
                "payload": {
                    "role": "Production Telemetry & Latency Analyst",
                    "goal": (
                        "Fetch telemetry statistics via the FastAPI service, analyze "
                        "latency distributions (avg, p95), token efficiency, and error rates between "
                        "Semantic and Hybrid agents "
                        "Also fetch the feedback metrics via FastAPI service, analyze the feedback of the agents based on the good and bad feedback count"
                    ),
                    "backstory": (
                        "You are an AI site reliability engineer. You consume REST API telemetry "
                        "to evaluate production models and rewriters, identify degradation, "
                        "and record actionable improvements into memory"
                    ),
                },
            },
            {
                "template_id": "agent_dynamo_query_engineer",
                "prompt_type": PromptType.AGENT,
                "payload": {
                    "role": "Autonomous DynamoDB Telemetry & Feedback Engineer",
                    "goal": (
                        "Retrieve, correlate, and analyze telemetry and feedback data across both "
                        "OrchestrationMetrics and FeedbackMetrics tables by executing Python code in the sandbox, "
                        "then deliver the final answer as a clear, concise natural language text summary."
                    ),
                    "backstory": (
                        "You are an expert AWS DynamoDB telemetry engineer.\n"
                        "EXACT DYNAMODB TABLES AND ATTRIBUTES:\n"
                        "1. `metrics_table` (Table: OrchestrationMetrics)\n"
                        "   - Primary Key: `request_id` (String - PK), `timestamp` (Number - SK in epoch ms)\n"
                        "   - GSI: `SearchTypeTimestampIndex` (PK: `search_type`, SK: `timestamp`)\n"
                        "   - Attributes: session_id, current_message, search_type, reasoning, requires_decomposition,\n"
                        "     sub_queries, total_latency_ms, total_tokens, total_prompt_tokens, total_completion_tokens,\n"
                        "     total_cached_prompt_tokens, cost, model_used, total_requests, agent_metrics, error.\n"
                        "2. `feedback_table` (Table: FeedbackMetrics)\n"
                        "   - Primary Key: `agentName` (String - PK) [Values: 'semanticAgent', 'hybridAgent']\n"
                        "   - Attributes: feedbackGoodCount (Number), feedbackBadCount (Number)\n"
                        "   - Direct Lookups / Queries:\n"
                        "     • Get specific agent: `feedback_table.get_item(Key={'agentName': 'semanticAgent'})\n"
                        "     • Get all feedback: `items = feedback_table.scan().get('Items', [])\n"
                        "HOW TO PROCESS DATA:\n"
                        "- To fetch feedback metrics: Scan or get items directly from `feedback_table`.\n"
                        "- To calculate satisfaction rates: `good_rate = (good / (good + bad)) * 100`\n"
                        "- To correlate telemetry with feedback: Query `metrics_table` for token/latency averages and compare against `feedback_table` counts.\n"
                        "- Always `print()` final computed numbers, tables, and comparisons to stdout.\n"
                        "- Summarize findings in clean natural language without showing raw Python code."
                    ),
                },
            },
            {
                "template_id": "agent_firebase_query_engineer",
                "prompt_type": PromptType.AGENT,
                "payload": {
                    "role": "Autonomous Firebase & Firestore Data Engineer",
                    "goal": (
                        "Retrieve, inspect, and analyze data from Firebase / Firestore by executing Python code in the sandbox, "
                        "then deliver the final answer as a clear, concise natural language text summary."
                    ),
                    "backstory": (
                        "You are an expert Firebase and Firestore database engineer.\n"
                        "FIREBASE / FIRESTORE ENVIRONMENT:\n"
                        "- Pre-loaded Firestore client: `db`\n"
                        "- Modules available: `firestore`, `firebase_admin`, `pd` (pandas), `json`, `datetime`\n"
                        "- Querying examples:\n"
                        "    - docs = db.collection('your_collection').stream()\n"
                        "    - docs = db.collection('your_collection').where('field', '==', 'value').stream()\n"
                        "    - doc = db.collection('your_collection').document('doc_id').get()\n"
                        "IMPORTANT:\n"
                        "- Use the preloaded `db` object directly in the sandbox.\n"
                        "- When answering the user, summarize the retrieved data in pure natural language text. Never return Python code in your final message.\n"
                        "- MULTI-DATA QUERIES: If the user asks for multiple collections or rules in a single question (e.g. blacklisted IPs AND rate limits), "
                        "query all needed collections in ONE single Python script to get all results immediately in one iteration."
                    ),
                },
            },

            # ------------------------------------------------------------------
            # TASK PROMPTS (from tasks.py)
            # ------------------------------------------------------------------
            {
                "template_id": "task_classification",
                "prompt_type": PromptType.TASK,
                "payload": {
                    "description_template": (
                        "TASK INSTRUCTIONS:\n"
                        "Classify the user's request for vector retrieval.\n"
                        "• Return search_type='semantic' for open-ended, conceptual, or paraphrastic questions.\n"
                        "• Return search_type='hybrid' when the query relies on exact keywords, identifiers, "
                        "codes, product names, numeric filters, dates, or negations.\n"
                        "• Set requires_decomposition=true if the message bundles more than one distinct information need.\n\n"
                        "CRITICAL: Output a valid single JSON object conforming strictly to the SearchDecision schema. "
                        "Do NOT wrap it in markdown code fences. Do NOT add any preamble or trailing text. "
                        "Do NOT use double braces '{{' or extra wrapper brackets.\n\n"
                        "CONVERSATION CONTEXT:\n"
                        "{conversation_context}\n\n"
                        "CURRENT USER MESSAGE:\n{current_message}"
                    ),
                    "expected_output": (
                        "A validated SearchDecision object with fields: "
                        "search_type, reasoning, requires_decomposition."
                    ),
                },
            },
            {
                "template_id": "task_rewrite",
                "prompt_type": PromptType.TASK,
                "payload": {
                    "description_template": (
                        "TASK INSTRUCTIONS (RETRIEVAL STRATEGY: {search_type_label_upper}):\n"
                        "1. Rewrite the user's request into 1 to {max_sub_queries} self-contained sub-queries.\n"
                        "2. Resolve pronouns and ellipsis using conversation context so each sub-query stands completely alone.\n"
                        "3. For each sub-query, assign a top_k between {min_top_k} and {max_top_k} "
                        "(default around {default_top_k}): narrow lookups get smaller top_k, broad lookups get larger top_k.\n"
                        "4. Set search_type='{search_type_label}' on output.\n\n"
                        "CRITICAL: Output a valid single JSON object conforming strictly to the SubQueryPlan schema. "
                        "Do NOT wrap it in markdown code fences. Do NOT add any preamble or trailing text. "
                        "Do NOT use double braces '{{' or extra wrapper brackets.\n\n"
                        "CONVERSATION CONTEXT:\n"
                        "{conversation_context}\n\n"
                        "CURRENT USER MESSAGE:\n{current_message}"
                    ),
                    "expected_output": "A validated SubQueryPlan object with search_type and sub_queries list.",
                },
            },
            {
                "template_id": "task_metric_evaluation",
                "prompt_type": PromptType.TASK,
                "payload": {
                    "description_template": (
                        "TASK INSTRUCTIONS:\n"
                        "1. Call tool 'Fetch Orchestration Telemetry from API' with hours={lookback_hours}.\n"
                        "2. Read the compact TOON telemetry returned by the tool.\n"
                        "3. Produce a JSON object with EXACTLY these two string fields:\n"
                        "   - evaluation_summary_narrative (string): Just summarize the performance of the agents of semantic and hybrid agents in terms of tokens uasge, latency and concluding which agent is performing better along with reason\n"
                        "   - optimization_recommendations (string): Just tell the good feedback count and bad feedback count of hybrid and semantic agent and conclude which is performing better \n\n"
                        "STRICT OUTPUT RULES:\n"
                        "- Output ONLY the JSON object. No markdown code fences. No preamble. "
                        "No trailing text. No extra fields.\n"
                        "- Both field values must be non-empty strings.\n"
                        "- Valid JSON only: one opening brace, one closing brace, two string values.\n\n"
                        "EXAMPLE SHAPE (structure only, not content):\n"
                        '{"evaluation_summary_narrative": "...", "optimization_recommendations": "..."}\n\n'
                        "PRIOR EVALUATION MEMORY:\n{prior_memory_context}"
                    ),
                    "expected_output": (
                        "A JSON object with exactly two string fields: "
                        "evaluation_summary_narrative and optimization_recommendations."
                    ),
                },
            },
            {
                "template_id": "task_dynamo_analytics",
                "prompt_type": PromptType.TASK,
                "payload": {
                    "description_template": (
                        "USER ANALYTICAL REQUEST:\n{user_query}\n\n"
                        "INSTRUCTIONS:\n"
                        "1. Write Python code to query the DynamoDB table using `table.query()` or `table.scan()`.\n"
                        "2. Convert results to a pandas DataFrame (`pd.DataFrame(records)`) for filtering, sorting, or aggregations.\n"
                        "3. Execute the code using the 'Execute Python Code in DynamoDB Sandbox' tool.\n"
                        "4. Analyze the output and provide a clear, well-formatted response with exact numbers and tables."
                    ),
                    "expected_output": "A comprehensive data analysis answering the user's question with exact figures and data points.",
                },
            },
            {
                "template_id": "task_dynamic_dynamo_query",
                "prompt_type": PromptType.TASK,
                "payload": {
                    "description_template": (
                        "USER QUERY / ANALYTICS REQUEST:\n"
                        "\"{user_query}\"\n\n"
                        "INSTRUCTIONS:\n"
                        "1. Determine whether a `table.query()` (via GSI SearchTypeTimestampIndex) or `table.scan()` with `FilterExpression` is best.\n"
                        "2. Write a Python script to fetch the matching items from `table`, process the data, and `print()` the result clearly.\n"
                        "3. Run the code via the 'Execute Python Code in DynamoDB Sandbox' tool.\n"
                        "4. Return the final answer clearly explaining the retrieved data, exact counts, and metrics.\n"
                        "5. Return ONLY the final natural language answer in plain text.\n"
                        "6. Do NOT include the Python code script in your final response.\n"
                        "7. Do NOT include raw JSON dumps or query strategy preambles.\n"
                        "8. State the findings, counts, and numbers directly and clearly."
                    ),
                    "expected_output": "A clean, direct natural language answer in plain text or bullet points",
                },
            },
            {
                "template_id": "task_dynamic_firebase_query",
                "prompt_type": PromptType.TASK,
                "payload": {
                    "description_template": (
                        "USER QUERY / FIREBASE REQUEST:\n"
                        "\"{user_query}\"\n\n"
                        "INSTRUCTIONS:\n"
                        "1. Determine the relevant Firestore collection/document to query using `db.collection(...)`.\n"
                        "2. Write a Python script to fetch the matching documents, process the attributes, and `print()` the results clearly.\n"
                        "3. Run the code via the 'Execute Python Code in Firebase Sandbox' tool.\n"
                        "4. Return the final answer clearly explaining the retrieved data, counts, or values.\n"
                        "5. Return ONLY the final natural language answer in plain text.\n"
                        "6. Do NOT include the Python code script in your final response.\n"
                        "7. State the findings directly and clearly."
                    ),
                    "expected_output": "A clean, direct natural language answer in plain text summarizing the Firebase/Firestore data.",
                },
            },
        ]

        return [PromptTemplateSchema(**item) for item in raw_definitions]


# ==============================================================================
# 4. ORCHESTRATION SERVICE (Dependency Inversion: High-Level Business Logic)
# ==============================================================================

class PromptSeedingService:
    """Orchestrates validation, serialization, and batch-uploading of prompts."""

    def __init__(self, repository: IPromptRepository, registry: IPromptRegistry) -> None:
        self._repository = repository
        self._registry = registry

    def seed(self) -> int:
        logger.info("Extracting and validating prompt catalog...")
        templates = self._registry.get_all_templates()
        logger.info(f"Successfully validated {len(templates)} templates with Pydantic.")

        logger.info("Committing batch write to Firestore...")
        count = self._repository.save_batch(templates)
        logger.info(f"✅ Successfully persisted {count} prompt templates to Firestore!")
        return count


# ==============================================================================
# 5. ENTRY POINT
# ==============================================================================

def get_client() -> firestore.Client:
    """Initializes Firestore client using application credentials."""
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if key_path and os.path.exists(key_path):
        return firestore.Client.from_service_account_json(key_path)
    return firestore.Client(project=project_id)


def main() -> None:
    try:
        db = get_client()
        repo = FirestorePromptRepository(client=db, collection_name="prompt_template")
        registry = CodebasePromptRegistry()
        service = PromptSeedingService(repository=repo, registry=registry)

        total_seeded = service.seed()
        print("\n" + "=" * 70)
        print(f"🎉 SEEDING COMPLETE: {total_seeded} PROMPTS SAVED TO 'prompt_template'")
        print("=" * 70)

    except Exception as exc:
        logger.error(f"❌ Seeding failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()