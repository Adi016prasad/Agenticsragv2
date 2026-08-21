# """
# Task factories.

# Optimized for LLM Prompt-Prefix Caching (Static instructions FIRST, Dynamic inputs LAST).
# """
# from typing import Any, List, Tuple
# import re
# from crewai import Agent, Task, TaskOutput
# import json
# from .config import OrchestrationConfig
# from .models import Message, SearchDecision, SubQueryPlan, SystemPerformanceEvaluation


# def _format_history(history: List[Message], max_turns: int = 4) -> str:
#     if not history:
#         return "(no prior conversation)"
#     recent_history = history[-max_turns:]
#     return "\n".join(f"{m.role.value.upper()}: {m.content}" for m in recent_history)


# def build_classification_task(
#     agent: Agent,
#     current_message: str,
#     history: List[Message],
#     config: OrchestrationConfig,
# ) -> Task:
#     """Task for Master Orchestrator: Static rules FIRST for prompt caching."""

#     def guardrail(result: TaskOutput) -> Tuple[bool, Any]:
#         if result.pydantic is None:
#             return False, "Output must conform to the SearchDecision schema."
#         return True, result.pydantic

#     return Task(
#         description=(
#             # 1. STATIC RULES (Always Cached across all users & turns)
#             "TASK INSTRUCTIONS:\n"
#             "Classify the user's request for vector retrieval.\n"
#             "• Return search_type='semantic' for open-ended, conceptual, or paraphrastic questions.\n"
#             "• Return search_type='hybrid' when the query relies on exact keywords, identifiers, "
#             "codes, product names, numeric filters, dates, or negations.\n"
#             "• Set requires_decomposition=true if the message bundles more than one distinct information need.\n\n"
#             "CRITICAL: Output a valid single JSON object conforming strictly to the SearchDecision schema. "
#             "Do NOT use double braces '{{' or extra wrapper brackets.\n\n"
#             # 2. SEMI-STATIC CONVERSATION HISTORY (Cached within multi-turn sessions)
#             "CONVERSATION CONTEXT:\n"
#             f"{_format_history(history, config.max_history_turns)}\n\n"
#             # 3. DYNAMIC INPUT (At the very end)
#             f"CURRENT USER MESSAGE:\n{current_message}"
#         ),
#         expected_output="A validated SearchDecision object with fields: search_type, reasoning, requires_decomposition.",
#         agent=agent,
#         output_pydantic=SearchDecision,
#         guardrail=guardrail,
#         guardrail_max_retries=config.guardrail_max_retries,
#     )


# def build_rewrite_task(
#     agent: Agent,
#     current_message: str,
#     history: List[Message],
#     search_type_label: str,
#     config: OrchestrationConfig,
# ) -> Task:
#     """Task for Rewriter: Static rules FIRST for prompt caching."""

#     def guardrail(result: TaskOutput) -> Tuple[bool, Any]:
#         if result.pydantic is None:
#             return False, "Output must conform to the SubQueryPlan schema."
#         plan: SubQueryPlan = result.pydantic
#         if not (1 <= len(plan.sub_queries) <= config.max_sub_queries):
#             return False, f"sub_queries must contain 1 to {config.max_sub_queries} items."
#         for sq in plan.sub_queries:
#             if not (config.min_top_k <= sq.top_k <= config.max_top_k):
#                 return (
#                     False,
#                     f"top_k for sub-query '{sq.query}' must be between "
#                     f"{config.min_top_k} and {config.max_top_k} (got {sq.top_k}).",
#                 )
#         if plan.search_type.value != search_type_label:
#             return False, f"search_type must be '{search_type_label}'."
#         return True, plan

#     return Task(
#         description=(
#             # 1. STATIC REWRITER RULES (Always Cached)
#             f"TASK INSTRUCTIONS (RETRIEVAL STRATEGY: {search_type_label.upper()}):\n"
#             f"1. Rewrite the user's request into 1 to {config.max_sub_queries} self-contained sub-queries.\n"
#             "2. Resolve pronouns and ellipsis using conversation context so each sub-query stands completely alone.\n"
#             f"3. For each sub-query, assign a top_k between {config.min_top_k} and {config.max_top_k} "
#             f"(default around {config.default_top_k}): narrow lookups get smaller top_k, broad lookups get larger top_k.\n"
#             f"4. Set search_type='{search_type_label}' on output.\n\n"
#             "CRITICAL: Output a valid single JSON object conforming strictly to the SubQueryPlan schema. "
#             "Do NOT use double braces '{{' or extra wrapper brackets.\n\n"
#             # 2. SEMI-STATIC CONVERSATION HISTORY (Cached within session)
#             "CONVERSATION CONTEXT:\n"
#             f"{_format_history(history, config.max_history_turns)}\n\n"
#             # 3. DYNAMIC INPUT (At the end)
#             f"CURRENT USER MESSAGE:\n{current_message}"
#         ),
#         expected_output="A validated SubQueryPlan object with search_type and sub_queries list.",
#         agent=agent,
#         output_pydantic=SubQueryPlan,
#         guardrail=guardrail,
#         guardrail_max_retries=config.guardrail_max_retries,
#     )

# def build_metric_evaluation_task(
#     agent: Agent,
#     lookback_hours: float = 0.25,
#     prior_memory_context: str = "",
# ) -> Task:
#     """Task for Metric Collector with intelligent Attempt-1 guardrail parsing."""

#     def robust_guardrail(result: TaskOutput) -> Tuple[bool, Any]:
#         # 1. If CrewAI parsed it cleanly, accept immediately
#         if result.pydantic is not None:
#             return True, result.pydantic

#         # 2. If CrewAI missed due to markdown text, extract and parse JSON manually!
#         try:
#             raw_text = result.raw.strip()
#             # Strip markdown backticks if present
#             if "```" in raw_text:
#                 match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
#                 if match:
#                     raw_text = match.group(1).strip()

#             # Parse JSON and validate against Pydantic model
#             parsed_dict = json.loads(raw_text)
#             validated_obj = SystemPerformanceEvaluation.model_validate(parsed_dict)
            
#             # 🎯 Success on Attempt 1!
#             return True, validated_obj
#         except Exception as exc:
#             return False, f"Failed to parse JSON into SystemPerformanceEvaluation: {exc}"

#     return Task(
#         description=(
#             "TASK INSTRUCTIONS:\n"
#             f"1. Call tool 'Fetch Orchestration Telemetry from API' with hours={lookback_hours}.\n"
#             "2. Read the compact TOON telemetry data.\n"
#             "3. Synthesize an 'evaluation_summary_narrative' string: Explain what happened in this window, "
#             "compare it with the PRIOR EVALUATION MEMORY, and state the main action needed.\n"
#             "4. Output ONLY valid JSON matching the SystemPerformanceEvaluation schema.\n\n"
#             f"{prior_memory_context}"
#         ),
#         expected_output="A validated SystemPerformanceEvaluation JSON object.",
#         agent=agent,
#         output_pydantic=SystemPerformanceEvaluation,
#         guardrail=robust_guardrail,
#         guardrail_max_retries=1,
#     )
"""
Task factories.

Optimized for LLM Prompt-Prefix Caching (Static instructions FIRST, Dynamic inputs LAST).

Guardrails: every task uses `_make_robust_guardrail`, which first tries the
CrewAI-parsed pydantic object and, on failure, extracts JSON from the raw
LLM output (handling markdown fences and preamble/trailing text) and
validates it manually. This makes guardrails succeed on attempt 1 in the
vast majority of cases, so `guardrail_max_retries=1` is enough as a safety
net rather than the primary recovery mechanism.
"""

import json
import re
from typing import Any, Callable, List, Optional, Tuple, Type

from crewai import Agent, Task, TaskOutput
from pydantic import BaseModel

from .config import OrchestrationConfig
from .models import Message, SearchDecision, SubQueryPlan, SystemPerformanceEvaluation


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

    Order of attempts:
      1. Fenced markdown block:  ```json ... ```  or  ``` ... ```
      2. First '{' to last '}' substring (handles preamble + trailing text)
      3. Fall back to the raw text as-is (may already be clean JSON)
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

    return text  # last resort — let json.loads decide


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

    `extra_validation` returns (ok, error_message). When ok, the message is
    ignored and the validated pydantic object is returned to CrewAI.
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


# ---------------------------------------------------------------------------
# Task factories
# ---------------------------------------------------------------------------

def build_classification_task(
    agent: Agent,
    current_message: str,
    history: List[Message],
    config: OrchestrationConfig,
) -> Task:
    """Master Orchestrator: classify retrieval strategy. Static rules FIRST for caching."""

    return Task(
        description=(
            # 1. STATIC RULES (cached across users & turns)
            "TASK INSTRUCTIONS:\n"
            "Classify the user's request for vector retrieval.\n"
            "• Return search_type='semantic' for open-ended, conceptual, or paraphrastic questions.\n"
            "• Return search_type='hybrid' when the query relies on exact keywords, identifiers, "
            "codes, product names, numeric filters, dates, or negations.\n"
            "• Set requires_decomposition=true if the message bundles more than one distinct information need.\n\n"
            "CRITICAL: Output a valid single JSON object conforming strictly to the SearchDecision schema. "
            "Do NOT wrap it in markdown code fences. Do NOT add any preamble or trailing text. "
            "Do NOT use double braces '{{' or extra wrapper brackets.\n\n"
            # 2. SEMI-STATIC CONVERSATION HISTORY (cached within session)
            "CONVERSATION CONTEXT:\n"
            f"{_format_history(history, config.max_history_turns)}\n\n"
            # 3. DYNAMIC INPUT (last)
            f"CURRENT USER MESSAGE:\n{current_message}"
        ),
        expected_output=(
            "A validated SearchDecision object with fields: "
            "search_type, reasoning, requires_decomposition."
        ),
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
    """Rewriter: rewrite into 1..N self-contained sub-queries with top_k. Static rules FIRST."""

    def rewrite_business_rules(plan: SubQueryPlan) -> Tuple[bool, str]:
        if not (1 <= len(plan.sub_queries) <= config.max_sub_queries):
            return False, f"sub_queries must contain 1 to {config.max_sub_queries} items."
        for sq in plan.sub_queries:
            if not (config.min_top_k <= sq.top_k <= config.max_top_k):
                return False, (
                    f"top_k for sub-query '{sq.query}' must be between "
                    f"{config.min_top_k} and {config.max_top_k} (got {sq.top_k})."
                )
        # `search_type` may be enum or string depending on parse path — handle both
        actual = plan.search_type.value if hasattr(plan.search_type, "value") else plan.search_type
        if actual != search_type_label:
            return False, f"search_type must be '{search_type_label}' (got '{actual}')."
        return True, ""

    return Task(
        description=(
            # 1. STATIC REWRITER RULES (cached)
            f"TASK INSTRUCTIONS (RETRIEVAL STRATEGY: {search_type_label.upper()}):\n"
            f"1. Rewrite the user's request into 1 to {config.max_sub_queries} self-contained sub-queries.\n"
            "2. Resolve pronouns and ellipsis using conversation context so each sub-query stands completely alone.\n"
            f"3. For each sub-query, assign a top_k between {config.min_top_k} and {config.max_top_k} "
            f"(default around {config.default_top_k}): narrow lookups get smaller top_k, broad lookups get larger top_k.\n"
            f"4. Set search_type='{search_type_label}' on output.\n\n"
            "CRITICAL: Output a valid single JSON object conforming strictly to the SubQueryPlan schema. "
            "Do NOT wrap it in markdown code fences. Do NOT add any preamble or trailing text. "
            "Do NOT use double braces '{{' or extra wrapper brackets.\n\n"
            # 2. SEMI-STATIC CONVERSATION HISTORY (cached within session)
            "CONVERSATION CONTEXT:\n"
            f"{_format_history(history, config.max_history_turns)}\n\n"
            # 3. DYNAMIC INPUT (last)
            f"CURRENT USER MESSAGE:\n{current_message}"
        ),
        expected_output="A validated SubQueryPlan object with search_type and sub_queries list.",
        agent=agent,
        output_pydantic=SubQueryPlan,
        guardrail=_make_robust_guardrail(SubQueryPlan, extra_validation=rewrite_business_rules),
        guardrail_max_retries=config.guardrail_max_retries,
    )


# def build_metric_evaluation_task(
#     agent: Agent,
#     lookback_hours: float = 0.25,
#     prior_memory_context: str = "",
# ) -> Task:
#     """Metric Collector: telemetry synthesis with the same robust guardrail as the others."""

#     return Task(
#         description=(
#             "TASK INSTRUCTIONS:\n"
#             f"1. Call tool 'Fetch Orchestration Telemetry from API' with hours={lookback_hours}.\n"
#             "2. Read the compact TOON telemetry data.\n"
#             "3. Synthesize an 'evaluation_summary_narrative' string: Explain what happened in this window, "
#             "compare it with the PRIOR EVALUATION MEMORY, and state the main action needed.\n"
#             "4. Output ONLY valid JSON matching the SystemPerformanceEvaluation schema. "
#             "Do NOT wrap it in markdown code fences and do NOT add preamble or trailing text.\n\n"
#             f"{prior_memory_context}"
#         ),
#         expected_output="A validated SystemPerformanceEvaluation JSON object.",
#         agent=agent,
#         output_pydantic=SystemPerformanceEvaluation,
#         guardrail=_make_robust_guardrail(SystemPerformanceEvaluation),
#         guardrail_max_retries=1
#     )

def build_metric_evaluation_task(
    agent: Agent,
    lookback_hours: float = 0.25,
    prior_memory_context: str = "",
) -> Task:
    """Metric Collector: telemetry synthesis into two prose fields."""

    return Task(
        description=(
            "TASK INSTRUCTIONS:\n"
            f"1. Call tool 'Fetch Orchestration Telemetry from API' with hours={lookback_hours}.\n"
            "2. Read the compact TOON telemetry returned by the tool.\n"
            "3. Produce a JSON object with EXACTLY these two string fields:\n"
            "   - evaluation_summary_narrative (string): prose covering what "
            "happened in this window, how it compares with the PRIOR EVALUATION "
            "MEMORY below, and the primary bottleneck. Multi-paragraph is fine.\n"
            "   - optimization_recommendations (string): prose containing concrete, "
            "actionable adjustments — prompt tweaks, top_k changes, model or "
            "routing changes. Use dashes or numbered lines inside the string if "
            "useful.\n\n"
            "STRICT OUTPUT RULES:\n"
            "- Output ONLY the JSON object. No markdown code fences. No preamble. "
            "No trailing text. No extra fields.\n"
            "- Both field values must be non-empty strings.\n"
            "- Valid JSON only: one opening brace, one closing brace, two string "
            "values.\n\n"
            "EXAMPLE SHAPE (structure only, not content):\n"
            '{"evaluation_summary_narrative": "...", "optimization_recommendations": "..."}\n\n'
            f"PRIOR EVALUATION MEMORY:\n{prior_memory_context}"
        ),
        expected_output=(
            "A JSON object with exactly two string fields: "
            "evaluation_summary_narrative and optimization_recommendations."
        ),
        agent=agent,
        output_pydantic=SystemPerformanceEvaluation,
        guardrail=_make_robust_guardrail(SystemPerformanceEvaluation),
        guardrail_max_retries=1,
    )

def build_dynamo_analytics_task(agent: Agent, user_query: str) -> Task:
    """Task for executing dynamic Python queries against DynamoDB."""
    return Task(
        description=(
            f"USER ANALYTICAL REQUEST:\n{user_query}\n\n"
            "INSTRUCTIONS:\n"
            "1. Write Python code to query the DynamoDB table using `table.query()` or `table.scan()`.\n"
            "2. Convert results to a pandas DataFrame (`pd.DataFrame(records)`) for filtering, sorting, or aggregations.\n"
            "3. Execute the code using the 'Execute Python Code in DynamoDB Sandbox' tool.\n"
            "4. Analyze the output and provide a clear, well-formatted response with exact numbers and tables."
        ),
        expected_output="A comprehensive data analysis answering the user's question with exact figures and data points.",
        agent=agent,
    )

def build_dynamic_dynamo_query_task(agent: Agent, user_query: str) -> Task:
    """Task that directs the agent to write and execute custom DynamoDB Python code."""
    return Task(
        description=(
            f"USER QUERY / ANALYTICS REQUEST:\n"
            f"\"{user_query}\"\n\n"
            "INSTRUCTIONS:\n"
            "1. Determine whether a `table.query()` (via GSI SearchTypeTimestampIndex) or `table.scan()` with `FilterExpression` is best.\n"
            "2. Write a Python script to fetch the matching items from `table`, process the data, and `print()` the result clearly.\n"
            "3. Run the code via the 'Execute Python Code in DynamoDB Sandbox' tool.\n"
            "4. Return the final answer clearly explaining the retrieved data, exact counts, and metrics."
            "5. Return ONLY the final natural language answer in plain text.\n"
            "6. Do NOT include the Python code script in your final response.\n"
            "7. Do NOT include raw JSON dumps or query strategy preambles.\n"
            "8. State the findings, counts, and numbers directly and clearly."
        ),
        expected_output="A clean, direct natural language answer in plain text or bullet points",
        agent=agent,
    )