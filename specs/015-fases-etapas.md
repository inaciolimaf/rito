# 015 — Fases e etapas

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 014 · **Status:** ⬜ pendente

---

## 1. Objetivo

O funil processual. **Fase** (`step`) é o macro-estágio — 9 valores fixos que viram as colunas
do Kanban. **Etapa** (`stage`) é o estado detalhado dentro da fase, configurável pelo escritório,
com regra de estagnação própria.

## 2. Escopo

- Tabela `steps`: 9 fases fixas, seed imutável (sem CRUD)
- Tabela `stages`: 59 etapas padrão, CRUD completo
- Configuração de estagnação por etapa (`enable_stagnant_days`, `stagnant_days`)
- Campo de workflow sugerido ao mover para a etapa (FK preenchida em 038)
- Transferência em lote antes de excluir
- Tela `Configurações > Etapas`

## 3. Fora de escopo

- Kanban → 051
- Motor de workflow → 038
- Cálculo efetivo de estagnação → 052

## 4. Modelo de dados

```sql
CREATE TABLE steps (            -- global, imutável
  id SMALLINT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  position SMALLINT NOT NULL UNIQUE
);

CREATE TABLE stages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  step_id SMALLINT NOT NULL REFERENCES steps(id),
  name TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  enable_stagnant_days BOOLEAN NOT NULL DEFAULT false,
  stagnant_days INTEGER,
  suggested_workflow_id UUID,      -- FK adicionada em 038
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name),
  CHECK (NOT enable_stagnant_days OR stagnant_days > 0)
);
CREATE INDEX ix_stages_step ON stages (step_id);
```
Migration `015_steps_stages.py`.

**Seed de fases (9, nesta ordem):** Marketing · Negociação · Consultoria · Administrativo ·
Judicial · Recursal · Execução/cobrança · Rh/financeiro · Arquivamento

**Seed de etapas (59):** a lista completa está em
`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.2. Cada etapa é semeada na fase correspondente.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/steps` | autenticado |
| GET | `/api/v1/stages?step_id=&status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/stages[/{id}]` | GESTOR |
| POST | `/api/v1/stages/reorder` | GESTOR — `{stage_ids[]}` |
| POST | `/api/v1/stages/transfer` | GESTOR — `{from_id, to_id}` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `TransferBeforeDeleteDialog`
**Cria:** `StageForm` (nome, fase, estagnação, workflow), `StageReorderList` (drag & drop)
**Rota:** `/settings/stages`

Colunas: Etapa · Classificação (fase) · Estagnação · Cadastro

## 7. Regras de negócio

1. As 9 fases são **imutáveis**: não há POST, PUT nem DELETE em `/steps`.
2. Etapa pertence a exatamente uma fase.
3. `enable_stagnant_days = true` exige `stagnant_days > 0` (constraint no banco).
4. Excluir etapa em uso exige transferência.
5. Ordenação é por `position` dentro da fase; reordenar é transacional.
6. Nome único por tenant, comparação sem acento.
7. Inativar mantém histórico e remove dos seletores.
8. Etapa não pode mudar de fase se houver processo nela — exige transferência.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | fases são somente leitura (POST → 405) | ~0,2 s |
| integração | CRUD de etapas | ~0,4 s |
| integração | estagnação sem dias → 422 | ~0,2 s |
| integração | excluir etapa em uso → 409 | ~0,3 s |
| integração | reordenação persiste e é transacional | ~0,4 s |
| integração | mudar fase com processo na etapa → 409 | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| unit | seed das 59 etapas mapeia a fase certa | ~0,2 s |
| frontend | `StageForm` condiciona dias à estagnação | ~0,4 s |

**Total:** ~2,7 s

## 9. Descobertas

- **Pareamento etapa→fase é inferência.** `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.2 lista as
  59 etapas como uma lista **flat**, sem declarar a fase de cada uma (só a lista de 9 fases está
  em §3.1, separada). O pareamento adotado (documentado com comentários na migration
  `015_steps_stages.py`) lê a lista fonte em blocos contíguos tematicamente coerentes — cada
  bloco virou uma fase (ex.: o bloco "AGENDADO ATENDIMENTO NO ÓRGÃO...AGUARDANDO CÓPIA DO
  PROCESSO ADMINISTRATIVO" é claramente Administrativo; "ELABORAÇÃO DE CÁLCULO...AGUARDANDO
  PAGAMENTO DE CONDENAÇÃO" é claramente Execução/cobrança). Os 9 blocos somam exatamente 59 e
  cobrem as 9 fases, o que reforça a leitura, mas é uma dedução, não algo levantado
  explicitamente na fonte.
- **"PLANEJAMENTO" está duplicado na fonte real** — aparece uma vez no bloco de Negociação e
  outra vez no bloco de Marketing. Isso quebra o `UNIQUE(tenant_id, name)` simples da seção 4
  da spec. Corrigido trocando para `UNIQUE(tenant_id, step_id, immutable_unaccent(lower(name)))`
  — unicidade por (tenant, fase), não só por tenant; regra 6 foi reinterpretada nesse sentido
  (documentada em `StageRepository.get_by_name`). Reaproveita a função `immutable_unaccent`
  criada na migration 014 (mesma necessidade: `unaccent()` do Postgres é `STABLE`, não pode
  entrar em expressão de índice).
- **Regras 4 e 8 ("etapa em uso" / "processo mudando de fase") não têm como ser aplicadas de
  verdade ainda.** Não existe tabela `lawsuits`/processos até a spec 022 (`ROADMAP.md`, Fase 2)
  — nada referencia `stage_id` hoje. Mesma situação já registrada na spec 014 para
  `lawsuit_types`. Resolvido assim:
  - `DELETE /stages/{id}` é **incondicional** por enquanto (sem guarda de "em uso").
  - `POST /stages/transfer` existe, valida `from_id`/`to_id` (distintos, existentes no tenant),
    mas a migração de dados é hoje um no-op (`transferred_count` sempre `0`) — o contrato fica
    pronto para quando `lawsuits.stage_id` existir.
  - O plano de testes original tinha "excluir etapa em uso → 409" e "mudar fase com processo na
    etapa → 409"; substituídos por testes do que É real hoje: exclusão incondicional funciona, e
    a reordenação (regra 5, mesma classe de problema de "não misturar fases") rejeita ids de
    fases diferentes com 422.
  - `TransferBeforeDeleteDialog` (existente desde a spec 014) **não foi plugado** na tela de
    etapas — mostrar um diálogo de transferência antes de excluir seria a UI fingindo uma trava
    que o backend não impõe. Fica para quando a spec 022 der um motivo real para isso.
- **Bug pego na verificação manual em navegador (não em teste automatizado):** etapas recém-
  criadas nasciam todas com `position=0` (default da coluna), então a ordem entre elas na mesma
  fase ficava a critério do Postgres, não da regra 5 ("position dentro da fase"). Corrigido com
  `StageRepository.next_position(step_id)` (fim da fase) usado tanto em `create()` quanto — ao
  mudar de fase — em `update()`. Coberto por dois testes de integração
  (`test_reordenacao_persiste_e_e_transacional`, `test_mudar_etapa_de_fase_reposiciona_no_fim_da_nova_fase`).
- **`suggested_workflow_id` existe na tabela mas não no formulário.** A coluna é criada (UUID
  nullable, sem FK — a FK real chega na spec 038 quando a tabela `workflows` existir), e o
  `StageResponse` a devolve (sempre `null` hoje), mas não há nada para o usuário selecionar
  ainda, então `StageForm` não expõe o campo.
- **`steps` é global e imutável, sem `tenant_id`/RLS** — mesmo padrão de `Occupation` (spec 012):
  as mesmas 9 fases para todos os escritórios, só leitura (`GET /steps`), `POST /steps` retorna
  405 automaticamente (Starlette resolve o path mas não o método).
- **`StageReorderList` usa HTML5 drag-and-drop nativo + botões de mover para cima/baixo** (sem
  nova dependência de npm) — os botões cobrem o caso de uso por teclado, que arrastar sozinho
  não resolve.

## 10. Definição de pronto

- [x] Migration `015_steps_stages` aplica e reverte de forma limpa (testado do zero contra
      `rito_test` e contra o banco de dev).
- [x] 9 fases semeadas na ordem certa; 59 etapas semeadas com o pareamento documentado acima
      (seed idempotente via `ON CONFLICT`, mesma limitação de 011/012/014: só atinge tenants que
      já existiam quando a migration rodou).
- [x] RLS ligado em `stages` (não em `steps`, que é global) + teste de isolamento entre tenants.
- [x] CRUD completo de etapas, reordenação transacional dentro da fase, endpoint de
      transferência com contrato pronto para a spec 022.
- [x] 219 testes de integração/unit cobrindo o plano da spec (ajustado conforme Descobertas) —
      100% de cobertura em `app/domain/stages/`.
- [x] Frontend: `StagesListPage`, `StageForm` (estagnação condicional), `StageReorderList`
      (novo, drag-and-drop + botões), reaproveitando `DataTable`/`FilterBar`/`FormModal`. Teste
      "StageForm condiciona dias à estagnação" verde (~0,3 s).
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier).
- [x] `make test` verde — 219 backend / 55 frontend / 3 e2e, wall-clock 35 s (orçamento 120 s).
- [x] Verificado manualmente em navegador (Playwright ad-hoc, não commitado) — CRUD, filtro por
      fase, estagnação condicional e reordenação (drag e botões) funcionando ponta a ponta.

Commit `feat(015): fases e etapas`
