import redis.asyncio as aioredis

from app.core.config import settings

# Единый пул Redis для Pub/Sub чата, TTL-кодов линковки и кэша.
redis_client: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)
