# 080 — 🔧 REFATORAÇÃO — Gestão e BI

**Fase:** 7 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 071–079 · **Status:** ⬜ pendente

---

## 1. Objetivo

Oitenta por cento. Duas prioridades: **auditar o isolamento entre tenants** agora que a spec 079
abriu a primeira exceção legítima à regra, e garantir que o BI não vire o gargalo de performance
do produto.

> Refatoração não muda comportamento. Testes de 071–079 passam **sem edição**.

## 2. Alvo 1 — auditoria completa de isolamento

A spec 079 estendeu a política de RLS de `lawsuits`, `posts` e `lawsuit_parties`. Toda exceção
é uma superfície de vazamento.

- [ ] Revisar **cada** política de RLS do banco, uma por uma, e documentar o porquê de cada exceção
- [ ] Teste matricial: para cada tabela com RLS, verificar que tenant B não lê, não escreve, não atualiza e não apaga dado de A
- [ ] Teste específico de parceria: parceiro vê exatamente o processo compartilhado e nada mais
- [ ] Verificar que a exceção de parceria **não** vazou para `transactions`, `customers`, `templates`, `reports` ou BI
- [ ] Verificar que a exceção de modelo público (068) não colide com a de parceria
- [ ] Confirmar que nenhuma query usa `SET ROLE` ou conexão com `BYPASSRLS`

Esta auditoria é a mais importante do projeto. Reserve tempo.

## 3. Alvo 2 — performance do BI

Sete views materializadas foram criadas. Com volume real, refresh pode travar o banco.

- [ ] Semear 100.000 processos, 500.000 tarefas e 200.000 lançamentos
- [ ] Medir o refresh de cada view e registrar em `docs/DECISOES.md`
- [ ] Nenhum refresh acima de 60 s
- [ ] Confirmar que `CONCURRENTLY` não bloqueia leitura durante o refresh
- [ ] Avaliar refresh incremental onde o completo for caro
- [ ] Confirmar que o refresh sequencial não estoura conexões do pool

## 4. Alvo 3 — consolidar o padrão de relatório

- [ ] 072 fez página genérica dirigida por metadados. As 4 abas de BI seguem o mesmo padrão?
- [ ] `BiTabPanel` reutilizável: indicadores + gráfico + tabela + defasagem
- [ ] Divisão por zero tratada em **um** lugar, não em quatro
- [ ] Formatação de indicador (moeda, percentual, dias) unificada
- [ ] Aviso de amostra pequena com o mesmo componente nas abas 075, 076 e 077

## 5. Checklist

### Cobertura
- [ ] Toda regra numerada de 071–079 com teste
- [ ] Os 5 testes de vazamento de 079 passando
- [ ] Divisão por zero em todos os indicadores
- [ ] Nulo distinguido de zero nos ciclos (076)
- [ ] Toda view materializada no registry (078)

### SOLID
- [ ] Cálculo de BI em services, nunca no router
- [ ] Uma query de agregação por indicador, não uma por card
- [ ] `MaterializedAggregate` de 060 usado por todas as sete views

### Duplicação
- [ ] Padrão de aba de BI extraído (alvo 3)
- [ ] Cálculo de ciclo em um só lugar (076 e 077 usam os mesmos)
- [ ] Definição de "custo fixo" (grupos 2, 3, 5, 7) como constante única

### Banco
- [ ] Refresh de todas as views medido com volume (alvo 2)
- [ ] Índices das views sendo usados
- [ ] Política de retenção de `access_logs` e `aggregate_refresh_log` ativa

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] E2E com no máximo 10 jornadas até aqui
- [ ] Fixture de volume só nos testes de performance, marcada como lenta

## 6. Entregáveis

1. `docs/SEGURANCA-RLS.md` — cada política, cada exceção, com justificativa e o teste que a cobre
2. Medição de refresh com volume real em `docs/DECISOES.md`
3. `BiTabPanel` com as 4 abas migradas
4. `test-timing.json` atualizado

## 7. Definição de pronto

- [ ] Testes de 071–079 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Matriz de isolamento completa e verde
- [ ] Nenhum refresh acima de 60 s com 100.000 processos
- [ ] Commit `refactor(080): auditoria de isolamento e performance do BI`
