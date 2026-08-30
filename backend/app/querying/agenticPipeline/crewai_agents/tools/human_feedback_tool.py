"""
CrewAI Tool: Retrieves past human feedback & rejection reasons on optimization proposals.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Type

from crewai.tools import BaseTool
from google.cloud import firestore
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _get_firestore_client() -> Optional[firestore.Client]:
    try:
        from container import get_firestore_client
        return get_firestore_client()
    except Exception:
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if key_path and os.path.exists(key_path):
            return firestore.Client.from_service_account_json(key_path)
        return firestore.Client(project=project_id)


class ReadFeedbackInput(BaseModel):
    limit: int = Field(default=5, description="Number of recent proposals/feedbacks to fetch.")


class ReadHumanOptimizationFeedbackTool(BaseTool):
    name: str = "Read Prior Human Optimization Feedback"
    description: str = (
        "Fetches recent human approvals and rejections from Firestore to understand past human guidance "
        "and avoid repeating previously rejected prompt changes."
    )
    args_schema: Type[BaseModel] = ReadFeedbackInput

    def _run(self, limit: int = 5) -> str:
        db = _get_firestore_client()
        if not db:
            return "No prior human feedback database connection available."

        try:
            docs = (
                db.collection("optimization_proposals")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )

            results: List[Dict[str, Any]] = []
            for d in docs:
                data = d.to_dict()
                status = data.get("status", "unknown")
                results.append({
                    "proposal_id": d.id,
                    "target_template": data.get("target_template_id"),
                    "status": status,
                    "rejection_reason": data.get("rejection_reason"),
                    "rationale": data.get("rationale"),
                })

            if not results:
                return "No prior human optimization feedback found (first-time run)."

            return f"Recent Human Feedback & Decisions:\n{results}"
        except Exception as exc:
            logger.warning(f"Could not read human feedback: {exc}")
            return f"No prior feedback history retrieved ({exc})."