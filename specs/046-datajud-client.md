# 046 — DataJud: client

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 041 · **Status:** ✅ concluída

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

- **Fixtures 100% reais, capturadas ao vivo.** Não existe endpoint público consultável
  para baixar a Tabela Processual Unificada inteira (o "Sistema de Gestão de Tabelas"
  do CNJ é uma página `sajax` legada, não dá pra fazer scraping simples). Em vez de
  inventar códigos de movimento, usei a própria APIKey pública (a mesma publicada no
  tutorial oficial "API Pública do Datajud" do DPJ/CNJ, replicada em `.env.example`)
  para consultar `api_publica_tjsp/_search` ao vivo em 2026-08-10: uma busca por
  `numeroProcesso` real virou a fixture `tjsp_processo.json` (truncada de 50/152
  movimentos reais para 5/8, nenhum campo alterado), uma chave inválida de propósito
  virou `401_chave_invalida.json` com o corpo real do `security_exception`, e uma
  varredura de 50 processos (`match_all`) rendeu os 71 pares `(código, nome)` reais
  que viraram o seed de `cnj_movement_codes` (`movement_codes_seed.py`) — zero dado
  inventado, tudo com proveniência documentada no README das fixtures.
- **`datajud_alias` já vinha seedado desde a migration 021.** A spec 021
  (tribunais/sistemas) já populou `courts.datajud_alias` para todos os tribunais com
  API pública (ex.: `TJSP` → `api_publica_tjsp`) e deixou `NULL` para os que não têm
  (CNJ, STF) — esta spec só leu a coluna, não precisou popular nada.
- **`dataAjuizamento` foge do padrão ISO do resto do payload** — chega como
  `AAAAMMDDHHmmss` (string de 14 dígitos), não `AAAA-MM-DDTHH:mm:ssZ` como
  `movimentos[].dataHora`/`dataHoraUltimaAtualizacao`. Um parser genérico de
  datetime quebraria nesse campo — `_to_compact_datetime` trata o formato à parte.
- **Regra 6/7 exigem banco — não podem morar no parser puro.** O parser
  (`app/integrations/datajud/parser.py`) não sabe o que é sigilo>0 nem quais
  códigos de movimento já são conhecidos (isso é estado, não payload). Essas duas
  regras ficaram no `DatajudService` (`app/domain/datajud/service.py`), que tem
  acesso a `CourtRepository`/`CnjMovementCodeRepository`/`IntegrationAlertRepository`
  — o parser continua 100% função pura (regra 10), testável sem sessão nenhuma.
- **`routed_by`-like discrepância no comentário da migration, de novo:** o comentário
  original de `routed_by`/`matched_by` em specs anteriores já tinha esse padrão de
  ficar incompleto — aqui não há CHECK constraint em `integration_alerts.severity`/
  `code`/`integration`, são texto livre por design (auditoria, não enum fechado).
- **`integration_alerts.tenant_id` nulo quebra o padrão usual de RLS — e quebrou um
  teste.** A política padrão (`enable_rls_statements`) exige match exato de tenant;
  para liberar alerta de SISTEMA a QUALQUER tenant, a migration 046 usa uma política
  custom (`tenant_id IS NULL OR tenant_id = current_setting(...)`). Isso significa
  que uma linha com `tenant_id` nulo é visível para **toda** sessão autenticada —
  incluindo sessões de testes concorrentes rodando em paralelo (`pytest -n auto`) ou
  de execuções anteriores da mesma suíte. O teste do alerta de 401 batia
  `MultipleResultsFound` com `.one()` porque cada execução anterior deixava uma linha
  órfã no `rito_test` compartilhado (nada faz `TRUNCATE integration_alerts` entre
  runs — `run-tests.sh` só trunca `tenants CASCADE`, que não alcança linha com FK
  nula). Corrigido fazendo o teste **não commitar**: `IntegrationAlertRepository.
  create` só dá `flush` (nunca `commit`), então basta não usar `session.begin()` no
  teste — a leitura de volta enxerga o INSERT dentro da própria transação, e fechar a
  sessão sem commitar descarta tudo. Fica registrado como armadilha para qualquer
  spec futura (049?) que também grave nessa tabela em teste.
- **Endpoint `GET /integration-alerts` não estava no §5/§6 explícito da spec, mas é
  necessário.** A spec só desenhou o `IntegrationAlertBanner` no front; sem uma rota
  para ele consumir, o banner seria inerte. Adicionei `GET /api/v1/integration-alerts`
  (COLABORADOR+, lista abertos) — infraestrutura mínima para o componente descrito
  funcionar, não escopo novo de feature.
- **`DatajudService`/domínio `app/domain/datajud/` nasce aqui, magro de propósito.**
  Só tem `fetch_process` (uma consulta) — a persistência incremental em
  `lawsuit_movements` com `dataHoraUltimaAtualizacao` é da spec 047, que estende este
  service em vez de recriar client/parser.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (persistência de andamentos fica para a 047,
      como o §3 determina)
- [x] Todas as regras de negócio com teste (17 testes — 3 unit de parser, 7
      integração de client, 5 integração de service, 2 meta; as 10 regras numeradas
      do §7 cobertas individualmente)
- [x] Teste de isolamento por tenant (RLS custom de `integration_alerts` verificado
      via `tenant_id IS NULL` visível a qualquer sessão + isolamento normal para
      linhas com tenant; `cnj_movement_codes` é taxonomia global sem tenant, mesmo
      padrão de `courts` desde a spec 021)
- [x] `make test` verde e wall-clock < 300 s (216 s — 698 backend, 134 frontend, 7 e2e)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (`IntegrationAlertBanner`
      em `components/domain/`, pronto para a 049 reusar com o DJEN; `get_or_404`,
      `HttpClient`/`ResilientHttpClient` da 041 reaproveitados sem duplicar)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(046): DataJud — client`
