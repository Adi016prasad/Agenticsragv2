"""
CrewAI Tool: Retrieves recent automated rollback incidents and error traces from Firestore.
Returns data in dense, token-saving TOON format.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Type

from crewai.tools import BaseTool
from google.cloud import firestore
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _get_firestore_client() -> firestore.Client | None:
    try:
        from container import get_firestore_client
        return get_firestore_client()
    except Exception:
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if key_path and os.path.exists(key_path):
            return firestore.Client.from_service_account_json(key_path)
        return firestore.Client(project=project_id)


def _to_toon_rollbacks(incidents: List[Dict[str, Any]]) -> str:
    """Converts raw incident dictionaries to dense Token-Oriented Object Notation (TOON)."""
    lines = []
    for inc in incidents:
        template = inc.get("template_id", "")
        metrics = inc.get("metrics_snapshot") or {}
        err_pct = metrics.get("error_rate_pct", 0.0)
        lat_ms = metrics.get("p95_latency_ms", 0.0)
        raw_traces = inc.get("sample_error_traces") or []
        clean_traces = []
        for t in raw_traces[:7]:
            short_t = str(t).replace("\n", " ").strip()
            short_t = short_t[:90] + "..." if len(short_t) > 90 else short_t
            clean_traces.append(short_t)

        lines.append(
            f"[template={template} | err_pct={err_pct} | lat_ms={lat_ms} | traces={clean_traces}]"
        )
    return "\n".join(lines)


class ReadRollbackInput(BaseModel):
    limit: int = Field(default=3, description="Number of recent rollback incidents to fetch.")


class ReadRollbackIncidentsTool(BaseTool):
    name: str = "Read Canary Rollback Incidents"
    description: str = (
        "Fetches recent automated rollback reports, metrics violations, and raw error traces. "
        "Use this to conduct post-mortem analysis and understand why previous deployments failed."
    )
    args_schema: Type[BaseModel] = ReadRollbackInput

    def _run(self, limit: int = 3) -> str:
        db = _get_firestore_client()
        if not db:
            return "No prior rollback incident database connection available."

        try:
            docs = (
                db.collection("canary_rollbacks")
                .where("status", "==", "pending_agent_review")
                .order_by("rolled_back_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )

            incidents = []
            for d in docs:
                data = d.to_dict() or {}
                incidents.append({
                    "template_id": data.get("template_id"),
                    "metrics_snapshot": data.get("metrics_snapshot"),
                    "sample_error_traces": data.get("sample_error_traces"),
                })

            if not incidents:
                return "No recent automated canary rollback incidents recorded."

            return f"Recent Canary Rollback Incidents :\n{_to_toon_rollbacks(incidents)}"

        except Exception as exc:
            logger.warning(f"Could not read rollback incidents: {exc}")
            return f"No prior rollback incidents retrieved ({exc})."