"""
SRE Scheduler: Encapsulates all background cron jobs, watchdogs, and alerts.
Adheres to the Single Responsibility Principle (SRP).
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText

import boto3
from boto3.dynamodb.conditions import Key
from google.cloud import firestore

from agenticPipeline.crewai_agents.config import DEFAULT_CONFIG
from agenticPipeline.crewai_agents.evaluation_crew import MetricEvaluationCrew
from agenticPipeline.crewai_agents.agent_discussion_crew import AgentDiscussionCrew
from agenticPipeline.crewai_agents.ragas_eval_crew import RagasEvaluationOrchestrator
from agenticPipeline.crewai_agents.prompt_loader import prompt_loader
from container import get_container

logger = logging.getLogger("SREScheduler")

TABLE_NAME = os.getenv("DYNAMODB_METRICS_TABLE", "OrchestrationMetrics")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)


def _query_dynamodb_range(from_ms: int) -> list[dict]:
    """Queries OrchestrationMetrics for the given timestamp range."""
    records = []
    for s_type in ["semantic", "hybrid"]:
        try:
            response = table.query(
                IndexName="SearchTypeTimestampIndex",
                KeyConditionExpression=Key("search_type").eq(s_type) & Key("timestamp").gte(from_ms),
            )
            records.extend(response.get("Items", []))
        except Exception as exc:
            logger.warning(f"GSI query for {s_type} failed: {exc}. Falling back to scan.")
            response = table.scan(FilterExpression=Key("timestamp").gte(from_ms))
            records = response.get("Items", [])
            break
    return records


async def run_metric_collector_job():
    """Cron starting 15 minute metric collector run."""
    logger.info("⏱️ Starting 15-minute SRE Metric Collector job...")
    try:
        eval_crew = MetricEvaluationCrew(config=DEFAULT_CONFIG)
        report = await asyncio.to_thread(eval_crew.evaluate, lookback_hours=0.25)
        logger.info(f"✅ Metric evaluation summary: {report.evaluation_summary_narrative}")
        logger.info(f"📊 Optimization recommendations: {report.optimization_recommendations}")
    except Exception as e:
        logger.error(f"❌ Metric collector job failed: {e}", exc_info=True)


async def run_hourly_agent_optimization_job():
    """SRE Optimizer: Debates prompt/model configs if traffic is high."""
    logger.info("🤖 Checking system traffic threshold for hourly optimization...")
    try:
        min_requests_threshold = int(os.getenv("MIN_REQUESTS_PER_HOUR", "15"))
        now_ms = int(time.time() * 1000)
        from_ms = now_ms - (3600 * 1000)

        recent_items = _query_dynamodb_range(from_ms)
        traffic_count = len(recent_items)

        logger.info(f"📊 Traffic: {traffic_count} req/hr (Threshold: {min_requests_threshold})")

        if traffic_count < min_requests_threshold:
            logger.info("⏸️ Skipping hourly discussion due to low traffic. Saving tokens.")
            return

        logger.info(f"🔥 High traffic detected ({traffic_count} >= {min_requests_threshold}). Triggering SRE Agents!")
        discussion_crew = AgentDiscussionCrew(config=DEFAULT_CONFIG)
        report = await asyncio.to_thread(discussion_crew.run_discussion)
        logger.info(f"✅ Discussion Complete. Staged & Emailed:\n{report}")
    except Exception as e:
        logger.error(f"❌ SRE Optimizer job failed: {e}", exc_info=True)


async def run_5_hour_continuous_benchmark_job():
    """Triggers the 3-Stage Ragas Benchmark every 5 hours."""
    logger.info("🧪 Triggering 5-Hour Ragas Benchmark Pipeline...")
    try:
        orchestrator = RagasEvaluationOrchestrator(config=DEFAULT_CONFIG)
        await orchestrator.execute_full_benchmark(collection_name="testinghubnew", delay_seconds=300)
    except Exception as e:
        logger.error(f"❌ 5-Hour Benchmark failed: {e}", exc_info=True)


def send_emergency_rollback_email(template_id: str, error_rate: float, p95_latency: float, reason: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    approver_email = os.getenv("APPROVER_EMAIL")

    if not all([smtp_host, smtp_user, smtp_password, approver_email]):
        logger.warning("SMTP settings missing. Skipping emergency rollback email.")
        return

    subject = f"⚠️ [CRITICAL] Automated Rollback Executed: {template_id}"
    body = (
        f"==================================================\n"
        f"🚨 SYSTEM HEALTH ALERT: AUTOMATED ROLLBACK EXECUTED\n"
        f"==================================================\n\n"
        f"The newly deployed prompt for '{template_id}' violated production SLAs.\n\n"
        f"📉 BREACH METRICS (Last 2 minutes):\n"
        f"- Error Rate: {error_rate:.2f}% (Threshold: > 5.0%)\n"
        f"- p95 Latency: {p95_latency:.0f}ms (Threshold: > 6000ms)\n\n"
        f"🛠️ ACTION TAKEN:\n"
        f"The system has AUTOMATICALLY reverted the prompt for '{template_id}' to the "
        f"previous stable version and invalidated the in-memory cache.\n\n"
        f"🔍 INCIDENT DETAILS:\n"
        f"{reason}\n\n"
        f"No manual intervention is needed. The stable prompt is live in production."
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = approver_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [approver_email], msg.as_string())
        logger.info(f"📧 Emergency rollback email sent successfully to {approver_email}")
    except Exception as exc:
        logger.error(f"Failed to send emergency rollback email: {exc}")


async def run_deterministic_canary_watchdog():
    """SRE Watchdog: Instantly rolls back and flushes cache on SLA breach."""
    logger.info("🛡️ Checking active canary deployments...")
    try:
        db = get_container().checkpointer.client
        active_canaries = list(
            db.collection("prompt_template")
            .where("canary_status", "==", "in_observation")
            .stream()
        )
        
        if not active_canaries:
            return

        for doc in active_canaries:
            data = doc.to_dict()
            template_id = doc.id
            expires_at = data.get("canary_expires_at", 0)
            previous_payload = data.get("previous_payload")
            current_version = data.get("version", 1)

            # Query last 2 minutes of telemetry
            now_ms = int(time.time() * 1000)
            two_mins_ago_ms = now_ms - (120 * 1000)
            items = _query_dynamodb_range(two_mins_ago_ms)

            if items:
                total_reqs = len(items)
                error_count = sum(1 for i in items if i.get("error"))
                error_rate = (error_count / total_reqs) * 100.0
                p95_latency = max([float(i.get("total_latency_ms", 0.0)) for i in items])

                if error_rate > 5.0 or p95_latency > 6000.0:
                    sample_errors = [i.get("error") for i in items if i.get("error")][:3]
                    reason = f"Outage triggered by version {current_version}.\nErrors: {sample_errors}"

                    # Revert Database
                    doc.reference.update({
                        "payload": previous_payload,
                        "canary_status": "rolled_back",
                        "canary_expires_at": None,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })

                    # Flush Cache
                    prompt_loader.invalidate_prompt(template_id)
                    
                    # Store Incident
                    db.collection("canary_rollbacks").add({
                        "template_id": template_id,
                        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                        "metrics_snapshot": {"error_rate_pct": round(error_rate, 2), "p95_latency_ms": round(p95_latency, 2)},
                        "sample_error_traces": sample_errors,
                        "status": "pending_agent_review",
                    })

                    # Alert Email
                    send_emergency_rollback_email(template_id, error_rate, p95_latency, reason)
                    logger.error(f"🛑 [AUTO-ROLLBACK] Reverted '{template_id}' back to stable!")
                    return

            if time.time() >= expires_at:
                doc.reference.update({"canary_status": "stable", "canary_expires_at": None})
                logger.info(f"❇️ [Canary Graduated] Template '{template_id}' declared stable.")

    except Exception as e:
        logger.error(f"Error in canary watchdog: {e}", exc_info=True)