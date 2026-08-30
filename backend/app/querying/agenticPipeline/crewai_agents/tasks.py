"""
Task factories.
Optimized for LLM Prompt-Prefix Caching with Dynamic Prompt Injection via prompt_loader.
"""
import json
import re
from typing import Any, Callable, List, Optional, Tuple, Type

from crewai import Agent, Task, TaskOutput
from pydantic import BaseModel

from .config import OrchestrationConfig
from .models import Message, SearchDecision, SubQueryPlan, SystemPerformanceEvaluation
from .prompt_loader import prompt_loader


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _format_history(history: List[Message], max_turns: int = 4) -> str:
    if not history:
        return "(no prior conversation)"
    recent_history = history[-max_turns:]
    return "\n".join(f"{m.role.value.upper()}: {m.content}" for m in recent_history)


_MARKDOWN_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def extract_json_object(raw_text: str) -> Optional[str]:
    """
    Try several strategies to pull a JSON object out of an LLM's raw output.
    """
    if not raw_text:
        return None
    text = raw_text.strip()

    md_match = _MARKDOWN_JSON_RE.search(text)
    if md_match:
        return md_match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]

    return text


ExtraValidator = Callable[[BaseModel], Tuple[bool, str]]


def _make_robust_guardrail(
    model_cls: Type[BaseModel],
    extra_validation: Optional[ExtraValidator] = None,
) -> Callable[[TaskOutput], Tuple[bool, Any]]:
    """
    Build a guardrail that:
      1. Uses CrewAI's parsed pydantic object if present (fast path).
      2. Otherwise extracts JSON from the raw output and validates manually.
      3. Then runs any task-specific `extra_validation` (business rules).
    """

    def guardrail(result: TaskOutput) -> Tuple[bool, Any]:
        obj: Optional[BaseModel] = None

        # Fast path
        if result.pydantic is not None:
            obj = result.pydantic
        else:
            # Slow path — extract + parse + validate manually
            raw = result.raw or ""
            extracted = extract_json_object(raw)
            if extracted is None:
                return False, (
                    f"No JSON found in {model_cls.__name__} output. "
                    f"Raw prefix: {raw[:200]!r}"
                )
            try:
                parsed = json.loads(extracted)
            except json.JSONDecodeError as exc:
                return False, (
                    f"Could not parse JSON for {model_cls.__name__}: {exc}. "
                    f"Extracted prefix: {extracted[:200]!r}"
                )
            try:
                obj = model_cls.model_validate(parsed)
            except Exception as exc:
                return False, (
                    f"Schema validation failed for {model_cls.__name__}: "
                    f"{type(exc).__name__}: {exc}"
                )

        # Business-rule validation, if any
        if extra_validation is not None:
            ok, err_msg = extra_validation(obj)
            if not ok:
                return False, err_msg

        return True, obj

    return guardrail

def build_classification_task(
    agent: Agent,
    current_message: str,
    config: OrchestrationConfig,
) -> Task:
    """Master Orchestrator: classify retrieval strategy. History removed for cost optimization."""

    default_template = (
        "TASK INSTRUCTIONS:\n"
        "Classify the user's request for vector retrieval.\n"
        "• Return search_type='semantic' for open-ended, conceptual, or paraphrastic questions.\n"
        "• Return search_type='hybrid' when the query relies on exact keywords, identifiers, "
        "codes, product names, numeric filters, dates, or negations.\n"
        "• Set requires_decomposition=true if the message bundles more than one distinct information need.\n\n"
        "CRITICAL: Output a valid single JSON object conforming strictly to the SearchDecision schema. "
        "Do NOT wrap it in markdown code fences. Do NOT add any preamble or trailing text.\n\n"
        "CURRENT USER MESSAGE:\n{current_message}"
    )
    default_expected = (
        "A validated SearchDecision object with fields: "
        "search_type, reasoning, requires_decomposition."
    )

    desc_tmpl, expected = prompt_loader.get_task_prompt(
        template_id="task_classification",
        default_description=default_template,
        default_expected_output=default_expected,
    )

    formatted_description = desc_tmpl.replace("{current_message}", current_message)

    return Task(
        description=formatted_description,
        expected_output=expected,
        agent=agent,
        output_pydantic=SearchDecision,
        guardrail=_make_robust_guardrail(SearchDecision),
        guardrail_max_retries=config.guardrail_max_retries,
    )

def build_rewrite_task(
    agent: Agent,
    current_message: str,
    history: List[Message],
    search_type_label: str,
    config: OrchestrationConfig,
) -> Task:
    """Rewriter: Sub-query rewriting task with dynamically injected prompt."""

    def rewrite_business_rules(plan: SubQueryPlan) -> Tuple[bool, str]:
        if not (1 <= len(plan.sub_queries) <= config.max_sub_queries):
            return False, f"sub_queries must contain 1 to {config.max_sub_queries} items."
        for sq in plan.sub_queries:
            if not (config.min_top_k <= sq.top_k <= config.max_top_k):
                return False, (
                    f"top_k for sub-query '{sq.query}' must be between "
                    f"{config.min_top_k} and {config.max_top_k} (got {sq.top_k})."
                )
        actual = plan.search_type.value if hasattr(plan.search_type, "value") else plan.search_type
        if actual != search_type_label:
            return False, f"search_type must be '{search_type_label}' (got '{actual}')."
        return True, ""

    default_template = (
        "TASK INSTRUCTIONS (RETRIEVAL STRATEGY: {search_type_label_upper}):\n"
        "1. Rewrite the user's request into 1 to {max_sub_queries} self-contained sub-queries.\n"
        "2. Resolve pronouns and ellipsis using conversation context so each sub-query stands completely alone.\n"
        "3. For each sub-query, assign a top_k between {min_top_k} and {max_top_k} "
        "(default around {default_top_k}): narrow lookups get smaller top_k, broad lookups get larger top_k.\n"
        "4. Set search_type='{search_type_label}' on output.\n\n"
        "CRITICAL: Output a valid single JSON object conforming strictly to the SubQueryPlan schema.\n\n"
        "CONVERSATION CONTEXT:\n{conversation_context}\n\n"
        "CURRENT USER MESSAGE:\n{current_message}"
    )
    default_expected = "A validated SubQueryPlan object with search_type and sub_queries list."

    desc_tmpl, expected = prompt_loader.get_task_prompt(
        template_id="task_rewrite",
        default_description=default_template,
        default_expected_output=default_expected,
    )

    # 👉 Safe replacement (Immune to JSON bracket collisions)
    formatted_description = (
        desc_tmpl
        .replace("{search_type_label_upper}", search_type_label.upper())
        .replace("{search_type_label}", search_type_label)
        .replace("{max_sub_queries}", str(config.max_sub_queries))
        .replace("{min_top_k}", str(config.min_top_k))
        .replace("{max_top_k}", str(config.max_top_k))
        .replace("{default_top_k}", str(config.default_top_k))
        .replace("{conversation_context}", _format_history(history, config.max_history_turns))
        .replace("{current_message}", current_message)
    )

    return Task(
        description=formatted_description,
        expected_output=expected,
        agent=agent,
        output_pydantic=SubQueryPlan,
        guardrail=_make_robust_guardrail(SubQueryPlan, extra_validation=rewrite_business_rules),
        guardrail_max_retries=config.guardrail_max_retries,
    )


def build_metric_evaluation_task(
    agent: Agent,
    lookback_hours: float = 0.25,
    prior_memory_context: str = "",
) -> Task:
    """Metric Collector: Telemetry evaluation task with dynamically injected prompt."""

    default_template = (
        "TASK INSTRUCTIONS:\n"
        "1. Call tool 'Fetch Orchestration Telemetry from API' with hours={lookback_hours}.\n"
        "2. Read the compact TOON telemetry returned by the tool.\n"
        "3. Produce a JSON object with EXACTLY these two string fields:\n"
        "   - evaluation_summary_narrative (string)\n"
        "   - optimization_recommendations (string)\n\n"
        "PRIOR EVALUATION MEMORY:\n{prior_memory_context}"
    )
    default_expected = (
        "A JSON object with exactly two string fields: "
        "evaluation_summary_narrative and optimization_recommendations."
    )

    desc_tmpl, expected = prompt_loader.get_task_prompt(
        template_id="task_metric_evaluation",
        default_description=default_template,
        default_expected_output=default_expected,
    )

    # 👉 Safe replacement (Immune to JSON bracket collisions)
    formatted_description = (
        desc_tmpl
        .replace("{lookback_hours}", str(lookback_hours))
        .replace("{prior_memory_context}", prior_memory_context)
    )

    return Task(
        description=formatted_description,
        expected_output=expected,
        agent=agent,
        output_pydantic=SystemPerformanceEvaluation,
        guardrail=_make_robust_guardrail(SystemPerformanceEvaluation),
        guardrail_max_retries=1,
    )


def build_dynamo_analytics_task(agent: Agent, user_query: str) -> Task:
    """Task for executing dynamic Python queries against DynamoDB."""
    default_template = (
        "USER ANALYTICAL REQUEST:\n{user_query}\n\n"
        "INSTRUCTIONS:\n"
        "1. Write Python code to query the DynamoDB table using `table.query()` or `table.scan()`.\n"
        "2. Convert results to a pandas DataFrame (`pd.DataFrame(records)`).\n"
        "3. Execute the code using 'Execute Python Code in DynamoDB Sandbox' tool.\n"
        "4. Print and summarize the findings."
    )
    default_expected = "A comprehensive data analysis answering the user's question with exact figures."

    desc_tmpl, expected = prompt_loader.get_task_prompt(
        template_id="task_dynamo_analytics",
        default_description=default_template,
        default_expected_output=default_expected,
    )

    return Task(
        description=desc_tmpl.replace("{user_query}", user_query),
        expected_output=expected,
        agent=agent,
    )


def build_dynamic_dynamo_query_task(agent: Agent, user_query: str) -> Task:
    """Task that directs the agent to write and execute custom DynamoDB Python code."""
    default_template = (
        "USER QUERY / ANALYTICS REQUEST:\n\"{user_query}\"\n\n"
        "INSTRUCTIONS:\n"
        "1. Write Python code to fetch matching items from `metrics_table` or `feedback_table`.\n"
        "2. Run via 'Execute Python Code in DynamoDB Sandbox' tool.\n"
        "3. Return ONLY the final natural language answer in plain text with no Python code."
    )
    default_expected = "A clean, direct natural language answer in plain text or bullet points"

    desc_tmpl, expected = prompt_loader.get_task_prompt(
        template_id="task_dynamic_dynamo_query",
        default_description=default_template,
        default_expected_output=default_expected,
    )

    return Task(
        description=desc_tmpl.replace("{user_query}", user_query),
        expected_output=expected,
        agent=agent,
    )


def build_dynamic_firebase_query_task(agent: Agent, user_query: str) -> Task:
    """Task that directs the agent to write and execute custom Firebase/Firestore Python code."""
    default_template = (
        "USER QUERY / FIREBASE REQUEST:\n\"{user_query}\"\n\n"
        "INSTRUCTIONS:\n"
        "1. Determine relevant Firestore collection/document to query using `db.collection(...)`.\n"
        "2. Run code via 'Execute Python Code in Firebase Sandbox' tool.\n"
        "3. Return ONLY the final natural language answer in plain text."
    )
    default_expected = "A clean, direct natural language answer in plain text summarizing the Firebase data."

    desc_tmpl, expected = prompt_loader.get_task_prompt(
        template_id="task_dynamic_firebase_query",
        default_description=default_template,
        default_expected_output=default_expected,
    )

    return Task(
        description=desc_tmpl.replace("{user_query}", user_query),
        expected_output=expected,
        agent=agent,
    )