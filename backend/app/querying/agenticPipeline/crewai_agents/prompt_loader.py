"""
Dynamic Prompt & LLM Model Loader & Cache Service.
Decoupled from container.py to eliminate circular imports.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple
from google.cloud import firestore

from cache import BaseCache, CacheFactory

logger = logging.getLogger(__name__)


def _get_independent_firestore_client() -> Optional[firestore.Client]:
    """Helper to initialize Firestore independently without importing container.py."""
    try:
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if key_path and os.path.exists(key_path):
            return firestore.Client.from_service_account_json(key_path)
        return firestore.Client(project=project_id) if project_id else None
    except Exception as exc:
        logger.warning(f"Could not initialize independent Firestore client: {exc}")
        return None


class PromptLoader:
    """
    Prompt and Model Loading Service.
    Injected with BaseCache and Firestore client to guarantee 0ms latency in production.
    """

    _instance: Optional[PromptLoader] = None

    def __new__(cls, *args, **kwargs) -> PromptLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        cache: Optional[BaseCache] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        self._cache: BaseCache = cache or self._resolve_cache_from_env()
        self._ttl_seconds: int = ttl_seconds or int(os.getenv("PROMPT_CACHE_TTL", "86400"))
        self._is_loaded: bool = False
        self._initialized: bool = True

    @staticmethod
    def _resolve_cache_from_env() -> BaseCache:
        """Factory resolver reading environment configuration."""
        provider = os.getenv("PROMPT_CACHE_PROVIDER", os.getenv("CACHE_PROVIDER", "memory")).lower()
        if provider in ("valkey", "redis", "elasticache"):
            return CacheFactory.create_cache(
                provider="valkey",
                host=os.getenv("ELASTICACHE_HOST", "localhost"),
                port=int(os.getenv("ELASTICACHE_PORT", 6379)),
                ssl=os.getenv("ELASTICACHE_SSL", "True").lower() == "true",
            )
        return CacheFactory.create_cache(provider="memory")

    def load_all_prompts(
        self,
        db: Optional[firestore.Client] = None,
        collection_name: str = "prompt_template",
    ) -> int:
        """
        Loads all active prompt templates and LLM models from Firestore and caches them.
        """
        client = db or _get_independent_firestore_client()

        if not client:
            logger.warning("⚠️ Firestore client unavailable. Using fallback prompts.")
            return 0

        try:
            logger.info(f"📥 Loading active prompt templates from Firestore collection: '{collection_name}'...")
            docs = list(client.collection(collection_name).where("is_active", "==", True).stream())

            loaded_count = 0
            for doc in docs:
                data = doc.to_dict()
                template_id = doc.id
                payload = data.get("payload", {})

                cache_key = f"prompt:{template_id}"
                self._cache.set(key=cache_key, value=payload, ttl=self._ttl_seconds)
                loaded_count += 1

            # Also preload active models from LLM collection
            try:
                active_model_doc = client.collection("LLM").document("currentlyactivemodel").get()
                if active_model_doc.exists:
                    self._cache.set(key="llm:currentlyactivemodel", value=active_model_doc.to_dict(), ttl=self._ttl_seconds)
                    logger.info("✅ Preloaded 'currentlyactivemodel' configuration into cache.")
            except Exception as exc:
                logger.warning(f"Could not preload currentlyactivemodel: {exc}")

            self._is_loaded = True
            logger.info(f"✅ Successfully loaded and cached {loaded_count} prompts into {self._cache.__class__.__name__}!")
            return loaded_count
        except Exception as exc:
            logger.error(f"❌ Error loading prompts from Firestore: {exc}. Using code fallbacks.", exc_info=True)
            return 0

    def _get_payload_with_fallback(self, template_id: str) -> Dict[str, Any]:
        """
        Checks cache. On cache miss, fetches fresh document from Firestore and caches it.
        """
        cache_key = f"prompt:{template_id}"
        payload = self._cache.get(cache_key)

        if payload:
            return payload

        try:
            client = _get_independent_firestore_client()
            if client:
                doc = client.collection("prompt_template").document(template_id).get()
                if doc.exists:
                    data = doc.to_dict() or {}
                    fresh_payload = data.get("payload", {})
                    self._cache.set(key=cache_key, value=fresh_payload, ttl=self._ttl_seconds)
                    return fresh_payload
        except Exception as exc:
            logger.warning(f"Could not fetch fresh prompt from DB: {exc}")

        return {}

    def get_agent_prompt(
        self,
        template_id: str,
        default_role: str,
        default_goal: str,
        default_backstory: str,
    ) -> Tuple[str, str, str]:
        payload = self._get_payload_with_fallback(template_id)
        role = payload.get("role", default_role)
        goal = payload.get("goal", default_goal)
        backstory = payload.get("backstory", default_backstory)
        return role, goal, backstory

    def get_task_prompt(
        self,
        template_id: str,
        default_description: str,
        default_expected_output: str,
    ) -> Tuple[str, str]:
        payload = self._get_payload_with_fallback(template_id)
        desc = payload.get("description_template", default_description)
        expected = payload.get("expected_output", default_expected_output)
        return desc, expected

    def get_active_model(self, role_key: str, default_model_id: str) -> str:
        cache_key = "llm:currentlyactivemodel"
        active_doc: Optional[Dict[str, Any]] = self._cache.get(cache_key)

        if not active_doc:
            try:
                client = _get_independent_firestore_client()
                if client:
                    doc = client.collection("LLM").document("currentlyactivemodel").get()
                    if doc.exists:
                        active_doc = doc.to_dict() or {}
                        self._cache.set(key=cache_key, value=active_doc, ttl=self._ttl_seconds)
            except Exception as exc:
                logger.warning(f"Could not load active LLM models from DB: {exc}")
                active_doc = {}

        if not active_doc:
            return default_model_id

        model_entry = active_doc.get(role_key, {})
        model_id = model_entry.get("model_id") if isinstance(model_entry, dict) else model_entry
        raw_model = model_id or default_model_id

        logger.info(f"Loading the llm {raw_model}")
        return raw_model if raw_model.startswith("openai/") else f"openai/{raw_model}"

    def invalidate_prompt(self, template_id: str) -> bool:
        if template_id == "currentlyactivemodel":
            return self._cache.delete("llm:currentlyactivemodel")
        cache_key = f"prompt:{template_id}"
        return self._cache.delete(cache_key)

    def clear_cache(self) -> bool:
        return self._cache.clear()


# Global Singleton Instance
prompt_loader = PromptLoader()