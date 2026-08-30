"""
Lightweight AWS SQS Feedback Emitter.
Publishes agent feedback (agentName, feedback) directly to SQS
for asynchronous processing by downstream Lambda workers.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class FeedbackSQSEmitter:
    """Publishes agent feedback events to AWS SQS."""

    def __init__(self, queue_url: Optional[str] = None, region_name: Optional[str] = None) -> None:
        self._queue_url = queue_url or os.getenv("FEEDBACK_SQS_QUEUE_URL", "")
        self._region = region_name or os.getenv("AWS_REGION", "ap-south-1")
        self._sqs = boto3.client("sqs", region_name=self._region)

    def emit(self, agent_name: str, feedback: str) -> bool:
        """Serializes agentName + feedback and publishes to SQS. Returns True on success."""
        if not self._queue_url:
            logger.warning("FEEDBACK_SQS_QUEUE_URL is not configured. Skipping SQS push.")
            return False

        payload = {
            "agentName": agent_name,
            "feedback": feedback,
            "eventType": "feedback"
        }

        try :
            self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(f"Feedback successfully emitted to SQS for agent: {agent_name}")
            return True
        except (BotoCoreError, ClientError) as e :
            logger.error(f"Failed to push feedback to SQS: {e}")
            return False