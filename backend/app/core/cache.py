"""Cache de leitura com TTL curto e invalidação por evento (spec 098, regra 9).

Extraído do cache do dashboard de processos (spec 028), que era o único do sistema — e
que a regra 9 manda estender a **todo** dashboard e a toda taxonomia. Terceira cópia do
mesmo idioma seria a hora de extrair pela regra dos 3 usos (CLAUDE.md §6); a 098 antecipa
porque a regra 9 já pede a terceira e a quarta.

## O que entra e o que não entra

Cabe aqui o que é **caro de calcular, lido o tempo todo e tolerante a alguns minutos de
atraso**: o dashboard (agregado sobre a base inteira, aberto a cada navegação) e a
taxonomia (59 etapas, 152 tipos de tarefa — praticamente imutáveis, lidas em todo
formulário). Não cabe listagem filtrada, cujo espaço de chaves é o produto de todos os
filtros possíveis: a taxa de acerto tende a zero e o que sobra é ocupar Redis.

## Por que TTL *e* evento

O TTL sozinho mostra número velho por até cinco minutos depois de uma escrita — o
usuário cria um processo, volta ao dashboard e não se vê nele, o que parece bug. O
evento sozinho depende de nunca esquecermos de invalidar em algum caminho novo de
escrita. Juntos, o evento cobre o caso comum e o TTL é o limite superior do erro.
"""

import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

# Regra 9: cinco minutos. É o teto do atraso quando alguma escrita esquecer de invalidar.
DEFAULT_TTL_SECONDS = 300


class Cache(Protocol):
    """Contrato mínimo — o Redis do app satisfaz estruturalmente, e os testes usam um
    fake em memória sem tocar rede. As assinaturas espelham as do redis-py (parâmetro
    `name`, retorno `Awaitable`) para o Redis servir sem `cast`."""

    def get(self, name: str) -> Awaitable[bytes | str | None]: ...

    def set(self, name: str, value: str, *, ex: int) -> Awaitable[object]: ...

    def delete(self, *names: str) -> Awaitable[object]: ...


def tenant_key(namespace: str, tenant_id: uuid.UUID, *parts: object) -> str:
    """`<namespace>:<tenant>:<...>` — o tenant SEMPRE no começo.

    Chave de cache não passa por RLS: é o prefixo que impede um escritório de ler o
    agregado do outro. Por isso a montagem da chave é uma função só, e não string
    formatada em cada chamador.
    """
    sufixo = ":".join(str(parte) for parte in parts)
    return f"{namespace}:{tenant_id}{':' + sufixo if sufixo else ''}"


async def cached_json(
    cache: Cache | None,
    key: str,
    produce: Callable[[], Awaitable[Any]],  # noqa: ANN401 — o valor cacheado é JSON arbitrário
    *,
    decode: Callable[[Any], Any],  # noqa: ANN401 — idem
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Any:  # noqa: ANN401
    """Devolve o valor do cache ou calcula, grava e devolve.

    `cache=None` desliga o cache sem ramificar o chamador — é o que permite a um teste
    exercitar o cálculo puro, e a um ambiente sem Redis continuar servindo (mais lento,
    correto).

    Falha de leitura do cache **não** propaga: Redis indisponível deve deixar o sistema
    lento, nunca fora do ar. Falha de escrita idem — o valor já foi calculado e a
    resposta já está pronta.
    """
    if cache is None:
        return await produce()
    try:
        bruto = await cache.get(key)
    except Exception:  # noqa: BLE001 — cache fora do ar degrada, não derruba
        bruto = None
    if bruto is not None:
        return decode(json.loads(bruto))

    valor = await produce()
    # Falha de ESCRITA também não propaga: o valor já foi calculado e a resposta já
    # está pronta — derrubá-la porque o cache não aceitou a gravação seria trocar uma
    # degradação por uma indisponibilidade.
    with contextlib.suppress(Exception):
        await cache.set(key, json.dumps(valor, default=str), ex=ttl_seconds)
    return valor


async def invalidate(cache: Cache | None, *keys: str) -> None:
    """Derruba as chaves do evento. Sem cache, não há o que derrubar."""
    if cache is None or not keys:
        return
    # Invalidação que falha não é perda total: o TTL de 5 minutos continua sendo o teto
    # do erro. Propagar o erro derrubaria a ESCRITA que disparou o evento.
    with contextlib.suppress(Exception):
        await cache.delete(*keys)
