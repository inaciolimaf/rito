# 090 — 🔧 REFATORAÇÃO — IA

**Fase:** 8 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 081–089 · **Status:** ⬜ pendente

---

## 1. Objetivo

Noventa por cento. A camada de IA é a mais nova e a que mais pode causar dano — escreve no
banco, lê dados sensíveis e gera SQL. Esta refatoração é sobre **segurança e custo**.

> Refatoração não muda comportamento. Testes de 081–089 passam **sem edição**.

## 2. Alvo 1 — auditoria de segurança da IA

Cada item é um vetor de ataque real.

- [ ] **Prompt injection:** dado do usuário (nome de cliente, texto de intimação, anotação de processo) chega ao prompt. Verificar que instrução embutida em campo de texto não muda o comportamento do agente. Teste com fixtures maliciosas.
- [ ] **Vazamento entre tenants:** ferramenta de leitura rodando com contexto do tenant A nunca retorna dado de B — reconfirmar as 16 ferramentas após as mudanças da fase
- [ ] **Escalada de privilégio:** Colaborador não obtém, via agente, dado que a UI não mostraria
- [ ] **Escrita sem aprovação:** nenhum caminho de código chama service de escrita direto a partir de tool, pulando `ai_actions`. Grep + teste.
- [ ] **Text-to-SQL:** as 4 camadas de guardrail testadas isoladamente, cada uma quebrada de propósito para confirmar que a seguinte segura
- [ ] **Exfiltração por SQL:** confirmar que a allowlist não expõe coluna com dado pessoal
- [ ] **Auditoria imutável:** confirmar no banco que `ai_audit_log` rejeita UPDATE e DELETE

Resultado vai para `docs/SEGURANCA-IA.md`.

## 3. Alvo 2 — controle de custo

IA sem teto de gasto é conta surpresa no fim do mês.

- [ ] Orçamento mensal por tenant, configurável, com alerta em 80% e bloqueio em 100%
- [ ] Custo por feature visível no painel (081 já registra; falta a política)
- [ ] Cache de resultado para entrada idêntica em janela curta (análise de intimação reprocessada)
- [ ] Revisar o tamanho dos prompts de sistema — cada token repetido em toda chamada custa
- [ ] Modelo barato onde não faz diferença: classificação e resumo curto não precisam do modelo mais caro
- [ ] Alerta quando uma feature ultrapassa a média histórica em 3×

## 4. Alvo 3 — consolidar o padrão de agente

Quatro features criaram grafos: copiloto (085), intimação (086), petição (087), editor (088).

- [ ] `BaseAgentGraph`: coleta de contexto, laço de ferramentas, interrupção, finalização
- [ ] Prompts em arquivos versionados, não string no código
- [ ] Convenção única de prompt de sistema, com as regras de segurança compartilhadas
- [ ] Um só lugar decidindo modelo, temperatura e limite de tokens
- [ ] Teste de contrato: todo grafo respeita o limite de 25 passos e o timeout

## 5. Checklist

### Cobertura
- [ ] Toda regra numerada de 081–089 com teste
- [ ] Tabela de cálculo de prazo (086) completa, com os casos de borda
- [ ] Os 3 testes meta de 081 ativos (sem SDK, sem modelo literal, sem chamada real)
- [ ] Os 2 testes meta de 083 ativos (sem SQL cru, sem vector store)
- [ ] Isolamento entre tenants em todas as tabelas de IA

### SOLID
- [ ] `LLMProvider` é a única porta de saída
- [ ] Ferramentas implementadas sobre services, sem query própria
- [ ] Grafos usando `BaseAgentGraph`
- [ ] Prompt separado de código

### Duplicação
- [ ] Padrão de agente extraído (alvo 3)
- [ ] Regras de segurança do prompt em um só lugar
- [ ] `AIActionPreview` servindo todos os consumidores

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] Fixtures de LLM enxutas — resposta gravada não precisa de 4.000 tokens
- [ ] E2E com no máximo 11 jornadas até aqui

## 6. Entregáveis

1. `docs/SEGURANCA-IA.md` com os 7 vetores testados e o resultado
2. Orçamento de custo por tenant, funcionando
3. `BaseAgentGraph` com os 4 grafos migrados
4. Prompts versionados em `app/ai/prompts/`
5. `test-timing.json` atualizado

## 7. Definição de pronto

- [ ] Testes de 081–089 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Nenhum vetor de segurança em aberto
- [ ] Teto de custo por tenant ativo
- [ ] Commit `refactor(090): segurança e custo da camada de IA`
