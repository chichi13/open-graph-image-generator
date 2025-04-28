import json
from typing import Any, Optional

import redis

from app.config import settings
from app.logger import logger

try:
    # decode_responses=True automatically decodes Redis responses (e.g., from bytes to UTF-8 strings)
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis for caching.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis for caching: {e}", exc_info=True)
    redis_client = None


def set_cache(key: str, value: Any, expiration_seconds: int):
    """Sets a value in the Redis cache with an expiration time."""
    if not redis_client:
        logger.warning("Redis client not available. Skipping cache set.")
        return
    try:
        # Serialize complex types (like dicts) to JSON strings
        serialized_value = json.dumps(value)
        redis_client.setex(key, expiration_seconds, serialized_value)
        logger.debug(f"Set cache for key '{key}' with expiration {expiration_seconds}s")
    except redis.exceptions.RedisError as e:
        logger.error(f"Redis error setting cache key '{key}': {e}", exc_info=True)
    except TypeError as e:
        logger.error(
            f"Serialization error setting cache key '{key}': {e}", exc_info=True
        )


def get_cache(key: str) -> Optional[Any]:
    """Gets a value from the Redis cache."""
    if not redis_client:
        logger.warning("Redis client not available. Skipping cache get.")
        return None
    try:
        cached_value = redis_client.get(key)
        if cached_value:
            logger.debug(f"Cache hit for key '{key}'")
            # Deserialize from JSON string
            return json.loads(cached_value)
        else:
            logger.debug(f"Cache miss for key '{key}'")
            return None
    except redis.exceptions.RedisError as e:
        logger.error(f"Redis error getting cache key '{key}': {e}", exc_info=True)
        return None
    except json.JSONDecodeError as e:
        logger.error(
            f"Deserialization error getting cache key '{key}': {e}", exc_info=True
        )
        # Cache data is corrupted, treat as miss
        return None
