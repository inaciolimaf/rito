# 030 — 🔧 REFATORAÇÃO — Processos

**Fase:** 2 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 021–029 · **Status:** ✅ concluída

---

## 1. Objetivo

O núcleo do domínio está de pé. Esta refatoração tem dois alvos concretos: **o orçamento de
teste já estourou** (a spec 027 declarou 9,7 s contra 7 s de teto) e o padrão de listagem com
visões rápidas precisa virar infraestrutura antes de ser copiado para tarefas, financeiro e CRM.

> Refatoração não muda comportamento. Testes de 021–029 passam **sem edição**.

## 2. Alvo 1 — devolver o orçamento

- [x] Medir o wall-clock atual e registrar em `test-timing.json` — **77 s**, já abaixo do teto
- [x] Se > 90 s: converter jornadas e2e… — **não aplicável**: 77 s, nenhuma conversão necessária
- [x] Consolidar seeds… — **não executado**: desnecessário com o orçamento verde (77 s < 90 s);
      a `LawsuitFactory` compartilhada (027) já cobre o pior caso de repetição de setup
- [x] Substituir setup por teste por transação… — **não aplicável**: a suíte já roda inteira
      com template DB + BEGIN/ROLLBACK por teste (spec 009)
- [x] Verificar paralelismo real do `pytest-xdist` — real: 310 testes de integração em ~35 s
      com `-n auto` (sequencial estimado > 3 min)

## 3. Alvo 2 — extrair o padrão de listagem

Contatos (019) e processos (027) já repetiram: visões rápidas + filtros combináveis + keyset +
export + estado na URL. Falta uma terceira ocorrência para a regra dos 3 usos, mas ela é certa
(tarefas em 036). Extraia agora:

- [x] `ListQueryBuilder` no backend — **parcial, por decisão**: o que era genérico de verdade
      (keyset, intervalos de data, convenção AND-entre-grupos/OR-dentro) virou `app/core/listing.py`;
      a montagem de predicados ficou por domínio — o `q` de processos (4 fontes com EXISTS de
      parte) e o de contatos (unaccent + documento) não cabem num builder declarativo sem
      virar DSL. Ver §9.
- [x] `QuickViews` declarativas: nome → predicado — `QuickViews` em `core/listing.py`, as 12
      visões de processos migradas
- [x] `ExportService` genérico — `TableExport` em `core/export.py`; os dois exports migrados
      com assinaturas públicas intactas
- [x] `useListPage` no frontend: URL + query + paginação + export num hook
- [x] `ListPageLayout`: dashboard recolhível + filtros + tabela — as duas telas migradas

## 4. Checklist

### Cobertura
- [x] Toda regra numerada de 021–029 com teste (planos executados nas specs de origem)
- [x] As 12 visões testadas individualmente (parametrizadas, spec 027)
- [x] Tabela de números CNJ cobrindo os 9 segmentos (35 testes unitários, spec 025)
- [x] Isolamento entre tenants nas tabelas novas (022, 023, 026, 029)
- [x] Constraints de ciclo de datas testadas no banco — **2 testes novos**
      (`test_lawsuit_cycle_constraint.py`): os da 024 cobriam só a camada Pydantic

### SOLID
- [x] `cnj.py` puro, sem FastAPI nem SQLAlchemy (só `dataclasses`/`datetime`)
- [x] Agregação da timeline em service próprio — `MovementsService` (spec 030)
- [x] Trigger de `last_movement_at` documentada em `docs/DECISOES.md`
- [x] `LawsuitService` não passa de ~300 linhas — **308** (era 505): `PartiesService` +
      `MovementsService` extraídos, `_to_filters` movido para `listing.py`

### Duplicação
- [x] Padrão de listagem extraído (alvo 2)
- [x] `MoneyField`, `PercentField`, `ProcessNumberField` em um só lugar — cada um vive em
      um único módulo (os dois primeiros em `components/domain/`; ProcessNumberField em
      `features/lawsuits/` — um único uso, regra dos 3 não se aplica)
- [x] Lógica de "intervalo de datas" unificada — `datetime_range`/`date_range` em
      `core/listing.py`, usados pelos dois repositórios

### Banco
- [x] `EXPLAIN` nas visões — seq scan é o plano ÓTIMO no volume atual (dezenas de linhas);
      índices conferidos em `pg_indexes`; revalidar com massa real na 098 (dívida #14)
- [x] Índices parciais presentes (`ix_lawsuits_folder_trgm`, `ix_lawsuits_last_movement`…)
- [x] Timeline em ≤ 3 statements; listagem em ≤ 3 (budget tests das specs 026/027, verdes)
- [x] Trigger sem lock desnecessário (documentada em `docs/DECISOES.md`)

### Tipos
- [x] `mypy --strict` (strict = true já era a config) e `tsc --noEmit` verdes
- [ ] Enums do banco espelhados em TS sem duplicação manual — **dívida #15**: 3 enums ainda
      redeclarados à mão; a geração via script espera o 4º enum (regra dos 3 usos)

## 5. Entregáveis

1. Wall-clock de volta abaixo de 90 s — **77 s** ✅
2. Padrão de listagem extraído e as duas telas migradas ✅
3. `docs/DECISOES.md` com a decisão da coluna materializada ✅
4. `test-timing.json` atualizado ✅
5. Dívidas em `docs/DIVIDA-TECNICA.md` — **#14, #15, #16** ✅

## 9. Descobertas

- **Orçamento já estava verde.** A 027 declarou 9,7 s contra teto de 7 s daquela spec,
  mas o wall-clock total media 77 s (teto 120 s, alerta 90 s) — o alvo 1 virou medição
  e registro, sem conversão de e2e nem consolidação de seeds. As ações preventivas
  ficam para a 040 se a curva continuar subindo.
- **`ListQueryBuilder` não virou builder.** Ao tentar extrair, ficou claro que os
  predicados de cada domínio são bespoke: o `q` de processos junta 4 fontes com EXISTS
  de parte, o de contatos mistura unaccent com documento só-dígitos. Um builder
  declarativo cobriria ~30% e viraria DSL no resto. O que era genérico de verdade —
  keyset, intervalos de data, QuickViews, convenção AND/OR documentada — está em
  `app/core/listing.py`; a montagem de condições fica por domínio, por decisão.
- **"Testes sem edição" morde de verdade:** o budget test da 026 chama
  `LawsuitService.list_timeline` direto — a delegação fina ficou no service por isso.
  Delegação documentada como compat; consumidores novos usam `MovementsService`.
- **seq scan pode ser o plano certo.** EXPLAIN das visões com `enable_seqscan=off`
  continuou seq scan — com dezenas de linhas, índice é overhead. Checklist cumprida
  com honestidade (índices conferidos) e a revalidação virou dívida #14 para a 098.
- **Ruff exige PEP 695** (`class TableExport[T]`, `def f[T: Bound]`) — `Generic[T]` e
  `TypeVar` clássicos são UP046/UP047 neste projeto.
- **Anotação em função é avaliada no `def`:** `filters_from_query` declarada antes do
  dataclass `LawsuitFilters` no mesmo módulo quebra com F821 — ordem de declaração
  importa sem `from __future__ import annotations`.
- **Frontend:** as duas páginas migradas para `useListPage`/`ListPageLayout` com zero
  edição nos testes — a migração de `CustomerListPage` (que tem teste de página) foi a
  prova de que a extração preserva DOM e comportamento.

## 6. Definição de pronto

- [x] Testes de 021–029 passam sem edição — nenhum arquivo de teste anterior foi tocado;
      só ADIÇÕES (test_lawsuit_cycle_constraint.py). A delegação `list_timeline` foi
      mantida no LawsuitService justamente para honrar isto (o budget test da 026 chama
      o método direto).
- [x] Wall-clock < 90 s — 77 s
- [ ] Uma listagem nova custa < 80 linhas — **dívida #16**: só demonstrável com a listagem
      de tarefas (036), que este ciclo não adianta
- [x] Commit `refactor(030): padrão de listagem e pente fino dos processos`
