"""Locks distribuídos em Redis (spec 044, regra 10).

`SyncLock` é o contrato consumido pelos services; `RedisSyncLock` é a
implementação de produção. O release compara o token antes de apagar — sem
isso, uma execução que estourou o TTL apagaria o lock de quem re-adquiriu
depois (o caso clássico do SET NX EX sem token).
"""

import uuid
from typing import Protocol

from redis.asyncio import Redis

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class SyncLock(Protocol):
    """Uma execução por vez por chave, mesmo com workers duplicados."""

    async def acquire(self, key: str, *, ttl_seconds: int) -> bool: ...
    async def release(self, key: str) -> None: ...


class RedisSyncLock:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._tokens: dict[str, str] = {}

    async def acquire(self, key: str, *, ttl_seconds: int) -> bool:
        token = uuid.uuid4().hex
        acquired = await self._redis.set(key, token, nx=True, ex=ttl_seconds)
        if acquired:
            self._tokens[key] = token
            return True
        return False

    async def release(self, key: str) -> None:
        token = self._tokens.pop(key, None)
        if token is not None:
            await self._redis.eval(_RELEASE_SCRIPT, 1, key, token)
