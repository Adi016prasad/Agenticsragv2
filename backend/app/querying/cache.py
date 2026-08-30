import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Union

import redis

logger = logging.getLogger(__name__)


# ==========================================================
# 1. ABSTRACT BASE CLASS (The Contract)
# ==========================================================
class BaseCache(ABC):
    """
    Abstract Base Class for all caching mechanisms.
    Any new caching technology must implement this interface.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Retrieve an item from the cache."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store an item in the cache.

        :param key: Cache key.
        :param value: Value to store (will be JSON-serialized if dict/list).
        :param ttl: Time to live in seconds (optional).
        :return: True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete an item from the cache."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        pass

    @abstractmethod
    def clear(self) -> bool:
        """Clear all keys in the cache (flush)."""
        pass


# ==========================================================
# 2. CONCRETE IMPLEMENTATION: Valkey / Redis ElastiCache
# ==========================================================
class ValkeyCache(BaseCache):
    """
    Concrete implementation for AWS ElastiCache (Valkey / Redis).
    Uses connection pooling and handles serialization automatically.
    """

    def __init__(
        self,
        host: str,
        port: int = 6379,
        password: Optional[str] = None,
        ssl: bool = True,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        max_connections: int = 50,
    ):
        # Initializing redis.Redis directly configures SSLConnection automatically
        self._client = redis.Redis(
            host=host,
            port=port,
            password=password,
            ssl=ssl,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            max_connections=max_connections,
            decode_responses=True,
        )

    def _serialize(self, value: Any) -> str:
        """Helper to serialize complex data types to JSON."""
        if isinstance(value, (dict, list, tuple, bool)):
            return json.dumps(value)
        return str(value)

    def _deserialize(self, value: Optional[str]) -> Optional[Any]:
        """Helper to deserialize string back to JSON objects if applicable."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def get(self, key: str) -> Optional[Any]:
        try:
            raw_value = self._client.get(key)
            return self._deserialize(raw_value)
        except redis.RedisError as e:
            logger.error(f"Error reading key '{key}' from Valkey: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            serialized_value = self._serialize(value)
            return bool(self._client.set(name=key, value=serialized_value, nx = True, ex=ttl))
        except redis.RedisError as e:
            logger.error(f"Error setting key '{key}' in Valkey: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            return bool(self._client.delete(key))
        except redis.RedisError as e:
            logger.error(f"Error deleting key '{key}' from Valkey: {e}")
            return False

    def exists(self, key: str) -> bool:
        try:
            return bool(self._client.exists(key))
        except redis.RedisError as e:
            logger.error(f"Error checking existence of key '{key}' in Valkey: {e}")
            return False

    def clear(self) -> bool:
        try:
            return bool(self._client.flushdb())
        except redis.RedisError as e:
            logger.error(f"Error flushing Valkey DB: {e}")
            return False


# ==========================================================
# 3. EXAMPLE LOCAL IN-MEMORY IMPLEMENTATION (For Unit Tests)
# ==========================================================
class InMemoryCache(BaseCache):
    """
    In-memory fallback cache (useful for local development/unit testing).
    """

    def __init__(self):
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        self._store[key] = value
        return True

    def delete(self, key: str) -> bool:
        return bool(self._store.pop(key, None))

    def exists(self, key: str) -> bool:
        return key in self._store

    def clear(self) -> bool:
        self._store.clear()
        return True


# ==========================================================
# 4. FACTORY (Dependency Inversion)
# ==========================================================
class CacheFactory:
    """Factory to create cache instances cleanly without tight coupling."""

    @staticmethod
    def create_cache(provider: str, **kwargs) -> BaseCache:
        provider = provider.lower()
        if provider in ("valkey", "redis", "elasticache"):
            return ValkeyCache(**kwargs)
        elif provider == "memory":
            return InMemoryCache()
        else:
            raise ValueError(f"Unsupported cache provider: {provider}")