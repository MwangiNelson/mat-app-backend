"""
Caching service utilities using Redis.
Provides high-level caching operations for the application.
"""
import json
import hashlib
from typing import Any, Optional, Union, Dict, List
from functools import wraps
import logging
from app.core.redis import get_redis_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    High-level caching service for Redis operations.
    """

    def __init__(self):
        self.client = None
        self.prefix = settings.CACHE_PREFIX

    async def _get_client(self):
        """Get Redis client instance."""
        if self.client is None:
            self.client = await get_redis_client()
        return self.client

    def _make_key(self, *parts: str) -> str:
        """Create a cache key with prefix."""
        key_parts = [self.prefix] + list(parts)
        return ":".join(str(part) for part in key_parts)

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache by key.

        Args:
            key: Cache key (without prefix)

        Returns:
            Cached value or None if not found
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            value = await client.get(full_key)

            if value is None:
                return None

            # Try to parse as JSON, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key (without prefix)
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (uses default if None)

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)

            # Serialize value to JSON
            if isinstance(value, (dict, list, int, float, bool)):
                serialized_value = json.dumps(value)
            else:
                serialized_value = str(value)

            ttl_value = ttl or settings.CACHE_TTL
            return await client.setex(full_key, ttl_value, serialized_value)

        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            return bool(await client.delete(full_key))
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "vehicles:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_client()
            full_pattern = self._make_key(pattern)

            # Find all keys matching the pattern
            keys = []
            async for key in client.scan_iter(full_pattern):
                keys.append(key)

            if keys:
                return await client.delete(*keys)
            return 0

        except Exception as e:
            logger.error(f"Error deleting cache pattern {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            True if key exists, False otherwise
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            return bool(await client.exists(full_key))
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {e}")
            return False

    async def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for a key.

        Args:
            key: Cache key (without prefix)

        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if no TTL
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            return await client.ttl(full_key)
        except Exception as e:
            logger.error(f"Error getting TTL for cache key {key}: {e}")
            return -2

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a numeric value in cache.

        Args:
            key: Cache key (without prefix)
            amount: Amount to increment by

        Returns:
            New value after increment, None if error
        """
        try:
            client = await self._get_client()
            full_key = self._make_key(key)
            return await client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"Error incrementing cache key {key}: {e}")
            return None

    async def clear_all(self) -> bool:
        """
        Clear all cache keys with our prefix.
        USE WITH CAUTION - this will clear all application cache.

        Returns:
            True if successful, False otherwise
        """
        try:
            pattern = f"{self.prefix}*"
            deleted_count = await self.delete_pattern("*")
            logger.info(f"Cleared {deleted_count} cache keys")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False


# Global cache service instance
cache_service = CacheService()


def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    Decorator to cache function results.

    Args:
        ttl: Time to live in seconds (uses default if None)
        key_prefix: Prefix for cache key generation

    Example:
        @cached(ttl=300, key_prefix="vehicles")
        async def get_vehicle(vehicle_id: str):
            # Function implementation
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            func_name = f"{key_prefix}:{func.__name__}" if key_prefix else func.__name__

            # Create a hash of the arguments for uniqueness
            arg_str = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
            arg_hash = hashlib.md5(arg_str.encode()).hexdigest()[:8]

            cache_key = f"{func_name}:{arg_hash}"

            # Try to get from cache first
            cached_result = await cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result

            # Execute function and cache result
            logger.debug(f"Cache miss for {cache_key}")
            result = await func(*args, **kwargs)

            if result is not None:
                await cache_service.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


def invalidate_cache(*patterns: str):
    """
    Decorator to invalidate cache patterns after function execution.

    Args:
        patterns: Cache key patterns to invalidate (e.g., "vehicles:*")

    Example:
        @invalidate_cache("vehicles:*", "dashboard:*")
        async def update_vehicle(vehicle_id: str, data: dict):
            # Function implementation
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Invalidate cache patterns
            for pattern in patterns:
                await cache_service.delete_pattern(pattern)

            return result

        return wrapper
    return decorator
