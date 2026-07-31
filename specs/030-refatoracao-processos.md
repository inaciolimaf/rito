# 030 — 🔧 REFATORAÇÃO — Processos

**Fase:** 2 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 021–029 · **Status:** ⬜ pendente

---

## 1. Objetivo

O núcleo do domínio está de pé. Esta refatoração tem dois alvos concretos: **o orçamento de
teste já estourou** (a spec 027 declarou 9,7 s contra 7 s de teto) e o padrão de listagem com
visões rápidas precisa virar infraestrutura antes de ser copiado para tarefas, financeiro e CRM.

> Refatoração não muda comportamento. Testes de 021–029 passam **sem edição**.

## 2. Alvo 1 — devolver o orçamento

- [ ] Medir o wall-clock atual e registrar em `test-timing.json`
- [ ] Se > 90 s: converter jornadas e2e em teste de integração, mantendo só as essenciais
- [ ] Consolidar seeds de teste: um único fixture de sessão com tenant, usuários, taxonomias e 20 processos
- [ ] Substituir setup por teste por transação com rollback onde ainda não estiver
- [ ] Verificar paralelismo real do `pytest-xdist` (workers ociosos?)

## 3. Alvo 2 — extrair o padrão de listagem

Contatos (019) e processos (027) já repetiram: visões rápidas + filtros combináveis + keyset +
export + estado na URL. Falta uma terceira ocorrência para a regra dos 3 usos, mas ela é certa
(tarefas em 036). Extraia agora:

- [ ] `ListQueryBuilder` no backend: filtros declarativos → SQL, com AND entre grupos e OR dentro
- [ ] `QuickViews` declarativas: nome → predicado
- [ ] `ExportService` genérico: xlsx e pdf a partir de queryset + colunas
- [ ] `useListPage` no frontend: URL + query + paginação + export num hook
- [ ] `ListPageLayout`: dashboard recolhível + filtros + tabela

## 4. Checklist

### Cobertura
- [ ] Toda regra numerada de 021–029 com teste
- [ ] As 12 visões testadas individualmente
- [ ] Tabela de números CNJ cobrindo os 9 segmentos
- [ ] Isolamento entre tenants nas tabelas novas
- [ ] Constraints de ciclo de datas testadas no banco

### SOLID
- [ ] `cnj.py` puro, sem FastAPI nem SQLAlchemy
- [ ] Agregação da timeline em service próprio, não no router
- [ ] Trigger de `last_movement_at` documentada em `docs/DECISOES.md`
- [ ] `LawsuitService` não passa de ~300 linhas (senão, divida por caso de uso)

### Duplicação
- [ ] Padrão de listagem extraído (alvo 2)
- [ ] `MoneyField`, `PercentField`, `ProcessNumberField` em um só lugar
- [ ] Lógica de "intervalo de datas" unificada entre contatos e processos

### Banco
- [ ] `EXPLAIN ANALYZE` nas 12 visões — nenhuma com seq scan em tabela grande
- [ ] Índices parciais realmente usados
- [ ] Timeline em ≤ 3 statements; listagem em ≤ 3
- [ ] Trigger sem lock desnecessário

### Tipos
- [ ] `mypy --strict` e `tsc --noEmit` verdes
- [ ] Enums do banco espelhados em TS sem duplicação manual

## 5. Entregáveis

1. Wall-clock de volta abaixo de 90 s
2. Padrão de listagem extraído e as duas telas migradas
3. `docs/DECISOES.md` com a decisão da coluna materializada
4. `test-timing.json` atualizado
5. Dívidas em `docs/DIVIDA-TECNICA.md`

## 6. Definição de pronto

- [ ] Testes de 021–029 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Uma listagem nova custa < 80 linhas (demonstre com a de tarefas)
- [ ] Commit `refactor(030): padrão de listagem e pente fino dos processos`
