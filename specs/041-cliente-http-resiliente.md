# 041 — Cliente HTTP resiliente

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 002 · **Status:** ⬜ pendente

---

## 1. Objetivo

Camada única de saída HTTP. DJEN e DataJud são APIs públicas de terceiro sem SLA — vão cair,
vão limitar, vão mudar. Toda a resiliência mora aqui, não espalhada nos clients. É também
onde nasce o mecanismo de fixtures que mantém os testes offline.

## 2. Escopo

- `HttpClient` sobre `httpx.AsyncClient` com timeout, retry e backoff exponencial com jitter
- Rate limit por host (token bucket em Redis, compartilhado entre workers)
- Circuit breaker por host (fechado → aberto → meio-aberto)
- Cache condicional (`ETag`, `If-Modified-Since`)
- **Gravação e reprodução de fixtures** para teste
- Log estruturado de cada chamada + métricas
- Tabela `external_requests` para auditoria de falhas

## 3. Fora de escopo

- Clients específicos → 042 (DJEN) e 046 (DataJud)
- Webhooks de saída → 093

## 4. Modelo de dados

```sql
CREATE TABLE external_requests (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id),    -- nulo em chamada de sistema
  host TEXT NOT NULL,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status_code SMALLINT,
  duration_ms INTEGER,
  attempt SMALLINT NOT NULL DEFAULT 1,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ext_req_host ON external_requests (host, created_at DESC);
CREATE INDEX ix_ext_req_error ON external_requests (host, created_at DESC) WHERE error IS NOT NULL;
```
Migration `041_external_requests.py`. Retenção de 30 dias por job de limpeza.

## 5. Contratos internos

```python
class HttpClient(Protocol):
    async def request(self, method: str, url: str, **kw) -> HttpResponse: ...

@dataclass
class HostPolicy:
    timeout_s: float = 30.0
    max_retries: int = 3
    backoff_base_s: float = 0.5
    rate_limit_per_minute: int | None = None
    breaker_failure_threshold: int = 5
    breaker_reset_after_s: int = 60
    retry_on: tuple[int, ...] = (429, 500, 502, 503, 504)
```

## 6. Front-end

Nenhum. O painel de status da sincronização vem em 049.

## 7. Regras de negócio

1. Retry só em erro **transitório**: timeout, erro de conexão e os status de `retry_on`. 4xx (exceto 429) nunca é retentado.
2. Backoff exponencial com jitter: `base × 2^tentativa × random(0.5, 1.5)`, teto de 30 s.
3. `429` com header `Retry-After` respeita o valor informado, ignorando o backoff calculado.
4. Rate limit é **por host e global entre workers** — token bucket em Redis, não contador em memória.
5. Circuit breaker: N falhas consecutivas abre o circuito; enquanto aberto, falha imediato sem chamar a rede; após o tempo de reset, entra meio-aberto e libera uma requisição de teste.
6. Toda chamada é registrada em `external_requests` com duração e status. Sucesso pode ser amostrado; **falha é sempre gravada**.
7. Em modo de teste, o client lê de `tests/fixtures/http/<host>/<hash>.json` e **falha explicitamente** se a fixture não existir — nunca cai na rede.
8. Modo de gravação (`HTTP_RECORD=1`) grava a resposta real em fixture, com redação de headers sensíveis.
9. Corpo de resposta acima de 10 MB é rejeitado.
10. Timeout é sempre explícito; nunca herda o default da biblioteca.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | retry em 500, 502, 503, 504, timeout | ~0,3 s |
| unit | 400 e 404 não são retentados | ~0,2 s |
| unit | backoff cresce e respeita o teto | ~0,2 s |
| unit | `Retry-After` prevalece sobre o backoff | ~0,2 s |
| integração | rate limit bloqueia acima do teto | ~0,4 s |
| integração | rate limit é compartilhado entre dois clients | ~0,4 s |
| unit | breaker abre após N falhas | ~0,2 s |
| unit | breaker meio-aberto libera uma e fecha no sucesso | ~0,3 s |
| unit | breaker aberto falha sem tocar a rede | ~0,2 s |
| integração | falha é gravada em `external_requests` | ~0,3 s |
| **meta** | **fixture ausente falha o teste** | ~0,2 s |
| unit | corpo acima de 10 MB é rejeitado | ~0,2 s |

**Total:** ~3,1 s
Servidor HTTP falso local (`pytest-httpserver`) — nenhuma chamada externa real.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Guarda de fixture ativa · Commit `feat(041): cliente HTTP resiliente`
