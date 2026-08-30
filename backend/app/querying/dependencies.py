"""
Dependencies & Abstractions (SOLID Compliant).
Decouples routers and the main server to prevent circular import loops.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pydantic import BaseModel

from cache import BaseCache, CacheFactory
from agenticPipeline.crewai_agents.tools.feedback_emitter import FeedbackSQSEmitter

# ------------------------------------------------------------------------------
# SHARED MODELS
# ------------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    agentName: str
    user_id: str
    session_id: str
    requestId: str
    feedback: str = ""


# ------------------------------------------------------------------------------
# CACHE INSTANTIATION
# ------------------------------------------------------------------------------
_cache_instance: BaseCache = CacheFactory.create_cache(
    provider=os.getenv("CACHE_PROVIDER", "valkey"),
    host=os.getenv("ELASTICACHE_HOST", "localhost"),
    port=int(os.getenv("ELASTICACHE_PORT", 6379)),
    ssl=os.getenv("ELASTICACHE_SSL", "True").lower() == "true",
)

TTL = int(os.getenv("TTL", "300000"))

def get_cache() -> BaseCache:
    return _cache_instance


# ------------------------------------------------------------------------------
# FEEDBACK PUBLISHER CONTRACTS
# ------------------------------------------------------------------------------
class FeedbackPublisher(ABC):
    @abstractmethod
    def publish(self, agent_name: str, feedback: str) -> bool:
        pass


class SQSFeedbackPublisher(FeedbackPublisher):
    def __init__(self, emitter: FeedbackSQSEmitter):
        self._emitter = emitter

    def publish(self, agent_name: str, feedback: str) -> bool:
        return self._emitter.emit(agent_name=agent_name, feedback=feedback)


_feedback_publisher: FeedbackPublisher = SQSFeedbackPublisher(FeedbackSQSEmitter())

def get_feedback_publisher() -> FeedbackPublisher:
    return _feedback_publisher