"""
APIRouter handling SRE telemetry, Prometheus metrics, and Admin approvals.
Contains the HTML page renderer for structured user rejection feedback.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse, HTMLResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from container import get_container, AppContainer
from agenticPipeline.crewai_agents.prompt_loader import prompt_loader
from agenticPipeline.crewai_agents.agentic_prometheus_metrics import AGENTIC_FEEDBACK_TOTAL
from dependencies import FeedbackRequest, FeedbackPublisher, get_feedback_publisher, BaseCache, get_cache, TTL

logger = logging.getLogger("SRERouter")
router = APIRouter(tags=["SRE & Telemetry Engine"])

TABLE_NAME = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")
FEEDBACK_TABLENAME = os.getenv("FEEDBACK_TABLENAME", "FeedbackMetrics")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)
feedbacktable = dynamodb.Table(FEEDBACK_TABLENAME)


def _to_toon(
    hours: float, total_records: int, errors: int,
    sem_count: int, sem_lat: float, sem_tok: float,
    hyb_count: int, hyb_lat: float, hyb_tok: float,
) -> str:
    return (
        f"[TELEMETRY: hours={hours} | records={total_records} | errors={errors}]\n"
        f"SEMANTIC: count={sem_count} | avg_lat_ms={sem_lat} | avg_tokens={sem_tok}\n"
        f"HYBRID: count={hyb_count} | avg_lat_ms={hyb_lat} | avg_tokens={hyb_tok}"
    )


def _query_dynamodb_range(from_ms: int) -> List[Dict[str, Any]]:
    records = []
    for s_type in ["semantic", "hybrid"]:
        try:
            response = table.query(
                IndexName="SearchTypeTimestampIndex",
                KeyConditionExpression=Key("search_type").eq(s_type) & Key("timestamp").gte(from_ms),
            )
            records.extend(response.get("Items", []))
        except Exception as exc:
            logger.warning(f"GSI query for {s_type} failed: {exc}. Using scan fallback.")
            response = table.scan(FilterExpression=Key("timestamp").gte(from_ms))
            records = response.get("Items", [])
            break
    return records


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus Metrics Endpoint", include_in_schema=False)
def get_prometheus_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# 👉 NEW: SERVES THE BEAUTIFUL HTML FEEDBACK PAGE ON REJECTION
@router.get("/optimization/reject-feedback", response_class=HTMLResponse)
async def serve_rejection_feedback_page(
    proposal_id: str = Query(..., description="ID of the staged optimization proposal")
):
    """
    Serves a clean, user-friendly HTML page allowing administrators to 
    submit their rejection reasons directly to the SRE agents.
    """
    submit_url = "/optimization/approve"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🛑 Reject Optimization Proposal</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 40px; display: flex; justify-content: center; }}
            .card {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 500px; width: 100%; border-top: 4px solid #d83b01; }}
            h2 {{ color: #d83b01; margin-top: 0; }}
            p {{ color: #666; font-size: 14px; }}
            textarea {{ width: 100%; height: 120px; padding: 10px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; font-size: 14px; margin-bottom: 20px; resize: none; }}
            button {{ background-color: #d83b01; color: white; border: none; padding: 12px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; width: 100%; font-size: 15px; }}
            button:hover {{ background-color: #b83201; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🛑 Reject Proposal: {proposal_id}</h2>
            <p>Please provide a brief reason for rejecting this optimization proposal. Your feedback will be saved and fed directly into the SRE agents' memory so they can adapt their future strategies.</p>
            
            <form action="{submit_url}" method="get">
                <input type="hidden" name="proposal_id" value="{proposal_id}">
                <input type="hidden" name="decision" value="reject">
                <textarea name="reason" placeholder="e.g., Do not shorten the hybrid prompt backstory. BM25 keyword matching requires those exact terms to prevent satisfaction drops." required></textarea>
                <button type="submit">Submit Rejection & Feedback</button>
            </form>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/optimization/approve")
async def handle_optimization_approval(
    proposal_id: str = Query(..., description="ID of the staged optimization proposal"),
    decision: str = Query(..., description="'approve' or 'reject'"),
    reason: Optional[str] = Query(None, description="Optional rejection reason"),
    container: AppContainer = Depends(get_container),
):
    from google.cloud import firestore
    firestore_client = container.checkpointer.client
    proposal_ref = firestore_client.collection("optimization_proposals").document(proposal_id)
    proposal_doc = proposal_ref.get()

    if not proposal_doc.exists:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

    proposal_data = proposal_doc.to_dict() or {}
    is_approved = decision.lower() in ("approve", "approved", "yes", "true")
    now_iso = datetime.now(timezone.utc).isoformat()

    if is_approved:
        target_template_id = proposal_data.get("target_template_id")
        proposed_payload = proposal_data.get("proposed_payload", {})
        change_reason = proposal_data.get("change_reason", "")

        if target_template_id and proposed_payload:
            if target_template_id == "currentlyactivemodel":
                db_ref = firestore_client.collection("LLM").document("currentlyactivemodel")
                db_ref.set({
                    "model_id": proposed_payload.get("model_id", "openai.gpt-oss-safeguard-20b"),
                    "name": proposed_payload.get("name", "GPT OSS Safeguard 20B"),
                    "input_price_per_1m": proposed_payload.get("input_price_per_1m", 0.08),
                    "output_price_per_1m": proposed_payload.get("output_price_per_1m", 0.24),
                    "max_context": proposed_payload.get("max_context", "128K"),
                    "max_output": proposed_payload.get("max_output", "16K"),
                    "is_active": True,
                    "updated_at": now_iso,
                    "updated_by": f"human_approved_{proposal_id}"
                }, merge=True)
                prompt_loader.invalidate_prompt("currentlyactivemodel")
                logger.info(f"🚀 [HITL Approved] Deployed model: {proposed_payload.get('name')}")
            else:
                db_ref = firestore_client.collection("prompt_template").document(target_template_id)
                current_prompt_snap = db_ref.get()
                previous_payload = current_prompt_snap.to_dict().get("payload") if current_prompt_snap.exists else None

                db_ref.set({
                    "template_id": target_template_id,
                    "payload": proposed_payload,
                    "previous_payload": previous_payload,
                    "version": firestore.Increment(1),
                    "change_reason": change_reason,
                    "canary_status": "in_observation",
                    "canary_expires_at": int(time.time() + 900),
                    "updated_at": now_iso,
                    "updated_by": f"human_approved_{proposal_id}",
                }, merge=True)
                prompt_loader.invalidate_prompt(target_template_id)
                logger.info(f"🚀 [HITL Approved] Deployed prompt '{target_template_id}'. Canary active (15m).")

        proposal_ref.update({"status": "approved", "reviewed_at": now_iso})
        return {"status": "success", "decision": "approved", "target_template_id": target_template_id}
    else:
        # Rejection path with custom feedback reason
        rejection_reason = reason or "Rejected by administrator."
        proposal_ref.update({"status": "rejected", "reviewed_at": now_iso, "rejection_reason": rejection_reason})
        logger.info(f"🛑 [HITL Rejected] Proposal '{proposal_id}' rejected. Reason: {rejection_reason}")
        return {"status": "success", "decision": "rejected", "rejection_reason": rejection_reason}


@router.get("/api/v1/models/catalog", summary="Fetch all LLM models and specs from Firebase", tags=["LLM Catalog"])
async def get_llm_models_catalog(
    container: AppContainer = Depends(get_container),
) -> Dict[str, Any]:
    try:
        firestore_client = container.checkpointer.client
        llm_col = firestore_client.collection("LLM")
        active_doc = llm_col.document("currentlyactivemodel").get()
        currently_active = active_doc.to_dict() if active_doc.exists else {}

        other_doc = llm_col.document("othermodelsavailable").get()
        other_data = other_doc.to_dict() if other_doc.exists else {}
        other_models = other_data.get("models", [])

        return {
            "status": "success",
            "currently_active_model": currently_active,
            "other_models_available": other_models,
            "total_candidate_models": len(other_models),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/telemetry/metrics", response_class=PlainTextResponse, summary="Fetch metrics in dense TOON format")
def get_metrics_by_hours(
    hours: float = Query(default=0.25, ge=0.01, le=168.0)
) -> str:
    now_ms = int(time.time() * 1000)
    from_ms = now_ms - int(hours * 3600 * 1000)
    try:
        items = _query_dynamodb_range(from_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    semantic_latencies, hybrid_latencies, semantic_tokens, hybrid_tokens = [], [], [], []
    errors = 0

    for item in items:
        st = str(item.get("search_type", "")).lower()
        lat, tok = float(item.get("total_latency_ms", 0.0)), int(item.get("total_tokens", 0))
        if item.get("error"):
            errors += 1
        if st == "semantic":
            semantic_latencies.append(lat)
            semantic_tokens.append(tok)
        elif st == "hybrid":
            hybrid_latencies.append(lat)
            hybrid_tokens.append(tok)

    sem_count, hyb_count = len(semantic_latencies), len(hybrid_latencies)
    return _to_toon(
        hours=hours, total_records=len(items), errors=errors,
        sem_count=sem_count,
        sem_lat=round(sum(semantic_latencies) / max(1, sem_count), 2),
        sem_tok=round(sum(semantic_tokens) / max(1, sem_count), 1),
        hyb_count=hyb_count,
        hyb_lat=round(sum(hybrid_latencies) / max(1, hyb_count), 2),
        hyb_tok=round(sum(hybrid_tokens) / max(1, hyb_count), 1),
    )


@router.get("/api/v1/telemetry/feedback")
def get_all_feedback_metrics() -> List[Dict[str, Any]]:
    try:
        return feedbacktable.scan().get("Items", [])
    except Exception as e:
        logger.error(f"Failed to scan: {e}")
        raise


@router.post("/api/v1/feedbackWrite")
async def writeuserfeedback(
    request: FeedbackRequest,
    publisher: FeedbackPublisher = Depends(get_feedback_publisher),
    cache: BaseCache = Depends(get_cache),
) -> Any:
    agent_name, feedback, user_id, session_id, request_id = request.agentName, request.feedback or "", request.user_id, request.session_id, request.requestId
    if not agent_name.strip():
        raise HTTPException(status_code=400, detail="agentName cannot be empty")

    cache_key = f"{user_id}_{session_id}_{request_id}_{feedback}"
    if cache.exists(cache_key):
        return {"message": "Key already exists", "cachekey": cache_key}

    cache_payload = {"agentName": agent_name, "user_id": user_id, "session_id": session_id, "requestId": request_id, "feedback": feedback}
    cache.set(key=cache_key, value=cache_payload, ttl=TTL)

    # Record in Prometheus
    sentiment = "good" if "good" in feedback.lower() or feedback == "1" else "bad"
    AGENTIC_FEEDBACK_TOTAL.labels(agent_name=agent_name, sentiment=sentiment).inc()

    success = publisher.publish(agent_name=agent_name, feedback=feedback)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to publish feedback")

    return {"status": "queued", "cache_key": cache_key}