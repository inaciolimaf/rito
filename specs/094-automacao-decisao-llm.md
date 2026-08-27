# 094 — Automação com decisão por LLM

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 093, 082 · **Status:** ✅ concluída

---

## 1. Objetivo

Nó de decisão inteligente dentro da automação: em vez de condição fixa em campo, o LLM analisa
o contexto e escolhe o ramo. Une o motor de 092 com o runtime de 082.

## 2. Escopo

- Ação `llm_decision` com ramos nomeados
- Contexto coletado por tool calling
- Ramificação condicional
- Registro do raciocínio
- Limite de custo por automação
- Fallback quando o LLM falha

## 3. Fora de escopo

- Escrita autônoma sem aprovação — a regra de 084 continua valendo

## 4. Modelo de dados

```sql
ALTER TABLE automation_actions
  ADD COLUMN branches JSONB;          -- {"nome_do_ramo": [action_ids]}

CREATE TABLE automation_decisions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  run_id UUID NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
  action_id UUID NOT NULL REFERENCES automation_actions(id),
  question TEXT NOT NULL,
  context_summary TEXT,
  chosen_branch TEXT,
  confidence NUMERIC(3,2),
  reasoning TEXT NOT NULL,
  model TEXT NOT NULL,
  tokens_used INTEGER,
  fell_back BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_decisions_run ON automation_decisions (run_id, created_at);

ALTER TABLE automations
  ADD COLUMN monthly_ai_budget_usd NUMERIC(10,2),
  ADD COLUMN current_month_spend_usd NUMERIC(10,2) NOT NULL DEFAULT 0;
```
RLS ligado. Migration `094_llm_decisions.py`.

## 5. Configuração da ação

```json
{ "action_kind": "llm_decision",
  "action_config": {
    "question": "Esta intimação exige resposta em até 5 dias?",
    "context_tools": ["get_lawsuit", "get_publication"],
    "branches": ["urgente", "normal", "sem_acao"],
    "default_branch": "normal",
    "min_confidence": 0.7 } }
```

## 6. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/automations/{id}/decisions?run_id=` |
| POST | `/api/v1/automations/{id}/decisions/simulate` → `{subject_id}` |
| PUT | `/api/v1/automations/{id}/ai-budget` → `{monthly_ai_budget_usd}` |

## 7. Front-end

**Reutiliza:** `AutomationBuilder`, `ActionRow`, `AgentStepsTimeline`
**Cria:** `LlmDecisionAction` (pergunta, ferramentas, ramos, confiança mínima),
`BranchEditor` (ações por ramo), `DecisionLogCard` (mostra o raciocínio),
`AiBudgetField`
**Rota:** dentro de `/settings/automations`

## 8. Regras de negócio

1. O nó de decisão escolhe **exatamente um** ramo entre os declarados. Resposta fora da lista aciona o `default_branch` e é registrada como anomalia.
2. Confiança abaixo de `min_confidence` também vai para o `default_branch`, registrando o motivo.
3. Contexto é coletado pelas ferramentas de **leitura** de 083. O nó de decisão **nunca** escreve.
4. `reasoning` é obrigatório na resposta do LLM e é sempre gravado — automação que decide sem explicar não é auditável.
5. Falha do LLM (timeout, erro, sem chave) → `default_branch`, `fell_back = true`, e a automação **continua**. Automação não pode parar por indisponibilidade de IA.
6. Orçamento mensal por automação: atingido, as execuções seguintes usam o `default_branch` sem chamar o LLM, com alerta ao GESTOR.
7. Máximo de **3 nós de decisão** por automação — mais que isso é regra de negócio disfarçada de IA.
8. Ramo pode conter as mesmas ações de 092, inclusive webhook.
9. Ramos aninhados não são permitidos: decisão dentro de ramo de decisão → 422.
10. Simulação roda a decisão sem executar as ações, mostrando o ramo escolhido e o raciocínio.
11. Ação de escrita dentro de um ramo segue as regras de 092 (permissão do criador), **não** cria `ai_action` — é automação configurada por humano, não proposta de agente. Isso é uma distinção deliberada e está documentada.
12. Toda decisão registra tokens e custo.

## 9. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | decisão escolhe o ramo e executa as ações dele | ~0,5 s |
| integração | resposta fora da lista → default, com anomalia | ~0,4 s |
| integração | confiança baixa → default com motivo | ~0,3 s |
| integração | **contexto usa só ferramentas de leitura** | ~0,4 s |
| integração | `reasoning` sempre gravado | ~0,2 s |
| integração | **falha do LLM cai no default e continua** | ~0,5 s |
| integração | sem chave de IA a automação continua funcionando | ~0,4 s |
| integração | orçamento estourado usa default sem chamar LLM | ~0,4 s |
| integração | 4º nó de decisão → 422 | ~0,2 s |
| integração | ramo aninhado → 422 | ~0,2 s |
| integração | simulação não executa ações | ~0,3 s |
| frontend | editor de ramos | ~0,4 s |

**Total:** ~4,2 s

## 10. Descobertas

- **O `AiRunner` comitava no meio da transação de quem chama.** A regra 6 da 081 manda
  gravar o uso mesmo quando a chamada falha, e o jeito de sobreviver ao rollback da
  sessão-por-request era um `commit()` de emergência. Dentro da automação isso encerrava
  o `session.begin()` do chamador no meio da execução — o erro que apareceu foi
  `Can't operate on closed transaction`. O runner ganhou `commit_usage`, e quem é dono da
  transação desliga: o registro do uso passa a viajar na transação de quem chama, que ou
  termina (e grava) ou volta atrás inteira (e aí a chamada também não aconteceu).
- **`NUMERIC(10,2)` zerava o contador de gasto.** Uma decisão custa centésimos de centavo;
  com duas casas decimais, toda chamada arredondava para `0.00` e o teto da regra 6 nunca
  seria atingido. A coluna virou `NUMERIC(12,6)` — o teto continua em duas casas, porque
  o teto é uma decisão humana em reais, mas o contador precisa somar o que de fato foi
  gasto.
- **Ramificar não exigiu tabela nova.** `branches` mora na própria ação de decisão
  (`{"ramo": [posições]}`), e a sequência continua linear: o motor pula o que pertence a
  um ramo não escolhido. Uma tabela de "nó de fluxo" custaria dois JOINs em toda leitura
  do editor para representar FORMA, não fatos da vida do escritório.
- **A execução precisa lembrar o ramo escolhido.** `automation_runs.scratch` entrou junto:
  uma execução que espera três dias no meio de um ramo volta sem contexto nenhum, e
  recalcular a decisão na retomada significaria pagar duas vezes por uma escolha já
  tomada — e possivelmente escolher diferente.
- **O nó de decisão roda FORA do `try/except` das outras ações.** Não há falha de decisão
  para tratar: pior caso, ela cai no ramo padrão e registra o motivo. Deixá-la no mesmo
  bloco faria uma exceção interna virar "automação falhou", que é exatamente o que a
  regra 5 proíbe.
- **`fell_back` sem `fallback_reason` esconderia o que importa.** Saber que a IA não
  decidiu é metade da informação; a outra metade — inventou um ramo, ficou abaixo da
  confiança, não respondeu, ou o orçamento acabou — é a que diz se o problema é a
  pergunta, o modelo ou a conta. A coluna extra não estava no §4 e entrou.
- **Decisão sem raciocínio não vale mais que o padrão.** A regra 4 diz que `reasoning` é
  obrigatório; a consequência prática só apareceu ao escrever o teste: se o modelo escolhe
  um ramo válido e não explica, aceitar a escolha seria aceitar uma decisão não auditável.
  Ela cai no padrão, com o motivo registrado.
- **O runner de IA é montado sob demanda dentro do motor.** Os gatilhos nascem em
  `complete()`, `create()` e `change_stage()` — use cases do domínio, que não conhecem (e
  não devem conhecer) o `app.state`. Sem isso, a decisão por IA só funcionaria pela rota
  de simulação, e a feature inteira seria uma demonstração.
- **A simulação decide de verdade.** É o ponto: quem está escrevendo a automação precisa
  ver o modelo escolher com o contexto real antes de deixar a regra no ar. O que ela não
  faz é executar as ações do ramo — e a execução de apoio que carrega o payload é apagada
  no fim, para não sujar o histórico com corridas que ninguém pediu.
- **O limite de três decisões é sobre custo, não sobre capacidade.** Cada nó é uma chamada
  paga em TODA execução da automação; a quarta decisão quase sempre é uma condição de
  campo mal disfarçada — e essas são grátis desde a 092.

## 11. Definição de pronto

- [x] Checklist padrão
- [x] IA indisponível nunca trava automação — provado por três caminhos (erro, sem chave,
      orçamento estourado)
- [x] Raciocínio sempre auditável — inclusive o do fallback
- [x] Commit `feat(094): automação com decisão por LLM`
