"""
Lightweight AWS SQS Metrics Emitter.
Decouples user request flow from database persistence.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class SQSMetricsEmitter:
    """Publishes orchestration telemetry directly to AWS SQS."""

    def __init__(self, queue_url: Optional[str] = None, region_name: Optional[str] = None) -> None:
        self._queue_url = queue_url or os.getenv("METRICS_SQS_QUEUE_URL", "")
        self._region = region_name or os.getenv("AWS_REGION", "ap-south-1")
        self._sqs = boto3.client("sqs", region_name=self._region)

    def emit(
        self,
        state: Any,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> bool:
        """Serializes state metrics and publishes to SQS."""
        if not self._queue_url:
            logger.warning("METRICS_SQS_QUEUE_URL is not configured. Skipping SQS push.")
            return False

        req_id = request_id or getattr(state, "request_id", None) or str(uuid.uuid4())
        sess_id = session_id or getattr(state, "session_id", None) or "anonymous"

        # 1. Format Sub-queries
        sub_queries_payload = []
        plan = getattr(state, "plan", None)
        if plan and getattr(plan, "sub_queries", None):
            sub_queries_payload = [
                {"query": sq.query, "top_k": sq.top_k} for sq in plan.sub_queries
            ]

        # 2. Format Agent Breakdown
        agent_metrics_payload: Dict[str, Any] = {}
        metrics = getattr(state, "metrics", None)
        if metrics and hasattr(metrics, "agent_metrics"):
            for name, m in metrics.agent_metrics.items():
                agent_metrics_payload[name] = {
                    "latency_ms": getattr(m, "latency_ms", 0.0),
                    "tokens_per_second": getattr(m, "tokens_per_second", 0.0),
                    "token_expansion_ratio": getattr(m, "token_expansion_ratio", 0.0),
                    "flow_latency_contribution_pct": getattr(m, "flow_latency_contribution_pct", 0.0),
                    "prompt_tokens": getattr(m, "prompt_tokens", 0),
                    "completion_tokens": getattr(m, "completion_tokens", 0),
                    "cached_prompt_tokens": getattr(m, "cached_prompt_tokens", 0),
                    "total_tokens": getattr(m, "total_tokens", 0),
                    "successful_requests": getattr(m, "successful_requests", 0),
                }

        decision = getattr(state, "decision", None)

        # 3. Assemble Complete Telemetry Payload
        payload = {
            "session_id": sess_id,
            "request_id": req_id,
            "timestamp": int(time.time() * 1000),
            "current_message": getattr(state, "current_message", ""),
            "search_type": decision.search_type.value if decision else "unknown",
            "reasoning": getattr(decision, "reasoning", "") if decision else "",
            "requires_decomposition": (
                getattr(decision, "requires_decomposition", False) if decision else False
            ),
            "sub_queries": sub_queries_payload,
            "total_latency_ms": getattr(metrics, "total_latency_ms", 0.0) if metrics else 0.0,
            "total_tokens": getattr(metrics, "total_tokens", 0) if metrics else 0,
            "total_prompt_tokens": getattr(metrics, "total_prompt_tokens", 0) if metrics else 0,
            "total_completion_tokens": getattr(metrics, "total_completion_tokens", 0) if metrics else 0,
            "total_cached_prompt_tokens": getattr(metrics, "total_cached_prompt_tokens", 0) if metrics else 0,
            "total_requests": getattr(metrics, "total_requests", 0) if metrics else 0,
            "agent_metrics": agent_metrics_payload,
            "error": getattr(state, "error", "") or "",
            "eventType" : "metrics"
        }

        try:
            self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(f"📡 Metrics successfully emitted to SQS for request_id: {req_id}")
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.error(f"❌ Failed to push metrics to SQS: {exc}")
            return False