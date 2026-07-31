# 060 — 🔧 REFATORAÇÃO — CRM e Financeiro I

**Fase:** 5 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 051–059 · **Status:** ⬜ pendente

---

## 1. Objetivo

O módulo financeiro é o que mais tolera erro mal — número errado em tela de dinheiro destrói
confiança no produto inteiro. Esta refatoração é sobre **exatidão numérica** e sobre consolidar
o padrão de agregação antes das 4 abas de BI (074–077).

> Refatoração não muda comportamento. Testes de 051–059 passam **sem edição**.

## 2. Alvo 1 — auditoria de exatidão numérica

- [ ] Todo valor monetário é `NUMERIC(14,2)` no banco e `Decimal` no Python — **zero `float`** em qualquer caminho de dinheiro (grep no CI)
- [ ] Arredondamento sempre `ROUND_HALF_UP`, nunca o padrão do Python (banker's rounding)
- [ ] Soma de parcelas fecha exatamente com o total (já testado em 057 — confirme que vale para 2 a 100)
- [ ] Saldo calculado pela view = saldo calculado por soma direta, no mesmo dataset
- [ ] Os 4 regimes de 059 sobre o mesmo dataset produzem números coerentes entre si
- [ ] Nenhum cálculo de dinheiro no frontend — a UI só formata

## 3. Alvo 2 — padrão de agregação

059 fez view materializada com refresh; 039 também; 074–077 vão fazer mais quatro. Extraia:

- [ ] `MaterializedAggregate`: definição, refresh concorrente, invalidação por evento, TTL
- [ ] Registro central de views com o intervalo de refresh de cada uma
- [ ] Convenção de nomes e de índice único (exigido pelo refresh concorrente)
- [ ] Métrica de defasagem exposta na UI

## 4. Alvo 3 — permissão financeira

A dupla dimensão (perfil × acesso financeiro) é fácil de furar.

- [ ] Varrer **todas** as rotas de `/transactions`, `/bank-accounts`, `/financial-categories`, `/cost-centers`
- [ ] Cada uma declara o nível exigido
- [ ] Teste de cobertura de permissão financeira, no mesmo espírito do de 005
- [ ] `financial_access = NONE` não vê valor nem em endpoint de outro módulo (painel do processo, card do CRM)

## 5. Checklist

### Cobertura
- [ ] Toda regra numerada de 051–059 com teste
- [ ] Regra tipo × categoria nos dois sentidos
- [ ] As 4 constraints de `transactions` testadas no banco
- [ ] Estagnação com etapa configurada e não configurada
- [ ] Isolamento entre tenants nas tabelas novas

### SOLID
- [ ] `KanbanBoard` sem nenhum conhecimento de processo
- [ ] Cálculo de saldo em serviço próprio, usado por dashboard, conta e processo
- [ ] `TransactionService` dividido se passou de ~300 linhas
- [ ] Regras de série (057) separadas do CRUD de lançamento

### Duplicação
- [ ] Padrão de agregação extraído (alvo 2)
- [ ] `MoneyField` e formatação de moeda em um só lugar
- [ ] Filtros de período compartilhados entre financeiro, CRM e processos

### Banco
- [ ] `EXPLAIN` no dashboard com 100.000 lançamentos
- [ ] Índices parciais (`ix_tx_open`, `ix_tx_effective`) sendo usados
- [ ] Refresh concorrente sem lock de leitura
- [ ] Histórico de etapa não cresce sem limite (política de retenção)

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] E2E com no máximo 9 jornadas até aqui

## 6. Entregáveis

1. Auditoria numérica documentada em `docs/DECISOES.md`, com a política de arredondamento
2. `MaterializedAggregate` com as views existentes migradas
3. Teste de cobertura de permissão financeira
4. `test-timing.json` atualizado

## 7. Definição de pronto

- [ ] Testes de 051–059 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Zero `float` em caminho de dinheiro
- [ ] Dashboard < 300 ms com 100.000 lançamentos
- [ ] Commit `refactor(060): exatidão numérica e padrão de agregação`
