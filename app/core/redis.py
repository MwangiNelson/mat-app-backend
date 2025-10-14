"""
Redis connection and client management for caching.
"""
import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: redis.Redis = None


async def get_redis_client() -> redis.Redis:
    """
    Get or create Redis client instance.
    Returns a singleton Redis client for the application.
    """
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                db=settings.REDIS_DB,
                ssl=settings.REDIS_SSL,
                decode_responses=True,  # Return strings instead of bytes
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
            )

            # Test the connection
            await _redis_client.ping()
            logger.info("Successfully connected to Redis")

        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            raise

    return _redis_client


async def close_redis_client():
    """
    Close the Redis client connection.
    Should be called during application shutdown.
    """
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


async def test_redis_connection() -> bool:
    """
    Test Redis connection and return True if successful.
    """
    try:
        client = await get_redis_client()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False


# Synchronous Redis client for non-async operations (like during startup)
def get_sync_redis_client():
    """
    Get synchronous Redis client for operations that don't need async.
    """
    try:
        import redis as sync_redis
        return sync_redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            db=settings.REDIS_DB,
            ssl=settings.REDIS_SSL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        logger.error(f"Failed to create sync Redis client: {e}")
        return None
