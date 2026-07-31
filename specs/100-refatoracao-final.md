# 100 — 🔧 REFATORAÇÃO FINAL

**Fase:** 9 · **Tipo:** refatoração · **Orçamento:** o gate final
**Depende de:** 001–099 · **Status:** ⬜ pendente

---

## 1. Objetivo

A última spec. Não entrega feature: entrega a garantia de que as 90 anteriores formam um sistema
coerente, seguro e sustentável — e não 90 pedaços que por acaso compilam juntos.

> Refatoração não muda comportamento. **Todos** os testes anteriores passam sem edição.

## 2. Auditoria de coerência

Onze fases foram construídas em momentos diferentes. Padrões divergem sem ninguém perceber.

- [ ] Todas as listagens usam o mesmo `ListQueryBuilder` e o mesmo contrato de resposta
- [ ] Todos os CRUDs usam o mesmo padrão de 020
- [ ] Todas as agregações usam o `MaterializedAggregate` de 060
- [ ] Todas as sincronizações usam o `SyncJob` de 050
- [ ] Todos os agentes usam o `BaseAgentGraph` de 090
- [ ] Todos os erros seguem RFC 7807, com os mesmos códigos
- [ ] Toda data na API é ISO 8601; toda data na UI é `DD/MM/AAAA`
- [ ] Todo dinheiro é `Decimal` no backend e formatado com vírgula na UI
- [ ] Nomenclatura consistente: inglês no código, português na UI
- [ ] Nenhum componente de domínio duplicado no frontend

## 3. Auditoria de segurança consolidada

Revisar tudo junto, uma vez, com o sistema completo.

- [ ] **Isolamento:** matriz completa — toda tabela com RLS × tenant A não lê, não escreve, não atualiza, não apaga de B
- [ ] **Exceções de RLS:** as três documentadas (parceria em 079, biblioteca pública em 068, catálogos globais) e nenhuma outra
- [ ] **RBAC:** toda rota declara permissão; nenhuma nasceu aberta
- [ ] **Acesso financeiro:** valor não vaza por endpoint de outro módulo
- [ ] **IA:** os 7 vetores de 090 reconferidos com o sistema completo
- [ ] **SSRF:** webhooks (093) e qualquer outro ponto de URL configurável
- [ ] **Upload:** allowlist, path traversal, tamanho — em todos os caminhos
- [ ] **Segredos:** nenhum no código, nos testes, nas fixtures ou no log
- [ ] **PII em log:** redação funcionando em produção
- [ ] **Auditoria:** `ai_audit_log` imutável; ações sensíveis registradas
- [ ] **Dependências:** `pip-audit` e `npm audit` sem vulnerabilidade crítica

## 4. Auditoria de testes

- [ ] Toda regra de negócio numerada nas 90 specs tem ao menos um teste
- [ ] Nenhum teste passa por acidente: mutar a asserção quebra
- [ ] Nenhum teste depende da ordem de execução
- [ ] Nenhum teste faz I/O de rede
- [ ] Nenhum `sleep`
- [ ] Nenhum teste marcado como pulado sem justificativa
- [ ] E2E dentro do teto de 25 jornadas
- [ ] **Wall-clock < 120 s** — o gate original, com o sistema inteiro

## 5. Auditoria de dívida

- [ ] Percorrer `docs/DIVIDA-TECNICA.md` item a item
- [ ] Resolver o que for barato
- [ ] Reclassificar o resto com justificativa e impacto
- [ ] Nenhum `TODO` ou `FIXME` órfão no código — cada um vira issue ou some
- [ ] Nenhum código morto
- [ ] Nenhuma feature flag esquecida ligada

## 6. Documentação final

- [ ] `README.md` atualizado com o estado real
- [ ] `CLAUDE.md` refletindo as convenções que de fato existem
- [ ] `docs/ARQUITETURA.md` — visão geral, com diagrama
- [ ] `docs/DECISOES.md` — todas as decisões e o porquê
- [ ] `docs/SEGURANCA-RLS.md` e `docs/SEGURANCA-IA.md` atualizados
- [ ] `docs/PERFORMANCE.md` com a linha de base final
- [ ] `docs/RUNBOOK.md` verificado passo a passo
- [ ] OpenAPI completo e coerente com o código

## 7. Verificação final do produto

Percorrer o sistema como um escritório faria no primeiro dia:

- [ ] Criar tenant, configurar escritório, convidar usuário
- [ ] Cadastrar cliente, abrir processo, atribuir tarefa
- [ ] Cadastrar termo monitorado e ver a intimação virar tarefa
- [ ] Mover o processo no CRM e aplicar workflow
- [ ] Lançar honorário, dar baixa, conferir no DRE
- [ ] Gerar petição pelo modelo, com variáveis resolvidas
- [ ] Perguntar ao copiloto e receber resposta com dado real
- [ ] Aprovar uma ação de escrita da IA e conferir a auditoria
- [ ] Configurar automação com webhook e ver disparar
- [ ] Abrir as 4 abas de BI e conferir que os números fecham

Cada passo que travar vira correção nesta spec.

## 8. Definição de pronto

- [ ] Todos os testes das 99 specs passam sem edição
- [ ] **Wall-clock de `make test` < 120 s**
- [ ] `make lint` verde: ruff, mypy strict, eslint, tsc
- [ ] Zero `Any`, `as any` ou `# type: ignore` sem justificativa
- [ ] Nenhum item de segurança em aberto
- [ ] Percurso completo do produto funcionando de ponta a ponta
- [ ] `ROADMAP.md` com as 100 specs em ✅
- [ ] Commit `refactor(100): auditoria final e fechamento do roadmap`

---

## O que vem depois

Terminadas as 100, o `ROADMAP.md` deixa de ser fila e vira histórico. Trabalho novo entra como
spec 101 em diante, seguindo o mesmo ciclo — e a cada 10, uma refatoração.

O gate de 120 s continua valendo. Ele é o que impede o projeto de ficar lento sem ninguém notar.
