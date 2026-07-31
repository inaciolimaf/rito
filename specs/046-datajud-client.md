# 046 — DataJud: client

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 041 · **Status:** ⬜ pendente

---

## 1. Objetivo

Client da API pública do DataJud — capa processual e movimentos com **códigos padronizados
nacionalmente**. É Elasticsearch com um alias por tribunal, autenticado por uma chave pública
do CNJ que pode ser rotacionada a qualquer momento.

## 2. Escopo

- Client de `api-publica.datajud.cnj.jus.br`
- Chave pública em configuração, **nunca** hardcoded
- Resolução do alias a partir do tribunal
- Query Elasticsearch por número de processo
- **Alerta em 401** apontando para a wiki do CNJ
- Parse de `_source` e `movimentos[]`

## 3. Fora de escopo

- Sincronização de andamentos → 047 · Descoberta de processos por OAB (fora do escopo do produto)

## 4. Modelo de dados

```sql
CREATE TABLE integration_alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id),      -- nulo = alerta de sistema
  integration TEXT NOT NULL,                  -- 'datajud' | 'djen'
  severity TEXT NOT NULL,                     -- 'warning' | 'critical'
  code TEXT NOT NULL,                         -- 'api_key_rotated' | 'rate_limited' | ...
  message TEXT NOT NULL,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_alerts_open ON integration_alerts (integration, created_at DESC)
  WHERE resolved_at IS NULL;

CREATE TABLE cnj_movement_codes (              -- tabela nacional de movimentos, global
  code INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  parent_code INTEGER REFERENCES cnj_movement_codes(code)
);
```
Migration `046_datajud.py` + seed dos códigos de movimento mais frequentes.

## 5. Contrato externo

```
POST https://api-publica.datajud.cnj.jus.br/api_publica_<alias>/_search
Authorization: APIKey <DATAJUD_API_KEY>
Content-Type: application/json

{ "size": 10, "query": { "match": { "numeroProcesso": "00007480420048260451" } } }

200 → { hits: { total, hits: [ { _source: {...} } ] } }
401 → chave inválida ou rotacionada
```

Campos de `_source`: `id · tribunal · grau · numeroProcesso · dataAjuizamento · nivelSigilo ·
orgaoJulgador · classe · sistema · formato · dataHoraUltimaAtualizacao · movimentos[] · assuntos[]`

Cada movimento: `codigo · dataHora · nome · complementosTabelados[] · orgaoJulgador`

## 6. Front-end

**Cria:** `IntegrationAlertBanner` — banner global quando há alerta crítico aberto
(reutilizado pelo DJEN em 049)

## 7. Regras de negócio

1. A chave vem **sempre** de `DATAJUD_API_KEY`. Chave literal no código reprova no lint.
2. É chave **pública do CNJ**, não credencial do usuário — documente isso no código, para ninguém tratá-la como segredo pessoal.
3. `401` cria `integration_alert` crítico com código `api_key_rotated`, mensagem apontando para
   `https://datajud-wiki.cnj.jus.br/api-publica/acesso/` e **para a sincronização** até haver
   intervenção. Não fica tentando em loop.
4. Alias resolvido de `courts.datajud_alias`. Tribunal sem alias → erro tipado `CourtNotSupported`, não exceção genérica.
5. Número de processo na query vai só com dígitos.
6. `nivelSigilo > 0` → o processo é descartado sem persistir (segredo de justiça).
7. Movimento com código fora de `cnj_movement_codes` é aceito e persistido, mas loga aviso para o seed ser atualizado.
8. `dataHoraUltimaAtualizacao` é a base do incremental de 047.
9. Timeout de 30 s; Elasticsearch de terceiro pode demorar.
10. Parse é função pura.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **parse de `_source` contra fixture real** (a capturada na pesquisa) | ~0,3 s |
| unit | parse de `movimentos[]` com complementos | ~0,2 s |
| unit | resposta sem hits | ~0,1 s |
| integração | client envia o header `APIKey` | ~0,2 s |
| integração | **401 cria alerta crítico e pausa** | ~0,4 s |
| integração | 401 não entra em loop de retry | ~0,3 s |
| integração | alias resolvido do tribunal | ~0,2 s |
| integração | tribunal sem alias → `CourtNotSupported` | ~0,2 s |
| integração | `nivelSigilo > 0` é descartado | ~0,3 s |
| integração | código de movimento desconhecido persiste com aviso | ~0,3 s |
| **meta** | **nenhuma chave literal no código** (grep) | ~0,2 s |

**Total:** ~2,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Chave só em configuração · Alerta de 401 funcionando · Commit `feat(046): DataJud — client`
