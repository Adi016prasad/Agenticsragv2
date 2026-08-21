"""
FastAPI Server providing Telemetry in TOON format.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List
import uuid
import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

load_dotenv()

app = FastAPI(title="Orchestration Telemetry API", version="1.0.0")
logger = logging.getLogger("uvicorn.error")

TABLE_NAME = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")
FEEDBACK_TABLENAME = os.getenv("FEEDBACK_TABLENAME", "FeedbackMetrics")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)
feedbacktable = dynamodb.Table(FEEDBACK_TABLENAME)

class FeedbackRequest():
    agentName : str
    feedback : str
    implicitfeedback : str

def _to_toon(
    hours: float,
    total_records: int,
    errors: int,
    sem_count: int,
    sem_lat: float,
    sem_tok: float,
    hyb_count: int,
    hyb_lat: float,
    hyb_tok: float,
) -> str:
    """Converts metric dictionary to dense Token-Oriented Object Notation (TOON)."""
    return (
        f"[TELEMETRY: hours={hours} | records={total_records} | errors={errors}]\n"
        f"SEMANTIC: count={sem_count} | avg_lat_ms={sem_lat} | avg_tokens={sem_tok}\n"
        f"HYBRID: count={hyb_count} | avg_lat_ms={hyb_lat} | avg_tokens={hyb_tok}"
    )


# 👈 THIS WAS MISSING OR PLACED AFTER THE CALL
def _query_dynamodb_range(from_ms: int) -> List[Dict[str, Any]]:
    """Helper to query records newer than from_ms using GSI with scan fallback."""
    records: List[Dict[str, Any]] = []
    for s_type in ["semantic", "hybrid"]:
        try:
            response = table.query(
                IndexName="SearchTypeTimestampIndex",
                KeyConditionExpression=Key("search_type").eq(s_type)
                & Key("timestamp").gte(from_ms),
            )
            records.extend(response.get("Items", []))
        except Exception as exc:
            logger.warning(f"GSI query for {s_type} failed ({exc}). Using scan fallback.")
            response = table.scan(FilterExpression=Key("timestamp").gte(from_ms))
            records = response.get("Items", [])
            break
    return records


@app.get(
    "/api/v1/telemetry/metrics",
    response_class=PlainTextResponse,
    summary="Fetch metrics in dense TOON format",
)
def get_metrics_by_hours(
    hours: float = Query(
        default=0.25,
        ge=0.01,
        le=168.0,
        description="Hours to look back (e.g. 0.25 for 15 mins, 1.0 for 1 hr)",
    )
) -> str:
    """Returns telemetry in dense TOON format for minimal LLM token consumption."""
    now_ms = int(time.time() * 1000)
    lookback_ms = int(hours * 3600 * 1000)
    from_ms = now_ms - lookback_ms

    try:
        items = _query_dynamodb_range(from_ms)
    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    semantic_latencies: List[float] = []
    hybrid_latencies: List[float] = []
    semantic_tokens: List[int] = []
    hybrid_tokens: List[int] = []
    errors = 0

    for item in items:
        st = str(item.get("search_type", "")).lower()
        lat = float(item.get("total_latency_ms", 0.0))
        tok = int(item.get("total_tokens", 0))
        if item.get("error"):
            errors += 1

        if st == "semantic":
            semantic_latencies.append(lat)
            semantic_tokens.append(tok)
        elif st == "hybrid":
            hybrid_latencies.append(lat)
            hybrid_tokens.append(tok)

    sem_count = len(semantic_latencies)
    hyb_count = len(hybrid_latencies)
    sem_lat = round(sum(semantic_latencies) / max(1, sem_count), 2)
    sem_tok = round(sum(semantic_tokens) / max(1, sem_count), 1)
    hyb_lat = round(sum(hybrid_latencies) / max(1, hyb_count), 2)
    hyb_tok = round(sum(hybrid_tokens) / max(1, hyb_count), 1)

    return _to_toon(
        hours=hours,
        total_records=len(items),
        errors=errors,
        sem_count=sem_count,
        sem_lat=sem_lat,
        sem_tok=sem_tok,
        hyb_count=hyb_count,
        hyb_lat=hyb_lat,
        hyb_tok=hyb_tok,
    )

@app.post("/api/v1/feedbackWrite")
async def writeuserfeedback(request : FeedbackRequest) :
    agentname = request.agentName
    feedback = request.feedback or ""
    implicitfeedback = request.implicitfeedback or ""

    item = {
    "id": str(uuid.uuid4()),
    "agentName": agentname,
    "feedback": feedback,
    "implicitfeedback" : implicitfeedback,
    "createdAt": int(time.time())
    }

    try:
        table.put_item(Item=item)
    except Exception as e :
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write feedback: {e.response['Error']['Message']}"
        )

    return {"status": "success", "id": item["id"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)