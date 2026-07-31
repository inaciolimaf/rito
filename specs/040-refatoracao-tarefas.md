# 040 — 🔧 REFATORAÇÃO — Tarefas

**Fase:** 3 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 031–039 · **Status:** ⬜ pendente

---

## 1. Objetivo

`posts` virou a tabela mais acessada do sistema e `PostService` provavelmente cresceu demais.
Além disso, três lógicas de calendário nasceram separadas — recorrência (034), dias úteis (038)
e agenda (037) — e vão ser reusadas por intimações (086) e financeiro (057).

> Refatoração não muda comportamento. Testes de 031–039 passam **sem edição**.

## 2. Alvo 1 — módulo de datas único

- [ ] Extrair `app/core/dates.py`: dias úteis, feriados, próxima ocorrência de recorrência, fim de mês, última semana do mês
- [ ] Zero dependência de framework — função pura, testável isolada
- [ ] Migrar 034, 037 e 038 para ele
- [ ] Documentar que 057 (parcelamento) e 086 (prazo processual) devem usá-lo

## 3. Alvo 2 — quebrar o PostService

Se passou de ~300 linhas, divida por caso de uso:
- [ ] `CreatePostUseCase` (com expansão de time e detecção de duplicata)
- [ ] `CompletePostUseCase` (com crédito de pontos e geração de recorrência)
- [ ] `InboxQueryService` (seções e contadores)
- [ ] `TaskscoreService` (agregação e ranking)

## 4. Alvo 3 — performance da caixa de entrada

É a tela mais aberta do produto. Ela tem que ser rápida.

- [ ] Contadores das 6 seções em **1 query** (verificar se ficou assim mesmo)
- [ ] Listagem sem N+1 em partes, responsáveis e tipo de tarefa
- [ ] `EXPLAIN ANALYZE` com 10.000 tarefas semeadas
- [ ] Índices parciais de `post_users` sendo usados de fato

## 5. Checklist

### Cobertura
- [ ] Toda regra numerada de 031–039 com teste
- [ ] Matriz de pontuação: 25 combinações
- [ ] Casos de borda de calendário: bissexto, mês curto, última semana
- [ ] Privacidade de tarefa testada contra GESTOR
- [ ] iCal validado por parser real
- [ ] Isolamento entre tenants nas 7 tabelas novas

### SOLID
- [ ] `dates.py` puro
- [ ] `FileStorage` como interface (035 não pode ter acoplado ao disco local)
- [ ] Geração de iCal em serviço próprio, não no router
- [ ] Nenhum use case acima de ~150 linhas

### Duplicação
- [ ] Lógica de data unificada (alvo 1)
- [ ] `attachments` e `notifications` genéricas o bastante para contatos e financeiro
- [ ] Padrão de listagem de 030 aplicado à caixa de entrada

### Banco
- [ ] View materializada refresca concorrente, sem lock
- [ ] Índices parciais usados
- [ ] Cascades corretos (excluir processo → tarefas → comentários → anexos)
- [ ] Nenhum órfão possível

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] E2E com no máximo 6 jornadas até aqui
- [ ] Fixture de 10.000 tarefas só nos testes que precisam, em escopo de sessão

## 6. Entregáveis

1. `app/core/dates.py` com cobertura completa
2. `PostService` dividido
3. Caixa de entrada medida com 10.000 tarefas, com o número no `docs/DECISOES.md`
4. `test-timing.json` atualizado
5. Dívidas em `docs/DIVIDA-TECNICA.md`

## 7. Definição de pronto

- [ ] Testes de 031–039 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Caixa de entrada < 200 ms com 10.000 tarefas
- [ ] Commit `refactor(040): módulo de datas e pente fino das tarefas`
