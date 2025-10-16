"""
Health check endpoints for monitoring system status.
"""
from fastapi import APIRouter, HTTPException
from starlette import status
from typing import Dict, Any
import time
from app.core.redis import test_redis_connection
from app.core.config import settings
import psycopg2
from psycopg2 import OperationalError

router = APIRouter()


async def check_database() -> Dict[str, Any]:
    """Check PostgreSQL database connection."""
    try:
        # Create a connection to test
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.close()
        return {"status": "healthy", "message": "Database connection successful"}
    except OperationalError as e:
        return {"status": "unhealthy", "message": f"Database connection failed: {str(e)}"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Unexpected database error: {str(e)}"}


async def check_redis() -> Dict[str, Any]:
    """Check Redis connection."""
    try:
        is_connected = await test_redis_connection()
        if is_connected:
            return {"status": "healthy", "message": "Redis connection successful"}
        else:
            return {"status": "unhealthy", "message": "Redis connection failed"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Redis error: {str(e)}"}


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    Returns overall system health status.
    """
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "service": "matatu-management-api",
        "version": "1.0.0"
    }


@router.get("/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check including all system components.
    """
    start_time = time.time()

    # Check database
    db_status = await check_database()

    # Check Redis
    redis_status = await check_redis()

    # Overall status
    components = {
        "database": db_status,
        "redis": redis_status
    }

    overall_status = "healthy"
    unhealthy_components = []

    for name, status_info in components.items():
        if status_info["status"] != "healthy":
            overall_status = "unhealthy"
            unhealthy_components.append(name)

    response_time = time.time() - start_time

    return {
        "status": overall_status,
        "timestamp": int(time.time()),
        "response_time": round(response_time, 3),
        "service": "matatu-management-api",
        "version": "1.0.0",
        "components": components,
        "unhealthy_components": unhealthy_components if unhealthy_components else None
    }


@router.get("/redis")
async def redis_health_check() -> Dict[str, Any]:
    """
    Redis-specific health check endpoint.
    """
    start_time = time.time()

    redis_status = await check_redis()
    response_time = time.time() - start_time

    # Additional Redis info
    redis_info = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "db": settings.REDIS_DB,
        "ssl_enabled": settings.REDIS_SSL,
        "cache_ttl": settings.CACHE_TTL,
        "cache_prefix": settings.CACHE_PREFIX
    }

    return {
        "status": redis_status["status"],
        "timestamp": int(time.time()),
        "response_time": round(response_time, 3),
        "message": redis_status["message"],
        "redis_config": redis_info
    }


@router.get("/database")
async def database_health_check() -> Dict[str, Any]:
    """
    Database-specific health check endpoint.
    """
    start_time = time.time()

    db_status = await check_database()
    response_time = time.time() - start_time

    # Mask sensitive info in database URL
    db_url_masked = settings.DATABASE_URL
    if "://" in db_url_masked:
        # Replace password with asterisks
        parts = db_url_masked.split("://")
        if "@" in parts[1]:
            auth_part = parts[1].split("@")[0]
            if ":" in auth_part:
                user = auth_part.split(":")[0]
                db_url_masked = f"{parts[0]}://{user}:***@{parts[1].split('@')[1]}"

    return {
        "status": db_status["status"],
        "timestamp": int(time.time()),
        "response_time": round(response_time, 3),
        "message": db_status["message"],
        "database_url": db_url_masked
    }
