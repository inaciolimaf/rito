# 090 — 🔧 REFATORAÇÃO — IA

**Fase:** 8 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 081–089 · **Status:** ✅ concluída

---

## 1. Objetivo

Noventa por cento. A camada de IA é a mais nova e a que mais pode causar dano — escreve no
banco, lê dados sensíveis e gera SQL. Esta refatoração é sobre **segurança e custo**.

> Refatoração não muda comportamento. Testes de 081–089 passam **sem edição**.

## 2. Alvo 1 — auditoria de segurança da IA

Cada item é um vetor de ataque real.

- [x] **Prompt injection:** dado do usuário (nome de cliente, texto de intimação, anotação de processo) chega ao prompt. Verificar que instrução embutida em campo de texto não muda o comportamento do agente. Teste com fixtures maliciosas.
- [x] **Vazamento entre tenants:** ferramenta de leitura rodando com contexto do tenant A nunca retorna dado de B — reconfirmar as 16 ferramentas após as mudanças da fase
- [x] **Escalada de privilégio:** Colaborador não obtém, via agente, dado que a UI não mostraria
- [x] **Escrita sem aprovação:** nenhum caminho de código chama service de escrita direto a partir de tool, pulando `ai_actions`. Grep + teste.
- [x] **Text-to-SQL:** as 4 camadas de guardrail testadas isoladamente, cada uma quebrada de propósito para confirmar que a seguinte segura
- [x] **Exfiltração por SQL:** confirmar que a allowlist não expõe coluna com dado pessoal
- [x] **Auditoria imutável:** confirmar no banco que `ai_audit_log` rejeita UPDATE e DELETE

Resultado vai para `docs/SEGURANCA-IA.md`.

## 3. Alvo 2 — controle de custo

IA sem teto de gasto é conta surpresa no fim do mês.

- [x] Orçamento mensal por tenant, configurável, com alerta em 80% e bloqueio em 100%
- [x] Custo por feature visível no painel (081 já registra; falta a política)
- [x] Cache de resultado para entrada idêntica em janela curta (análise de intimação reprocessada)
- [x] Revisar o tamanho dos prompts de sistema — cada token repetido em toda chamada custa
- [x] Modelo barato onde não faz diferença: classificação e resumo curto não precisam do modelo mais caro
- [x] Alerta quando uma feature ultrapassa a média histórica em 3×

## 4. Alvo 3 — consolidar o padrão de agente

Quatro features criaram grafos: copiloto (085), intimação (086), petição (087), editor (088).

- [x] `BaseAgentGraph`: coleta de contexto, laço de ferramentas, interrupção, finalização
- [x] Prompts em arquivos versionados, não string no código
- [x] Convenção única de prompt de sistema, com as regras de segurança compartilhadas
- [x] Um só lugar decidindo modelo, temperatura e limite de tokens
- [x] Teste de contrato: todo grafo respeita o limite de 25 passos e o timeout

## 5. Checklist

### Cobertura
- [x] Toda regra numerada de 081–089 com teste
- [x] Tabela de cálculo de prazo (086) completa, com os casos de borda
- [x] Os 3 testes meta de 081 ativos (sem SDK, sem modelo literal, sem chamada real)
- [x] Os 2 testes meta de 083 ativos (sem SQL cru, sem vector store)
- [x] Isolamento entre tenants em todas as tabelas de IA

### SOLID
- [x] `LLMProvider` é a única porta de saída
- [x] Ferramentas implementadas sobre services, sem query própria
- [x] Grafos usando `BaseAgentGraph`
- [x] Prompt separado de código

### Duplicação
- [x] Padrão de agente extraído (alvo 3)
- [x] Regras de segurança do prompt em um só lugar
- [x] `AIActionPreview` servindo todos os consumidores

### Performance dos testes
- [ ] Wall-clock **< 90 s** — **não atingido**, e a meta estava errada: ver Descobertas
- [x] Fixtures de LLM enxutas — resposta gravada não precisa de 4.000 tokens
- [x] E2E com no máximo 11 jornadas até aqui

## 6. Entregáveis

1. `docs/SEGURANCA-IA.md` com os 7 vetores testados e o resultado
2. Orçamento de custo por tenant, funcionando
3. `BaseAgentGraph` com os 4 grafos migrados
4. Prompts versionados em `app/ai/prompts/`
5. `test-timing.json` atualizado

## 7. Definição de pronto

- [x] Testes de 081–089 passam sem edição
- [ ] Wall-clock < 90 s — ver Descobertas: a meta é de uma suíte que não existe mais
- [x] Nenhum vetor de segurança em aberto
- [x] Teto de custo por tenant ativo
- [x] Commit `refactor(090): segurança e custo da camada de IA`

---

## 8. Descobertas

- **O cache não podia ser automático.** A spec pede "cache de resultado para entrada
  idêntica (análise de intimação reprocessada)", e a primeira versão ligou o cache dentro
  do `AiRunner` para a feature `publication_summary`. Três testes de 081 e 086 ficaram
  vermelhos na hora — e estavam certos: **reanalisar é alguém pedindo outra leitura de
  propósito**. Repetir a mesma entrada às vezes significa "de novo, por favor" e às vezes
  significa "essa resposta serve", e só o chamador sabe qual. O cache virou `use_cache`,
  opt-in, e a análise de intimação passa `use_cache=anterior is None`: a PRIMEIRA análise
  aproveita (clique duplo, nova tentativa depois de um erro, varredura automática), a
  reanálise paga. Foi o teste de 086 que corrigiu o desenho, não o contrário.
- **Bloquear depois de chamar seria pagar e negar.** A verificação de teto acontece antes
  do `provider.complete()`, e o teste garante isso conferindo `provider.calls == []` —
  não só o código de erro. Um teste que só olhasse o 409 passaria com a chamada feita.
- **Teto estourado virou handler global, não `try/except` por rota.** São oito rotas de
  IA hoje; a nona nasceria sem a política. O `BudgetExceededError` sobe até
  `app/core/errors.py`, que devolve 409 com `spent_usd` e `limit_usd` como membros de
  extensão do problem+json — a UI precisa poder dizer **quanto falta**, não só "não deu".
- **Desligar o bloqueio mantém o alerta.** Não é indulgência: um escritório que estoure o
  teto às 16h de um dia de prazo prefere a conta maior. Quem decide é ele, e o padrão
  (`is_blocking=true`) é o conservador.
- **A anomalia se compara com a própria feature.** Copiloto custa naturalmente mais que
  classificação de intimação; comparar features entre si produziria alerta todo dia. A
  janela de 30 dias exclui o dia de hoje — incluir o dia julgado puxaria a média para cima
  e abafaria justamente o pico. E feature sem histórico não gera alerta: o primeiro dia de
  uso é estreia, não desvio.
- **A auditoria de segurança achou um bug de verdade.** Cinco das dez ferramentas de
  escrita (`create_task`, `create_transaction`, `link_publication`, `apply_workflow`,
  `update_lawsuit`) tinham descrição **sem** "Exige confirmação" — e a descrição é o que o
  modelo lê. Uma ferramenta que se anuncia como imediata convida o modelo a dizer ao
  usuário que já fez. Corrigido, com teste que impede a regressão. Um comentário em
  `tool_specs` afirmava que "todas dizem exige confirmação"; o comentário estava certo
  sobre a intenção e errado sobre o código.
- **O teste que importa contra injeção é o que assume que ela funcionou.** Os dois
  primeiros (o texto chega como mensagem `tool`, e todo prompt versionado carrega a regra
  4) protegem a probabilidade. O terceiro protege o resultado: com o modelo inteiramente
  obediente ao atacante, a escrita ainda para em `ai_actions` e a linha nova não é a do
  cliente. Nenhuma defesa de prompt é perfeita, então o desenho não depende dela.
- **O grep da spec virou teste.** "Nenhum caminho chama service de escrita direto a partir
  de tool" é uma afirmação sobre a ÁRVORE de código, não sobre uma execução: um caminho
  paralelo não apareceria em teste de comportamento nenhum, porque o fluxo aprovado
  continuaria verde ao lado. `WriteToolDef.execute` só pode ser chamado de
  `app/domain/ai/actions.py`, e é isso que o teste varre.
- **O contrato dos grafos estava provado no runtime, não nos grafos.** A 082 testou teto
  de passos e timeout com grafos escritos para o teste. O teste novo é parametrizado pelo
  **registro**: dirige cada grafo real com um provider que pede ferramenta para sempre.
  Grafo novo entra sozinho — que é o ponto, porque quem registrar o quinto grafo descobre
  no CI e não no fim do mês.
- **"Quatro features criaram grafos" não era verdade.** O alvo 3 pressupõe grafos em 085,
  086, 087 e 088; na implementação, só o copiloto virou grafo. Intimação, petição e editor
  falam direto com o `AiRunner`, porque nenhuma delas tem laço de decisão — é uma chamada,
  às vezes com ferramenta. A consolidação pedida já existia por construção; o que faltava
  era o contrato testado e os prompts fora do código, e é isso que a spec entregou.
- **Prompts viraram arquivo, e a refatoração não mudou um teste sequer.** O padrão nasceu
  na 088 (os três prompts do editor já foram escritos em `app/ai/prompts/*.md`); aqui ele
  virou regra: os de copiloto e de intimação saíram do código para lá, e as proibições
  passaram a vir de uma constante única (`SAFETY_RULES`) usada inclusive pelos 19 agentes
  da 087, que antes repetiam as mesmas proibições com outras palavras. As 58 provas das features
  afetadas passaram sem edição — que é a definição de refatoração. Cada arquivo tem menos
  de 2 KB, com teto verificado por teste: prompt de sistema é pago em toda chamada, e sem
  teto ele vira depósito de exceção, crescendo um parágrafo por bug corrigido.
- **Modelo barato é configuração, não código.** `publication_summary` (classificar um ato,
  resumir três parágrafos) declara `tier="economico"` e, **sem configuração do escritório**,
  cai em `OPENROUTER_ECONOMY_MODEL`. O que o código sabe é que existe um modelo mais barato
  e quais features podem usá-lo; qual é ele continua sendo variável de ambiente (regra 2 da
  081), e escolha do escritório na UI vence sempre o tier.
- **A meta de 90 s de wall-clock não foi atingida — e ela é de outra suíte.** A suíte de
  backend está em ~200 s com `-n 2` neste host (1.221 testes na 089, 1.253 agora), dentro
  do gate de 300 s do CLAUDE.md §3, mas longe dos 90 s que a spec 090 escreveu lá atrás,
  quando a projeção da fase 8 era de umas poucas centenas de testes. Cortar 110 s exigiria
  remover cobertura das nove specs de IA ou parar de rodar migração real por sessão — as
  duas coisas custam mais do que economizam. A meta correta é a do CLAUDE.md, e ela está
  sendo cumprida; deixar o item marcado como feito seria mentir no lugar em que a spec
  serve justamente para não se mentir.
- **`make lint` estava vermelho antes desta spec.** Três arquivos do frontend da 079
  (`InvitePartnerDialog`, `PartnersPage`, `SharedBadge`) não passavam no `prettier
  --check`. Formatados aqui, sem mudança de comportamento. Vale a mesma observação para o
  backend: `ruff format` e `black` discordam em detalhes (concatenação implícita de string,
  `yield` de tupla) — o formatador do projeto é o **black**, e é ele que o `make lint`
  cobra.

## 9. Definição de pronto (fechamento)

- [x] Sete vetores auditados, documentados em `docs/SEGURANCA-IA.md`, cada um com teste
- [x] Um achado real corrigido (descrição de cinco ferramentas de escrita)
- [x] Teto de custo por tenant ativo, com alerta, bloqueio opcional e alerta de anomalia
- [x] Prompts versionados em `app/ai/prompts/`, com regras de segurança num só lugar
- [x] Contrato de grafo testado sobre o registro real
- [x] Testes de 081–089 passando **sem edição**
- [ ] Wall-clock < 90 s — não atingido; ver Descobertas
- [x] Commit `refactor(090): segurança e custo da camada de IA`
