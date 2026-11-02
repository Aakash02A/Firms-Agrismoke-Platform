"""
AgriSmoke AI - Enterprise Distributed Caching Layer
Provides hybrid caching with in-memory TTL caching by default and transparent
failover to Redis when REDIS_URL is configured in environment variables.
"""

import os
import time
import json
import logging
from typing import Any, Optional, Dict

try:
    from backend.security import mask_url, redact_secrets
except ImportError:  # pragma: no cover - supports flat/direct imports
    from security import mask_url, redact_secrets

logger = logging.getLogger("agri_smoke.cache")

REDIS_URL = os.getenv("REDIS_URL", "").strip()


class CacheInterface:
    def __init__(self, default_ttl_seconds: int = 900):
        self.default_ttl = default_ttl_seconds
        self._memory_store: Dict[str, Any] = {}
        self._memory_expiry: Dict[str, float] = {}
        self._redis_client = None
        self._is_redis_available = False

        if REDIS_URL:
            try:
                import redis
                self._redis_client = redis.from_url(REDIS_URL, decode_responses=True)
                self._redis_client.ping()
                self._is_redis_available = True
                logger.info("Connected to enterprise Redis cache at %s", mask_url(REDIS_URL))
            except Exception as e:
                logger.warning(
                    "Redis connection failed (%s). Falling back to in-memory TTL cache.",
                    redact_secrets(str(e), [REDIS_URL]),
                )

    @property
    def is_redis(self) -> bool:
        return self._is_redis_available

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value by key; returns None if expired or non-existent."""
        if self._is_redis_available and self._redis_client:
            try:
                val = self._redis_client.get(key)
                return json.loads(val) if val else None
            except Exception as e:
                logger.warning(
                    "Redis GET failed for %s (%s); falling back to memory.",
                    key, redact_secrets(str(e), [REDIS_URL]),
                )

        # In-memory retrieval
        now = time.time()
        if key in self._memory_expiry and now > self._memory_expiry[key]:
            self.delete(key)
            return None
        return self._memory_store.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Store value with specified TTL (defaults to 900s)."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl

        if self._is_redis_available and self._redis_client:
            try:
                self._redis_client.setex(key, ttl, json.dumps(value))
                return True
            except Exception as e:
                logger.warning(
                    "Redis SET failed for %s (%s); falling back to memory.",
                    key, redact_secrets(str(e), [REDIS_URL]),
                )

        # In-memory storage
        self._memory_store[key] = value
        self._memory_expiry[key] = time.time() + ttl
        return True

    def delete(self, key: str) -> bool:
        """Removes a key from cache."""
        if self._is_redis_available and self._redis_client:
            try:
                self._redis_client.delete(key)
            except Exception:
                pass

        self._memory_store.pop(key, None)
        self._memory_expiry.pop(key, None)
        return True

    def clear(self) -> bool:
        """Flushes cache."""
        if self._is_redis_available and self._redis_client:
            try:
                self._redis_client.flushdb()
            except Exception:
                pass
        self._memory_store.clear()
        self._memory_expiry.clear()
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Cache operational statistics."""
        return {
            "backend": "redis" if self._is_redis_available else "in_memory",
            "activeKeys": len(self._memory_store),
            "redisConfigured": bool(REDIS_URL),
            "defaultTtlSeconds": self.default_ttl
        }


# Global singleton cache instance
cache = CacheInterface()

