from redis.asyncio import Redis


async def check_and_increment(redis: Redis, key: str, *, limit: int, window_seconds: int) -> bool:
    """Incrementa o contador da janela e devolve True se ainda dentro do limite."""
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count <= limit
