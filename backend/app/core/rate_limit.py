from redis.asyncio import Redis


async def check_and_increment(redis: Redis, key: str, *, limit: int, window_seconds: int) -> bool:
    """Incrementa o contador da janela e devolve True se ainda dentro do limite.

    Defesa contra chave travada sem TTL (observado em agosto/2026: chaves
    `login_attempts:*` com ttl=-1 acumulando entre runs e causando 429 espúrio —
    um processo que morre entre o incr e o expire deixa a chave para sempre).
    Se a chave existe sem expiração, o TTL é rearmado na próxima passagem.
    """
    count = await redis.incr(key)
    if count == 1 or await redis.ttl(key) < 0:
        await redis.expire(key, window_seconds)
    return count <= limit
