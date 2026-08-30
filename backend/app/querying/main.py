# import logging
# import os
# import sys
# import time
# import json
# import uuid
# import asyncio
# from typing import Any, Dict, List, Optional
# from abc import ABC, abstractmethod
# from contextlib import asynccontextmanager
# from datetime import datetime, timezone
# import smtplib
# from email.mime.text import MIMEText

# import boto3
# from boto3.dynamodb.conditions import Key
# from google.cloud import firestore
# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException, Depends, Query
# from fastapi.responses import PlainTextResponse
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from langchain_core.messages import HumanMessage
# from langgraph.types import Command
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
# from fastapi.responses import Response
# from agenticPipeline.crewai_agents.ragas_eval_crew import RagasEvaluationOrchestrator

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# load_dotenv()

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
# )
# logger = logging.getLogger(__name__)

# from nodes import GraphState
# from container import build_container, close_container, get_container, AppContainer
# from agenticPipeline.crewai_agents.config import DEFAULT_CONFIG
# from agenticPipeline.crewai_agents.evaluation_crew import MetricEvaluationCrew
# from agenticPipeline.crewai_agents.tools.feedback_emitter import FeedbackSQSEmitter
# from agenticPipeline.crewai_agents.analytics_crew import DynamoDBQueryCrew
# from agenticPipeline.crewai_agents.agent_discussion_crew import AgentDiscussionCrew
# from agenticPipeline.crewai_agents.prompt_loader import prompt_loader
# from agenticPipeline.crewai_agents.agentic_prometheus_metrics import AGENTIC_FEEDBACK_TOTAL
# from cache import BaseCache, CacheFactory

# TABLE_NAME = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")
# FEEDBACK_TABLENAME = os.getenv("FEEDBACK_TABLENAME", "FeedbackMetrics")
# AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
# table = dynamodb.Table(TABLE_NAME)
# feedbacktable = dynamodb.Table(FEEDBACK_TABLENAME)

# class FeedbackRequest(BaseModel):
#     agentName: str
#     user_id: str
#     session_id: str
#     requestId: str
#     feedback: str = ""

# _cache_instance: BaseCache = CacheFactory.create_cache(
#     provider=os.getenv("CACHE_PROVIDER", "valkey"),
#     host=os.getenv("ELASTICACHE_HOST", "localhost"),
#     port=int(os.getenv("ELASTICACHE_PORT", 6379)),
#     ssl=os.getenv("ELASTICACHE_SSL", "True").lower() == "true",
# )

# TTL = int(os.getenv("TTL", 300000))

# def get_cache() -> BaseCache:
#     return _cache_instance


# class FeedbackPublisher(ABC):
#     @abstractmethod
#     def publish(self, agent_name: str, feedback: str) -> bool:
#         pass


# class SQSFeedbackPublisher(FeedbackPublisher):
#     def __init__(self, emitter: FeedbackSQSEmitter):
#         self._emitter = emitter

#     def publish(self, agent_name: str, feedback: str) -> bool:
#         return self._emitter.emit(agent_name=agent_name, feedback=feedback)


# _feedback_publisher: FeedbackPublisher = SQSFeedbackPublisher(FeedbackSQSEmitter())

# def get_feedback_publisher() -> FeedbackPublisher:
#     return _feedback_publisher


# def _to_toon(
#     hours: float,
#     total_records: int,
#     errors: int,
#     sem_count: int,
#     sem_lat: float,
#     sem_tok: float,
#     hyb_count: int,
#     hyb_lat: float,
#     hyb_tok: float,
# ) -> str:
#     return (
#         f"[TELEMETRY: hours={hours} | records={total_records} | errors={errors}]\n"
#         f"SEMANTIC: count={sem_count} | avg_lat_ms={sem_lat} | avg_tokens={sem_tok}\n"
#         f"HYBRID: count={hyb_count} | avg_lat_ms={hyb_lat} | avg_tokens={hyb_tok}"
#     )


# def _query_dynamodb_range(from_ms: int) -> List[Dict[str, Any]]:
#     records: List[Dict[str, Any]] = []
#     for s_type in ["semantic", "hybrid"]:
#         try:
#             response = table.query(
#                 IndexName="SearchTypeTimestampIndex",
#                 KeyConditionExpression=Key("search_type").eq(s_type)
#                 & Key("timestamp").gte(from_ms),
#             )
#             records.extend(response.get("Items", []))
#         except Exception as exc:
#             logger.warning(f"GSI query for {s_type} failed ({exc}). Using scan fallback.")
#             response = table.scan(FilterExpression=Key("timestamp").gte(from_ms))
#             records = response.get("Items", [])
#             break
#     return records


# # ==============================================================================
# # SRE CRON SCHEDULER JOBS
# # ==============================================================================
# scheduler = AsyncIOScheduler()

# async def run_metric_collector_job():
#     logger.info("Cron starting 15 minute metric collector run")
#     try:
#         eval_crew = MetricEvaluationCrew(config=DEFAULT_CONFIG)
#         report = await asyncio.to_thread(eval_crew.evaluate, lookback_hours=0.25)
#         logger.info(f"Cron metric evaluation summary: {report.evaluation_summary_narrative}")
#         logger.info(f"Cron optimization recommendations: {report.optimization_recommendations}")
#     except Exception as e:
#         logger.error(f"Cron metric collector run failed: {e}", exc_info=True)

# async def run_hourly_agent_optimization_job():
#     """
#     SRE Optimizer Job: Runs every 1 hour.
#     Only triggers the expensive CrewAI Agent Discussion if traffic is HIGH (Saves 100% tokens when idle).
#     """
#     logger.info("🤖 [SRE Optimizer] Checking system traffic threshold...")
#     try:
#         min_requests_threshold = int(os.getenv("MIN_REQUESTS_PER_HOUR", "15"))

#         now_ms = int(time.time() * 1000)
#         one_hour_ms = 3600 * 1000
#         from_ms = now_ms - one_hour_ms

#         recent_items = _query_dynamodb_range(from_ms)
#         traffic_count = len(recent_items)

#         logger.info(f"📊 [SRE Optimizer] Current traffic: {traffic_count} requests/hr (Threshold: {min_requests_threshold})")

#         if traffic_count < min_requests_threshold:
#             logger.info(
#                 f"⏸️ [SRE Optimizer] Skipping hourly discussion. "
#                 f"Traffic is LOW ({traffic_count}/{min_requests_threshold} requests). Saving token budget."
#             )
#             return

#         logger.info(f"🔥 [SRE Optimizer] High traffic detected ({traffic_count} >= {min_requests_threshold}). Launching SRE Agents!")
        
#         discussion_crew = AgentDiscussionCrew(config=DEFAULT_CONFIG)
#         report = await asyncio.to_thread(discussion_crew.run_discussion)
        
#         logger.info(f"✅ [SRE Optimizer] Discussion Complete. Staged & Emailed:\n{report}")

#     except Exception as e:
#         logger.error(f"❌ [SRE Optimizer] Job execution failed: {e}", exc_info=True)
        
# async def run_5_hour_continuous_benchmark_job():
#     """Triggers the 3-Stage Ragas Benchmark every 5 hours."""
#     logger.info("🧪 [SCHEDULER] Triggering 5-Hour Ragas Benchmark Pipeline...")
#     try:
#         orchestrator = RagasEvaluationOrchestrator(config=DEFAULT_CONFIG)
#         await orchestrator.execute_full_benchmark(collection_name="testinghubnew", delay_seconds = 300)
#     except Exception as e:
#         logger.error(f"❌ 5-Hour Benchmark failed: {e}", exc_info=True)

# def send_emergency_rollback_email(template_id: str, error_rate: float, p95_latency: float, reason: str):
#     """Triggers SMTP alert immediately when an automated rollback is executed."""
#     smtp_host = os.getenv("SMTP_HOST")
#     smtp_port = int(os.getenv("SMTP_PORT", "587"))
#     smtp_user = os.getenv("SMTP_USER")
#     smtp_password = os.getenv("SMTP_PASSWORD")
#     approver_email = os.getenv("APPROVER_EMAIL")

#     if not all([smtp_host, smtp_user, smtp_password, approver_email]):
#         logger.warning("SMTP settings missing. Skipping emergency rollback email.")
#         return

#     subject = f"⚠️ [CRITICAL] Automated Rollback Executed: {template_id}"
#     body = (
#         f"==================================================\n"
#         f"🚨 SYSTEM HEALTH ALERT: AUTOMATED ROLLBACK EXECUTED\n"
#         f"==================================================\n\n"
#         f"The newly deployed prompt for '{template_id}' violated production SLAs.\n\n"
#         f"📉 BREACH METRICS (Last 2 minutes):\n"
#         f"- Error Rate: {error_rate:.2f}% (Threshold: > 5.0%)\n"
#         f"- p95 Latency: {p95_latency:.0f}ms (Threshold: > 6000ms)\n\n"
#         f"🛠️ ACTION TAKEN:\n"
#         f"The system has AUTOMATICALLY reverted the prompt for '{template_id}' to the "
#         f"previous stable version and invalidated the in-memory cache.\n\n"
#         f"🔍 INCIDENT DETAILS:\n"
#         f"{reason}\n\n"
#         f"No manual intervention is needed. The stable prompt is live in production."
#     )

#     msg = MIMEText(body)
#     msg["Subject"] = subject
#     msg["From"] = smtp_user
#     msg["To"] = approver_email

#     try:
#         with smtplib.SMTP(smtp_host, smtp_port) as server:
#             server.starttls()
#             server.login(smtp_user, smtp_password)
#             server.sendmail(smtp_user, [approver_email], msg.as_string())
#         logger.info(f"📧 Emergency rollback email sent successfully to {approver_email}")
#     except Exception as exc:
#         logger.error(f"Failed to send emergency rollback email: {exc}")


# async def run_deterministic_canary_watchdog():
#     """
#     SRE Watchdog: Scans DynamoDB telemetry and triggers an instant rollback & email 
#     on SLA breach (error rate > 5% or p95 latency > 6000ms).
#     """
#     logger.info("🛡️ [SRE Watchdog] Checking active canary deployments...")
#     try:
#         db = get_container().checkpointer.client
        
#         # 1. Fetch prompts currently in observation
#         active_canaries = list(
#             db.collection("prompt_template")
#             .where("canary_status", "==", "in_observation")
#             .stream()
#         )
        
#         if not active_canaries:
#             return  # No active canaries -> Exit instantly

#         for doc in active_canaries:
#             data = doc.to_dict()
#             template_id = doc.id
#             expires_at = data.get("canary_expires_at", 0)
#             previous_payload = data.get("previous_payload")
#             current_version = data.get("version", 1)

#             # 2. Query last 2 minutes of telemetry from DynamoDB
#             now_ms = int(time.time() * 1000)
#             two_mins_ago_ms = now_ms - (120 * 1000)
#             items = _query_dynamodb_range(two_mins_ago_ms)

#             if items:
#                 total_reqs = len(items)
#                 error_count = sum(1 for i in items if i.get("error"))
#                 error_rate = (error_count / total_reqs) * 100.0
#                 p95_latency = max([float(i.get("total_latency_ms", 0.0)) for i in items])

#                 # 3. 🚨 CIRCUIT BREAKER: REVERT & EXPELL CACHE ON SLA VIOLATION
#                 if error_rate > 5.0 or p95_latency > 6000.0:
#                     sample_errors = [i.get("error") for i in items if i.get("error")][:3]
#                     reason = (
#                         f"Outage triggered by version {current_version}.\n"
#                         f"Sample error logs from DynamoDB:\n{sample_errors}"
#                     )

#                     # Revert Firestore immediately
#                     doc.reference.update({
#                         "payload": previous_payload,
#                         "canary_status": "rolled_back",
#                         "canary_expires_at": None,
#                         "updated_at": datetime.now(timezone.utc).isoformat(),
#                     })

#                     # Evict from in-memory cache instantly
#                     prompt_loader.invalidate_prompt(template_id)
                    
#                     # Store rollback incident in Firestore
#                     incident_ref = db.collection("canary_rollbacks").document()
#                     incident_ref.set({
#                         "template_id": template_id,
#                         "rolled_back_at": datetime.now(timezone.utc).isoformat(),
#                         "metrics_snapshot": {
#                             "error_rate_pct": round(error_rate, 2),
#                             "p95_latency_ms": round(p95_latency, 2),
#                         },
#                         "sample_error_traces": sample_errors,
#                         "status": "pending_agent_review",
#                     })

#                     # Dispatch immediate alert email
#                     send_emergency_rollback_email(
#                         template_id=template_id,
#                         error_rate=error_rate,
#                         p95_latency=p95_latency,
#                         reason=reason
#                     )
#                     logger.error(f"🛑 [AUTO-ROLLBACK EXECUTED] Reverted '{template_id}' back to stable!")
#                     return

#             # 4. ✅ GRADUATION: Clean bill of health
#             if time.time() >= expires_at:
#                 doc.reference.update({
#                     "canary_status": "stable",
#                     "canary_expires_at": None,
#                 })
#                 logger.info(f"❇️ [Canary Graduated] Template '{template_id}' declared stable.")

#     except Exception as e:
#         logger.error(f"Error in canary watchdog: {e}", exc_info=True)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     container = await build_container()
#     logger.info("-----------------------------------------------")
#     logger.info(container)
#     logger.info("-----------------------------------------------")

#     # Metrics collector
#     scheduler.add_job(run_metric_collector_job, "interval", minutes = 15, id="metric_and_feedback_collector_job")
    
#     # NEW: Hourly Optimization Debate
#     scheduler.add_job(run_hourly_agent_optimization_job, "interval", hours = 1, id="hourly_agent_optimization_job")
    
#     # NEW: 1-Minute SRE Canary Watchdog
#     scheduler.add_job(run_deterministic_canary_watchdog, "interval", minutes = 1, id="canary_watchdog_job")

#     scheduler.add_job(run_5_hour_continuous_benchmark_job, "interval", hours = 5, id="continuous_ragas_benchmark_job")

#     logger.info("5 Hour Continuous Ragas Benchmark Scheduler registered")
    
#     scheduler.start()
#     logger.info("All cron schedulers started successfully.")

#     yield
#     logger.info("Closing down everything")
#     scheduler.shutdown(wait=False)
#     await close_container()


# app = FastAPI(
#     title="LangGraph Complex Workflow Example",
#     version="1.0.0",
#     lifespan=lifespan,
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:3000", "http://localhost:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ==============================================================================
# # API ENDPOINTS
# # ==============================================================================

# @app.get("/metrics", summary="Prometheus Metrics Endpoint", include_in_schema=False)
# def get_prometheus_metrics():
#     return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# @app.get("/optimization/approve")
# async def handle_optimization_approval(
#     proposal_id: str = Query(..., description="ID of the staged optimization proposal"),
#     decision: str = Query(..., description="'approve' or 'reject'"),
#     reason: Optional[str] = Query(None, description="Optional rejection reason / human feedback"),
#     container: AppContainer = Depends(get_container),
# ):
#     """
#     Handles 1-Click human approvals or rejections from the optimization email.
#     """
#     firestore_client = container.checkpointer.client
#     proposal_ref = firestore_client.collection("optimization_proposals").document(proposal_id)
#     proposal_doc = proposal_ref.get()

#     if not proposal_doc.exists:
#         raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

#     proposal_data = proposal_doc.to_dict()
#     is_approved = decision.lower() in ("approve", "approved", "yes", "true")
#     now_iso = datetime.now(timezone.utc).isoformat()

#     if is_approved:
#         target_template_id = proposal_data.get("target_template_id")
#         proposed_payload = proposal_data.get("proposed_payload", {})
#         change_reason = proposal_data.get("change_reason", "")

#         if target_template_id and proposed_payload:
#             prompt_doc_ref = firestore_client.collection("prompt_template").document(target_template_id)
#             current_prompt_snap = prompt_doc_ref.get()
            
#             # 1. Snapshot previous version
#             previous_payload = None
#             if current_prompt_snap.exists:
#                 previous_payload = current_prompt_snap.to_dict().get("payload")

#             # 2. Deploy and activate Canary Check
#             prompt_doc_ref.set({
#                 "template_id": target_template_id,
#                 "payload": proposed_payload,
#                 "previous_payload": previous_payload,
#                 "version": firestore.Increment(1),
#                 "change_reason": change_reason,
#                 "canary_status": "in_observation",
#                 "canary_expires_at": int(time.time() + 900),  # 15 minutes
#                 "updated_at": now_iso,
#                 "updated_by": f"human_approved_{proposal_id}",
#             }, merge=True)

#             # 3. Evict old prompt from cache
#             prompt_loader.invalidate_prompt(target_template_id)
#             logger.info(f"🚀 [Approved] Deployed '{target_template_id}'. Canary active (15m).")

#         proposal_ref.update({
#             "status": "approved",
#             "reviewed_at": now_iso,
#         })

#         return {
#             "status": "success",
#             "decision": "approved",
#             "message": f"Proposal '{proposal_id}' approved! Prompt deployed and 15-minute Canary active.",
#             "target_template_id": target_template_id,
#         }

#     else:
#         # Rejection path
#         rejection_reason = reason or "Rejected by administrator."
#         proposal_ref.update({
#             "status": "rejected",
#             "reviewed_at": now_iso,
#             "rejection_reason": rejection_reason,
#         })
#         logger.info(f"🛑 [Rejected] Proposal '{proposal_id}' rejected. Reason: {rejection_reason}")

#         return {
#             "status": "success",
#             "decision": "rejected",
#             "message": "Proposal rejected. Feedback recorded for future discussions.",
#             "rejection_reason": rejection_reason,
#         }


# @app.get("/api/v1/models/catalog", summary="Fetch all LLM models and specs from Firebase", tags=["LLM Catalog"])
# async def get_llm_models_catalog(
#     container: AppContainer = Depends(get_container),
# ) -> Dict[str, Any]:
#     try:
#         firestore_client = container.checkpointer.client
#         llm_col = firestore_client.collection("LLM")

#         # 1. Fetch currently active model
#         active_doc = llm_col.document("currentlyactivemodel").get()
#         currently_active = active_doc.to_dict() if active_doc.exists else {}

#         # 2. Fetch all other candidate models
#         other_doc = llm_col.document("othermodelsavailable").get()
#         other_data = other_doc.to_dict() if other_doc.exists else {}
#         other_models = other_data.get("models", [])

#         return {
#             "status": "success",
#             "currently_active_model": currently_active,
#             "other_models_available": other_models,
#             "total_candidate_models": len(other_models),
#         }
#     except Exception as exc:
#         logger.error(f"Failed to fetch model catalog: {exc}", exc_info=True)
#         raise HTTPException(status_code=500, detail=str(exc))


# class RequestStructure(BaseModel):
#     session_id : str
#     user_input : str
#     collection_name : str

# @app.get("/approve")
# async def approve_endpoint(
#     session_id: str,
#     decision: str,
#     container: AppContainer = Depends(get_container),
# ):
#     config = {"configurable": {"thread_id": f"user_name_{session_id}"}}
#     try:
#         final_state = await container.query_graph.ainvoke(Command(resume=decision), config=config)
#         status = "approved" if decision.lower() in ("yes", "true", "approve", "approved") else "denied"
#         output = final_state["messages"][-1].content if final_state.get("messages") else ""

#         firestore_client = container.query_graph.checkpointer.client
#         firestore_client.collection("approval_status").document(session_id).set({
#             "session_id": session_id,
#             "status": status,
#             "output": output,
#         })

#         return {"status": status, "output": output}
#     except Exception as e:
#         logger.error(f"Error resuming graph: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/approval-status")
# async def approval_status(
#     session_id: str,
#     container: AppContainer = Depends(get_container),
# ):
#     try:
#         firestore_client = container.query_graph.checkpointer.client
#         doc = firestore_client.collection("approval_status").document(session_id).get()
#         if not doc.exists:
#             return {"status": "awaiting_approval"}
#         data = doc.to_dict()
#         return {"status": data.get("status", "awaiting_approval"), "output": data.get("output", "")}
#     except Exception as e:
#         logger.error(f"Error checking approval: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/chat")
# async def chat_endpoint(
#     request: RequestStructure,
#     container: AppContainer = Depends(get_container),
# ):
#     if not request.user_input.strip():
#         raise HTTPException(status_code=400, detail="user_input cannot be empty.")

#     newRequestId = uuid.uuid4().hex[:8]
#     initial_state: GraphState = {
#         "session_id": request.session_id,
#         "collection_name": request.collection_name,
#         "messages": [HumanMessage(content=request.user_input)],
#         "request_id" : newRequestId
#     }
#     config = {"configurable": {"thread_id": f"user_name_{request.session_id}"}}

#     try:
#         final_state = await container.query_graph.ainvoke(initial_state, config=config)
#         if "__interrupt__" in final_state:
#             return {"status": "awaiting_approval", "detail": final_state["__interrupt__"][0].value}

#         content = final_state["messages"][-1].content
#         try:
#             parsed = json.loads(content)
#             output = parsed["llm_responseLanggraph"] if isinstance(parsed, dict) and "llm_responseLanggraph" in parsed else content
#         except json.JSONDecodeError:
#             output = content

#         return {"output": output}
#     except Exception as e:
#         logger.error(f"Error in chat_endpoint: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/v1/telemetry/metrics", response_class=PlainTextResponse, summary="Fetch metrics in dense TOON format")
# def get_metrics_by_hours(
#     hours: float = Query(default=0.25, ge=0.01, le=168.0)
# ) -> str:
#     now_ms = int(time.time() * 1000)
#     from_ms = now_ms - int(hours * 3600 * 1000)
#     try:
#         items = _query_dynamodb_range(from_ms)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

#     semantic_latencies, hybrid_latencies, semantic_tokens, hybrid_tokens = [], [], [], []
#     errors = 0

#     for item in items:
#         st = str(item.get("search_type", "")).lower()
#         lat, tok = float(item.get("total_latency_ms", 0.0)), int(item.get("total_tokens", 0))
#         if item.get("error"):
#             errors += 1
#         if st == "semantic":
#             semantic_latencies.append(lat)
#             semantic_tokens.append(tok)
#         elif st == "hybrid":
#             hybrid_latencies.append(lat)
#             hybrid_tokens.append(tok)

#     sem_count, hyb_count = len(semantic_latencies), len(hybrid_latencies)
#     return _to_toon(
#         hours=hours,
#         total_records=len(items),
#         errors=errors,
#         sem_count=sem_count,
#         sem_lat=round(sum(semantic_latencies) / max(1, sem_count), 2),
#         sem_tok=round(sum(semantic_tokens) / max(1, sem_count), 1),
#         hyb_count=hyb_count,
#         hyb_lat=round(sum(hybrid_latencies) / max(1, hyb_count), 2),
#         hyb_tok=round(sum(hybrid_tokens) / max(1, hyb_count), 1),
#     )

# @app.get("/api/v1/telemetry/feedback")
# def get_all_feedback_metrics() -> List[Dict[str, Any]]:
#     try:
#         return feedbacktable.scan().get("Items", [])
#     except Exception as e:
#         logger.error(f"Failed to scan: {e}")
#         raise

# @app.post("/api/v1/feedbackWrite")
# async def writeuserfeedback(
#     request: FeedbackRequest,
#     publisher: FeedbackPublisher = Depends(get_feedback_publisher),
#     cache: BaseCache = Depends(get_cache),
# ) -> Any:
#     agent_name, feedback, user_id, session_id, request_id = request.agentName, request.feedback or "", request.user_id, request.session_id, request.requestId
#     if not agent_name.strip():
#         raise HTTPException(status_code=400, detail="agentName cannot be empty")

#     cache_key = f"{user_id}_{session_id}_{request_id}_{feedback}"
#     if cache.exists(cache_key):
#         return {"message": "Key already exists", "cachekey": cache_key}

#     cache_payload = {"agentName": agent_name, "user_id": user_id, "session_id": session_id, "requestId": request_id, "feedback": feedback}
#     cache.set(key=cache_key, value=cache_payload, ttl=TTL)

#     # Record in Prometheus
#     sentiment = "good" if "good" in feedback.lower() or feedback == "1" else "bad"
#     AGENTIC_FEEDBACK_TOTAL.labels(agent_name=agent_name, sentiment=sentiment).inc()

#     success = publisher.publish(agent_name=agent_name, feedback=feedback)
#     if not success:
#         raise HTTPException(status_code=500, detail="Failed to publish feedback")

#     return {"status": "queued", "cache_key": cache_key}


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
"""
Clean FastAPI Server Entrypoint.
Adheres strictly to SOLID Principles by decoupling routing, dependencies, and SRE cron jobs.
"""
from __future__ import annotations

import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Inject querying root path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from container import build_container, close_container

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("MainServer")

# ------------------------------------------------------------------------------
# LIFESPAN & SCHEDULERS
# ------------------------------------------------------------------------------
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Dependency Container
    logger.info("Initializing dependency injection container (build_container)...")
    await build_container()

    # 2. Register SRE Background Cron Jobs
    from sre_scheduler import (
        run_metric_collector_job,
        run_hourly_agent_optimization_job,
        run_deterministic_canary_watchdog,
        run_5_hour_continuous_benchmark_job,
    )

    logger.info("Scheduling SRE metric and evaluation cron jobs...")
    scheduler.add_job(run_metric_collector_job, "interval", minutes=15, id="metric_collector_job")
    scheduler.add_job(run_hourly_agent_optimization_job, "interval", hours=1, id="agent_optimization_job") # agents discussion here
    scheduler.add_job(run_deterministic_canary_watchdog, "interval", minutes=1, id="canary_watchdog_job") # post deployment
    scheduler.add_job(run_5_hour_continuous_benchmark_job, "interval", hours=5, id="ragas_benchmark_job") # ragas

    # Start Scheduler
    scheduler.start()
    logger.info("🚀 SRE Schedulers started successfully! Background jobs are active.")

    yield

    # 3. Shutdown Resources
    logger.info("Shutdown initiated. Stopping schedulers and closing container connections...")
    scheduler.shutdown(wait=False)
    await close_container()
    logger.info("💤 Server successfully stopped.")


# ------------------------------------------------------------------------------
# FASTAPI APP & MIDDLEWARE
# ------------------------------------------------------------------------------
app = FastAPI(
    title="LangGraph & CrewAI Production Observability Server",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# MOUNT LLD SOLID ROUTERS (Busts Circular Imports completely)
# ------------------------------------------------------------------------------
from routers import chat_router, sre_router

logger.info("Mounting API Sub-Routers...")
app.include_router(chat_router.router)
app.include_router(sre_router.router)
logger.info("✅ All API Routers initialized and mounted successfully!")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)