"""
CrewAI Tool: Stages prompt and model optimization proposals in Firestore.
Awaits human approval before applying changes to production.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type

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


class StageProposalInput(BaseModel):
    target_template_id: str = Field(
        ..., 
        description="A single Firestore template ID to update (e.g. 'agent_hybrid_rewriter' or 'task_rewrite'). Do NOT comma-separate."
    )
    recommended_model: str = Field(
        ..., 
        description="The recommended model ID from the 35 available models (e.g. 'openai.gpt-oss-safeguard-20b')."
    )
    change_reason: str = Field(
        ..., 
        description="Clear, specific explanation of WHY the prompt text was changed (e.g. 'Reordered static rules to top to fix 2% cache hit rate and pruned 200 tokens of redundant backstory')."
    )
    proposed_payload: Dict[str, Any] = Field(
        ..., 
        description=(
            "The COMPLETE, READY-TO-USE replacement prompt dictionary. "
            "For an agent: {'role': '...', 'goal': '...', 'backstory': '...'}. "
            "For a task: {'description_template': '...', 'expected_output': '...'}. "
            "Must be the actual full prompt text."
        )
    )
    expected_cost_savings_pct: float = Field(
        default=0.0,
        description="Estimated percentage of cost or token savings (e.g. 45.0)."
    )


class StageOptimizationProposalTool(BaseTool):
    name: str = "Stage Optimization Proposal in Firestore"
    description: str = (
        "Saves the proposed prompt adjustments, change reason, and model selection into Firestore with "
        "status 'awaiting_human_approval'. Returns the unique proposal_id required for the email."
    )
    args_schema: Type[BaseModel] = StageProposalInput

    def _run(
        self,
        target_template_id: str,
        recommended_model: str,
        change_reason: str,
        proposed_payload: Dict[str, Any],
        expected_cost_savings_pct: float = 0.0,
    ) -> str:
        db = _get_firestore_client()
        if not db:
            return "Error: Could not connect to Firestore to stage proposal."

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        proposal_doc = {
            "proposal_id": proposal_id,
            "target_template_id": target_template_id,
            "recommended_model": recommended_model,
            "change_reason": change_reason,
            "proposed_payload": proposed_payload,
            "expected_cost_savings_pct": expected_cost_savings_pct,
            "status": "awaiting_human_approval",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_at": None,
            "rejection_reason": None,
        }

        try:
            db.collection("optimization_proposals").document(proposal_id).set(proposal_doc)
            logger.info(f"✅ Staged optimization proposal {proposal_id} in Firestore.")
            return (
                f"Successfully staged proposal in Firestore with ID: '{proposal_id}'. "
                f"You must now send the approval email containing this proposal_id."
            )
        except Exception as exc:
            logger.error(f"Failed to stage proposal: {exc}", exc_info=True)
            return f"Error staging proposal in Firestore: {exc}"