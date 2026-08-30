# from __future__ import annotations

# import os
# import logging
# from dataclasses import dataclass, field
# from crewai import LLM

# logger = logging.getLogger(__name__)


# def _bedrock_model_id() -> str:
#     # Ensure it has the openai/ prefix for LiteLLM
#     model = os.getenv("BEDROCK_MANTLE_AGENTIC_MODEL", "openai.gpt-oss-safeguard-20b")
#     if not model.startswith("openai/"):
#         return f"openai/{model}"
#     return model


# @dataclass(frozen=True)
# class OrchestrationConfig:
#     orchestrator_model: str = field(default_factory=_bedrock_model_id)
#     rewriter_model: str = field(default_factory=_bedrock_model_id)
#     max_sub_queries: int = 3
#     min_top_k: int = 1
#     max_top_k: int = 5
#     default_top_k: int = 2
#     max_history_turns: int = 4
#     guardrail_max_retries: int = 1
#     verbose: bool = True
#     sqs_queue_url: str = os.getenv("METRICS_SQS_QUEUE_URL", "")
#     dynamodb_metrics_table: str = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")


# DEFAULT_CONFIG = OrchestrationConfig()

# def build_llm(model_name: str, temperature: float | None = None) -> LLM:
#     """
#     Points CrewAI's LLM at the AWS Bedrock Mantle OpenAI-compatible gateway.
#     """
#     logger.info(f"---> Initializing CrewAI LLM with model: {model_name}")
    
#     return LLM(
#         model=model_name,
#         base_url=os.getenv(
#             "BEDROCK_MANTLE_BASE_URL",
#             "https://bedrock-mantle.ap-south-1.api.aws/v1",
#         ),
#         api_key=os.getenv("APIKEYFORBEDROCK"),
#         timeout=int(os.getenv("TIMEOUT", "120")),
#         max_retries=int(os.getenv("MAXRETRIES", "3")),
#         temperature=(
#             temperature if temperature is not None else float(os.getenv("TEMPERATURE", "0.0"))
#         ),
#     )
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from crewai import LLM
from .prompt_loader import prompt_loader

logger = logging.getLogger(__name__)


def _get_model(role_key: str, default_model: str) -> str:
    """Helper to dynamically resolve model IDs from PromptLoader / Firestore."""
    return prompt_loader.get_active_model(role_key, default_model)


@dataclass(frozen=True)
class OrchestrationConfig:
    # 1. Master Query Orchestrator -> Voxtral Mini 3B 2507 ($0.05 / $0.05)
    orchestrator_model: str = field(
        default_factory=lambda: _get_model("orchestrator_model", "mistral.voxtral-mini-3b-2507")
    )
    # 2. Semantic & Hybrid Rewriters -> Voxtral Mini 3B 2507 ($0.05 / $0.05)
    rewriter_model: str = field(
        default_factory=lambda: _get_model("rewriter_model", "mistral.voxtral-mini-3b-2507")
    )
    # 3. Telemetry Metric Collector -> Gemma 3 4B IT ($0.05 / $0.09)
    metric_collector_model: str = field(
        default_factory=lambda: _get_model("metric_collector_model", "google.gemma-3-4b-it")
    )
    # 4. Multi-Agent Discussion Crew -> GPT OSS Safeguard 120B ($0.18 / $0.71)
    discussion_model: str = field(
        default_factory=lambda: _get_model("discussion_model", "openai.gpt-oss-safeguard-120b")
    )

    max_sub_queries: int = 3
    min_top_k: int = 1
    max_top_k: int = 5
    default_top_k: int = 2
    max_history_turns: int = 4
    guardrail_max_retries: int = 1
    verbose: bool = True
    sqs_queue_url: str = os.getenv("METRICS_SQS_QUEUE_URL", "")
    dynamodb_metrics_table: str = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")


DEFAULT_CONFIG = OrchestrationConfig()


def build_llm(model_name: str, temperature: float | None = None) -> LLM:
    """
    Points CrewAI's LLM at the AWS Bedrock Mantle OpenAI-compatible gateway.
    Automatically ensures the 'openai/' prefix is present for LiteLLM routing.
    """
    formatted_model = model_name if model_name.startswith("openai/") else f"openai/{model_name}"
    logger.info(f"---> Initializing CrewAI LLM with model: {formatted_model}")

    return LLM(
        model=formatted_model,
        base_url=os.getenv(
            "BEDROCK_MANTLE_BASE_URL",
            "https://bedrock-mantle.ap-south-1.api.aws/v1",
        ),
        api_key=os.getenv("APIKEYFORBEDROCK"),
        timeout=int(os.getenv("TIMEOUT", "120")),
        max_retries=int(os.getenv("MAXRETRIES", "3")),
        temperature=(
            temperature if temperature is not None else float(os.getenv("TEMPERATURE", "0.0"))
        ),
    )