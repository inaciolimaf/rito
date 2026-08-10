"""Cache condicional (ETag / If-Modified-Since) no Redis (spec 041, §2).

Só GET é cacheável aqui. O guarda-chuva é o Redis para que o cache seja
compartilhado entre workers, como o rate limit — e porque o par
(validadores, corpo) sobrevive ao restart do processo, que é exatamente quando
a revalidação condicional mais economiza.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

_CACHE_TTL_S = 24 * 60 * 60


@dataclass
class CachedEntry:
    etag: str | None
    last_modified: str | None
    headers: dict[str, str]
    body: bytes


def cache_key_for(method: str, url: str) -> str:
    digest = hashlib.sha256(f"{method.upper()} {url}".encode()).hexdigest()
    return f"http_cache:{digest}"


class CacheStore(Protocol):
    """Abstração do cache condicional — o client depende disto, não do Redis (DIP)."""

    async def get(self, key: str) -> CachedEntry | None: ...

    async def store(
        self,
        key: str,
        *,
        etag: str | None,
        last_modified: str | None,
        headers: dict[str, str],
        body: bytes,
    ) -> None: ...


class ConditionalCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> CachedEntry | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        return CachedEntry(
            etag=data["etag"],
            last_modified=data["last_modified"],
            headers=data["headers"],
            body=base64.b64decode(data["body_b64"]),
        )

    async def store(
        self,
        key: str,
        *,
        etag: str | None,
        last_modified: str | None,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        payload = json.dumps(
            {
                "etag": etag,
                "last_modified": last_modified,
                "headers": headers,
                "body_b64": base64.b64encode(body).decode(),
            }
        )
        await self._redis.set(key, payload, ex=_CACHE_TTL_S)
