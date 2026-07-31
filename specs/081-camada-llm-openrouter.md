# 081 — Camada LLM (OpenRouter)

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 041 · **Status:** ⬜ pendente

---

## 1. Objetivo

Uma única porta de saída para LLM. **OpenRouter é o gateway; o modelo é escolha do usuário, por
feature.** Nenhum provider é chamado diretamente e nenhum modelo é hardcoded — trocar de modelo
é configuração, não deploy.

## 2. Escopo

- Interface `LLMProvider` e implementação OpenRouter
- Tabela `ai_feature_config` — modelo por feature, configurável na UI
- Streaming SSE
- Contagem de tokens e custo em `ai_usage`
- Fallback de modelo em falha
- Listagem dos modelos disponíveis no OpenRouter
- Fixtures gravadas para teste

## 3. Fora de escopo

- LangGraph → 082 · Ferramentas → 083/084 · Qualquer feature de IA → 085+

## 4. Modelo de dados

```sql
CREATE TABLE ai_feature_config (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  feature_key TEXT NOT NULL,            -- 'copilot' | 'publication_summary' | ...
  model TEXT NOT NULL,                  -- id do modelo no OpenRouter
  fallback_model TEXT,
  temperature NUMERIC(3,2) NOT NULL DEFAULT 0.20,
  max_tokens INTEGER,
  is_enabled BOOLEAN NOT NULL DEFAULT true,
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, feature_key)
);

CREATE TABLE ai_usage (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID REFERENCES users(id),
  feature_key TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(12,6),
  latency_ms INTEGER,
  status TEXT NOT NULL,                 -- 'ok' | 'error' | 'fallback'
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_usage_tenant ON ai_usage (tenant_id, created_at DESC);
CREATE INDEX ix_ai_usage_feature ON ai_usage (tenant_id, feature_key, created_at DESC);
```
RLS nas duas. Migration `081_llm_layer.py`.

## 5. Contratos internos

```python
class LLMProvider(Protocol):
    async def complete(self, *, messages: list[Message], model: str,
                       tools: list[ToolSpec] | None = None,
                       temperature: float = 0.2,
                       max_tokens: int | None = None) -> LLMResponse: ...
    async def stream(self, ...) -> AsyncIterator[LLMChunk]: ...

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    usage: Usage
    model: str
    finish_reason: str
```

## 6. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/ai/models` | ADMINISTRADOR — catálogo do OpenRouter, com preço |
| GET/PUT | `/api/v1/ai/feature-config` | GESTOR |
| GET | `/api/v1/ai/usage?from=&to=&feature_key=&group_by=` | ADMINISTRADOR |

## 7. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `StatCard`
**Cria:** `AiSettingsPage`, `ModelSelect` (busca no catálogo, mostra preço e contexto),
`FeatureConfigRow`, `AiUsagePanel` (custo por feature e por período)
**Rota:** `/settings/ai`

## 8. Regras de negócio

1. **OpenRouter é o único gateway.** Import de SDK de provider específico reprova no lint.
2. **Nenhum modelo hardcoded.** O padrão vem de variável de ambiente; o efetivo vem de
   `ai_feature_config`. String de modelo literal no código reprova no teste de cobertura.
3. Feature sem configuração usa o padrão do ambiente e registra aviso — nunca falha por isso.
4. `is_enabled = false` desliga a feature: a UI esconde e a API retorna 409 explicando.
5. Falha do modelo principal tenta o `fallback_model` uma vez, registrando `status = 'fallback'`.
6. Todo uso grava tokens, custo e latência — mesmo em erro.
7. Custo vem do header de uso do OpenRouter; ausente, é calculado pelo preço do catálogo.
8. Streaming por SSE com eventos `chunk`, `tool_call`, `done` e `error`.
9. Timeout de 120 s para completions, 300 s para streaming.
10. Header `HTTP-Referer` e `X-Title` enviados ao OpenRouter, conforme a documentação deles.
11. Chave em `OPENROUTER_API_KEY`; ausente, as features de IA aparecem desabilitadas com aviso — o sistema **não quebra**.
12. **Nenhuma chamada real em teste.** Fixtures gravadas em `tests/fixtures/llm/`.
13. Prompt e resposta **não** são persistidos por padrão (LGPD); só metadados. Persistir exige opt-in explícito do tenant.

## 9. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | monta requisição no formato OpenRouter | ~0,2 s |
| unit | parseia resposta com e sem tool calls | ~0,3 s |
| unit | streaming emite os 4 tipos de evento | ~0,3 s |
| integração | modelo vem de `ai_feature_config` | ~0,3 s |
| integração | sem config usa o padrão e avisa | ~0,2 s |
| integração | `is_enabled = false` → 409 | ~0,2 s |
| integração | falha aciona fallback uma vez | ~0,4 s |
| integração | uso registrado inclusive em erro | ~0,3 s |
| integração | custo calculado quando o header falta | ~0,3 s |
| integração | sem `OPENROUTER_API_KEY` a feature desabilita sem quebrar | ~0,3 s |
| integração | prompt não é persistido sem opt-in | ~0,3 s |
| **meta** | **nenhum SDK de provider importado** (grep) | ~0,2 s |
| **meta** | **nenhum id de modelo literal no código** (grep) | ~0,2 s |
| **meta** | **nenhuma chamada real de LLM em teste** | ~0,2 s |
| frontend | seletor de modelo mostra preço | ~0,4 s |

**Total:** ~4,1 s

## 10. Definição de pronto

Checklist padrão · Os 3 testes meta ativos · Sistema funciona sem chave de IA · Commit `feat(081): camada LLM (OpenRouter)`
