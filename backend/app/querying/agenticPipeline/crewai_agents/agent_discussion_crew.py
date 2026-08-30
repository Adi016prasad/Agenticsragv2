"""
Hourly Multi-Agent Discussion Crew with Human-in-the-Loop Proposal Staging & Email.
Optimized for high agent autonomy, zero redundancy, and full Firestore/DynamoDB access.
"""
from __future__ import annotations

import logging
from crewai import Crew, Process, Task

from .agents import (
    DynamoDBQueryEngineerAgentFactory,
    FirebaseQueryEngineerAgentFactory,
)
from .config import DEFAULT_CONFIG, OrchestrationConfig

logger = logging.getLogger(__name__)


class AgentDiscussionCrew:
    """Orchestrates hourly debate between DynamoDB and Firebase agents."""

    def __init__(self, config: OrchestrationConfig = DEFAULT_CONFIG) -> None:
        self._config = config
        self._dynamo_factory = DynamoDBQueryEngineerAgentFactory(config)
        self._firebase_factory = FirebaseQueryEngineerAgentFactory(config)

    def run_discussion(self) -> str:
        logger.info("🤖 Starting Multi-Agent Discussion (DynamoDB <---> Firebase)...")
        dynamo_agent = self._dynamo_factory.build()
        firebase_agent = self._firebase_factory.build()

        # Phase 1: DynamoDB Agent audits metrics & feedback
        task_audit = Task(
            description=(
                "SYSTEM TELEMETRY & SATISFACTION AUDIT:\n"
                "1. Audit the last 1 hour of telemetry from `metrics_table` (OrchestrationMetrics):\n"
                "   - Compare Semantic vs. Hybrid search types: Total Tokens, Prompt/Completion ratio, and Cache Hit Rate.\n"
                "   - Analyze latency distributions (avg, p95) and error rates.\n"
                "2. Audit user satisfaction from `feedback_table` (FeedbackMetrics):\n"
                "   - Good vs. Bad feedback counts and satisfaction percentages for 'semanticAgent' and 'hybridAgent'.\n"
                "3. Diagnose the primary system bottleneck (e.g. token bloat, cache busting, high latency, or poor feedback) "
                "and state clear data findings for your Firebase coworker."
            ),
            expected_output=(
                "A comprehensive data audit comparing Semantic and Hybrid agents across tokens, "
                "cache efficiency, latencies, and user satisfaction percentages."
            ),
            agent=dynamo_agent,
        )

        # Phase 2: Firebase Agent cross-examines, stages proposal, and triggers email
        task_optimize_and_propose = Task(
            description=(
                "SYSTEM OPTIMIZATION, PROPOSAL STAGING & EMAIL DISPATCH:\n"
                "1. Check for recent auto-rollback errors using 'Read Canary Rollback Incidents' and "
                "   check past human rejections using 'Read Prior Human Optimization Feedback'. Conduct a post-mortem to avoid repeating failures.\n"
                "2. Review the DynamoDB audit from Phase 1.\n"
                "3. In Firebase Sandbox, inspect active prompts in `prompt_template` and user volume in `threads`.\n"
                "4. Debate with the DynamoDB agent (ask clarifying questions if needed) to agree on the highest-impact optimization.\n"
                "5. Call 'Stage Optimization Proposal in Firestore' tool to stage the proposed prompt and model adjustments under `optimization_proposals`.\n"
                "   - `target_template_id` must be ONE single document ID (e.g. 'agent_hybrid_rewriter').\n"
                "   - `proposed_payload` MUST be the COMPLETE replacement prompt dictionary (e.g. {'role': '...', 'goal': '...', 'backstory': '...'}).\n"
                "6. Call 'Send Optimization Action Plan Email' tool with the `proposal_id`, executive summary, and action plan.\n"
                "7. Return a clean natural language summary confirming the proposal was staged and emailed."
            ),
            expected_output=(
                "A consolidated executive summary confirming the agreed optimization, "
                "staged proposal ID in Firestore, and successful email delivery."
            ),
            agent=firebase_agent,
            context=[task_audit],
        )

        crew = Crew(
            agents=[dynamo_agent, firebase_agent],
            tasks=[task_audit, task_optimize_and_propose],
            process=Process.sequential,
            verbose=self._config.verbose,
        )

        result = crew.kickoff()
        metrics = crew.usage_metrics
        logger.info("==================================================")
        logger.info("💰 DISCUSSION CREW TOKEN CONSUMPTION STATS:")
        logger.info("==================================================")
        logger.info(f"• Total Tokens:      {metrics.total_tokens}")
        logger.info(f"• Input Tokens:      {metrics.prompt_tokens}")
        logger.info(f"• Output Tokens:     {metrics.completion_tokens}")
        logger.info(f"• Cached Tokens:     {metrics.cached_prompt_tokens}")
        logger.info("==================================================")
        return str(result.raw)