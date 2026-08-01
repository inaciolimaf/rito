# 014 — Grupos e tipos de ação

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 011 · **Status:** ⬜ pendente

---

## 1. Objetivo

A taxonomia que classifica processos por área do direito. O **grupo de ação** também define
quem recebe as intimações daquela área — é peça central do roteamento da spec 045.

## 2. Escopo

- Tabela `action_groups` com responsável por intimações (6 padrão)
- Tabela `lawsuit_types` vinculada a grupo (10 padrão)
- CRUD de ambos + transferência em lote antes de excluir
- Telas `Configurações > Grupos de ação` e `> Tipos de ação`

## 3. Fora de escopo

- Fases e etapas → 015
- Metas por grupo → 039

## 4. Modelo de dados

```sql
CREATE TABLE action_groups (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  publications_user_id UUID REFERENCES users(id),  -- responsável por intimações
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE lawsuit_types (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  action_group_id UUID NOT NULL REFERENCES action_groups(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX ix_lawsuit_types_group ON lawsuit_types (action_group_id);
```
Migration `014_action_groups_types.py`.

**Seed de grupos (6):** ADMINISTRATIVO · CÍVEL · FINANCEIRO/RH · PENAL · PREVIDENCIÁRIO · TRABALHISTA

**Seed de tipos (10):** ACUSAÇÃO DE ESTELIONATO · ADMISSÃO DE FUNCIONÁRIO · APOSENTADORIA POR
IDADE · CONCESSÃO DE FÉRIAS · CONCESSÃO DE FOLGA · DEMISSÃO DE FUNCIONÁRIO · JUSTIFICAÇÃO DE
FALTA · NULIDADE DE LICITAÇÃO · RECLAMATÓRIA TRABALHISTA · REINTEGRAÇÃO DE POSSE

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/action-groups?status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/action-groups[/{id}]` | GESTOR |
| GET | `/api/v1/lawsuit-types?group_id=&status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/lawsuit-types[/{id}]` | GESTOR |
| POST | `/api/v1/lawsuit-types/transfer` | GESTOR — `{from_id, to_id}` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `ConfirmDialog`, `EntityPicker`
**Cria:** `TransferBeforeDeleteDialog` (reutilizado por 015 e 016)
**Rotas:** `/settings/action-groups`, `/settings/lawsuit-types`

## 7. Regras de negócio

1. Nome único por tenant, case-insensitive e sem acento na comparação (`unaccent`).
2. Tipo de ação **sempre** pertence a um grupo. Grupo é derivado do tipo no processo — nunca informado direto.
3. Excluir grupo ou tipo em uso exige **transferência**: os registros migram para o destino escolhido.
4. `publications_user_id` opcional. Vazio → intimação cai no responsável geral (spec 045).
5. Inativar mantém o histórico; o item some dos seletores de novos registros.
6. Só GESTOR escreve.
7. Transferência é transacional: ou migra tudo, ou nada.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD dos dois | ~0,5 s |
| integração | nome duplicado ignorando acento → 409 | ~0,3 s |
| integração | excluir tipo em uso sem transferir → 409 | ~0,3 s |
| integração | transferência migra e é transacional | ~0,5 s |
| integração | tipos filtrados por grupo | ~0,3 s |
| integração | Colaborador → 403 | ~0,2 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | seleção de tipo filtra pelo grupo | ~0,4 s |

**Total:** ~2,8 s

## 9. Descobertas

- **Unicidade real exige índice funcional, não `UNIQUE` simples.** A seção 4 original listava
  `UNIQUE (tenant_id, name)`, mas a regra 1 pede comparação sem acento e case-insensitive.
  `unaccent()` do Postgres é `STABLE`, não `IMMUTABLE` — não pode entrar numa expressão de
  índice. Solução: uma função wrapper `immutable_unaccent(text)` (`IMMUTABLE PARALLEL SAFE
  STRICT`) criada pela própria migration 014, usada só na expressão do índice
  (`UNIQUE (tenant_id, immutable_unaccent(lower(name)))`); consultas normais em `WHERE`
  continuam usando o `unaccent()` nativo do Postgres. Reaproveitável por 015/016 (mesma regra
  de unicidade normalizada em outras taxonomias).
- **Semântica de `from_id`/`to_id` no `POST /lawsuit-types/transfer`:** a spec não deixava
  explícito a quem esses ids se referem. Não existe ainda tabela `lawsuits` (processos) — nada
  torna um `lawsuit_type` "em uso" hoje. Interpretação adotada: `from_id`/`to_id` são ids de
  **action_group**; o endpoint migra todos os `lawsuit_types` de um grupo para outro. "Excluir
  tipo em uso" do plano de testes (seção 8) foi lido como "excluir **grupo** com tipos
  vinculados" — é o único cenário de "em uso" que o schema atual permite. `lawsuit_type` em si
  não tem guarda de exclusão (nada referencia um tipo individual ainda); isso muda quando a
  spec de Processos existir.
- **Pareamento tipo→grupo é inferência.** `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` lista os 6
  grupos e os 10 tipos como listas **flat**, sem declarar qual tipo pertence a qual grupo. O
  pareamento na migration (`_TYPES_BY_GROUP`) foi inferido pelo nome (ex.: "RECLAMATÓRIA
  TRABALHISTA" → TRABALHISTA) e está documentado como tal no próprio arquivo da migration —
  não é um fato levantado da fonte, é uma dedução razoável.
- **Seed só atinge tenants que já existem no momento em que a migration roda** (mesma limitação
  já registrada em 011/012: não existe spec de provisionamento de tenant ainda). Tenants criados
  depois — inclusive em teste, via `make_user` — não recebem os 6 grupos/10 tipos automaticamente;
  cada teste cria os próprios registros via API, igual squads/users já fazem.
- **Sem `updated_at`/`onupdate` nestas duas tabelas** — o bug de `MissingGreenlet` corrigido na
  spec 013 (squads) não se aplica aqui; `update()` nos dois services não precisa de
  `session.refresh()` porque não há coluna que fique "expirada" por autoflush.
- **Confirmado via smoke manual em navegador** (Playwright ad-hoc, não commitado): login,
  criação de grupo, criação de tipo com grupo selecionado no formulário, e o fluxo completo de
  "excluir grupo com tipos vinculados → dialog de transferência → escolher destino → transferir
  e excluir" funcionam ponta a ponta contra o backend real.
- **Achado de ambiente (não é bug do Rito):** ao rodar os testes manualmente neste sandbox,
  usar a role `rito` (superusuário, `BYPASSRLS`) em `TEST_DATABASE_URL` — em vez de `rito_app`
  — faz o RLS parecer quebrado (lista cruza tenants, checagem de nome duplicado enxerga outros
  tenants). Isso já estava documentado na memória do projeto sobre este sandbox; o app em si
  está correto — confirmado revertendo para `rito_app` e vendo os 23 testes (incluindo o de
  isolamento entre tenants) passarem.

## 10. Definição de pronto

- [x] Migration `014_action_groups_types` aplica e reverte de forma limpa (`upgrade`/`downgrade`
      testados manualmente contra `rito_test` do zero).
- [x] Seeds idempotentes (`ON CONFLICT ... DO NOTHING` na expressão do índice único).
- [x] RLS ligado (`ENABLE`/`FORCE ROW LEVEL SECURITY`) + teste de isolamento entre tenants.
- [x] CRUD completo dos dois recursos + transferência em lote transacional.
- [x] 23 testes de integração cobrindo as 8 linhas do plano de testes e mais (erros 404/409/422,
      filtros de listagem) — 100% de cobertura em `app/domain/action_groups/`.
- [x] Frontend: `ActionGroupsListPage`, `LawsuitTypesListPage`, `TransferBeforeDeleteDialog`
      (novo componente reutilizável, spec 015/016), reaproveitando `DataTable`/`FilterBar`/
      `FormModal`/`ConfirmDialog`/`EntityPicker`. Teste "seleção de tipo filtra pelo grupo"
      verde (~0,4 s).
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier).
- [x] `make test` verde — backend 196 testes / ~13 s, frontend 54 testes / ~19 s, dentro do
      orçamento de 120 s combinado.
- [x] Verificado manualmente em navegador (Playwright ad-hoc, não commitado).

Commit `feat(014): grupos e tipos de ação`
