# 133 — A fronteira do text-to-SQL e as ações de IA

**Fase:** 13 · **Tipo:** correção · **Orçamento:** +6 s
**Depende de:** 083, 084, 086, 089, 094, 126 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar sete defeitos da camada de IA, sendo um deles a única quebra de isolamento entre
escritórios que o projeto já teve: uma consulta do text-to-SQL conseguia trocar o
`app.tenant_id` da própria sessão no meio da execução e ler os indicadores do escritório
vizinho. Os outros seis são da mesma família das dívidas 36, 43 e 44 — **código que decide
errado e não avisa ninguém**: um teto de linhas que não valia para `LIMIT 0+5000000`, uma
confiança mínima que não valia quando o modelo não devolvia número, uma confirmação humana
que virava duas escritas, um desfazer que não entrava no log de auditoria, um prazo em dias
corridos contado como úteis e um catálogo de ferramentas que oferecia ao modelo o que ele
não podia usar.

## 2. O achado crítico, e por que ele existia

`POST /api/v1/ai/analytics/ask` recebe `confirm_sql` do cliente. O comentário da própria
rota diz por quê: «o cliente pode ter mexido no texto entre uma chamada e outra». Logo, o
`sql_guard` é a **única** defesa de texto, e a quarta camada do §5 da 089 (a transação
somente-leitura) é a única defesa de execução.

O guarda filtrava por **tipo de nó** (`Insert`, `Update`, `Drop`, …) e por **allowlist de
relações**. Não olhava chamada de função nenhuma. E `set_config` é uma função comum:

```sql
SELECT * FROM ai_allowed_metrics LIMIT 1000 OFFSET
  (SELECT 0 FROM (SELECT set_config('app.tenant_id', '<tenant B>', true)) AS z)
```

A subconsulta em `OFFSET` é não-correlacionada, então o Postgres a resolve como **InitPlan**
— avaliada UMA vez, **antes** de varrer a relação. As nove relações da allowlist filtram por
`current_setting('app.tenant_id')`, avaliado **depois**. O `transaction_read_only = on` não
via nada de errado, porque trocar um GUC não é escrita.

Medido no HEAD, ponta a ponta, dentro do mesmo savepoint que a aplicação usa:

```
sessão do tenant A vê:    ['SEGREDO-DO-A']
consulta da IA devolveu:  ['SEGREDO-DO-B']   ← dado do outro escritório
após o ROLLBACK TO:       ['SEGREDO-DO-A']   ← e sem deixar rastro na sessão
```

Alcançável por ADMINISTRADOR de qualquer escritório com a feature ligada. O alcance era o
catálogo agregado inteiro do vizinho: pipeline, vintage, ciclos, custo, produtividade,
saldos, agilidade e ponto.

**A lição estrutural** é que a 089 escreveu quatro camadas e três delas eram a mesma
pergunta feita ao mesmo parser. Uma camada que só sabe ler texto não fecha uma classe que
depende da ORDEM DE AVALIAÇÃO do banco. Por isso esta spec entrega duas defesas de
naturezas diferentes, e não uma melhor.

## 3. Escopo

- **Camada de texto:** allowlist de funções puras no `sql_guard`, varrendo a árvore inteira
  (`LIMIT`, `OFFSET`, `HAVING`, `ORDER BY`, CTE, subconsulta); `LIMIT` e `OFFSET` só como
  literal inteiro.
- **Camada de banco:** papel `rito_ai` e `REVOKE EXECUTE ON set_config FROM PUBLIC`
  (migration 133); a consulta do modelo roda sob `SET LOCAL ROLE` dentro do savepoint.
- **Dívida 43:** teto de linhas contra `LIMIT` com aritmética.
- **`AiActionService`:** `SELECT … FOR UPDATE` em `approve`/`reject`/`undo`; reconferência de
  permissão em `approve` e `undo`; `ai_audit_log` no desfazer; `undo` idempotente.
- **`tool_specs`:** as ferramentas de escrita passam pelo mesmo filtro de RBAC das de leitura.
- **`decision.py`:** confiança ausente cai no ramo padrão quando há mínimo configurado.
- **`publications/analysis.py`:** espécie de prazo normalizada, dias lidos como número, e
  espécie desconhecida não vira data.

## 4. Fora de escopo

- Os outros achados da auditoria de segurança: API pública fora do eixo `financial_access`,
  `PUT` públicos sem service, token que sobrevive à desativação do usuário, valores
  financeiros nas bordas não-financeiras, autorização de anexos, URL pré-assinada de 7 dias,
  `nivelSigilo` ilegível lido como público. São de outras specs (134, 135, …) e de outros
  módulos — `app/public/`, `app/domain/users/`, `app/domain/financial/`.
- Trocar `ai_allowed_metrics` de view viva (`security_invoker=true`) para view barreira.
  Investigado e recusado — ver §9.
- Refatorar `_ROLE_ORDER`/`_FINANCIAL_ORDER` para uma única definição em
  `app/core/permissions.py`. Esta spec fundiu duas das três cópias; a terceira é a do core,
  que é a fonte, e mexer nela é escopo de refatoração.

## 5. Modelo de dados

Nenhuma tabela, nenhuma coluna. A migration é só de **privilégio**:

```sql
CREATE ROLE rito_ai NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT rito_ai TO rito_app;
GRANT USAGE ON SCHEMA public TO rito_ai;
GRANT SELECT ON <as 9 relações do catálogo> TO rito_ai;
GRANT SELECT ON lawsuits, lawsuit_types, action_groups, stages, steps TO rito_ai;
REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) TO rito_app;
```

Migration: `alembic/versions/133_papel_de_leitura_da_ia.py`

As cinco tabelas de apoio existem porque `ai_allowed_metrics` é a única das nove que **não**
é view barreira sobre matview: é uma view viva sobre `lawsuits`, criada com
`security_invoker=true` na 089 justamente para que quem isole seja o RLS de quem consulta
(§4 do `CLAUDE.md`). Com `security_invoker`, o privilégio conferido é o do papel corrente.
Isso não afrouxa nada — `rito_ai` é `NOBYPASSRLS` e as políticas valem para ele exatamente
como valem para `rito_app`, o que o teste
`test_o_escritorio_a_nao_soma_o_processo_do_escritorio_b` mede.

`rito_ai` é compartilhado pelo cluster, como `rito_app` desde a 003, e por isso o
`downgrade` desfaz os `GRANT`s do banco e não derruba o papel.

## 6. Contratos de API

Inalterados em forma. Mudam três **respostas**, e as três são recusas novas:

| Situação | Antes | Depois |
|---|---|---|
| `confirm_sql` chamando função fora da allowlist | 200 com o resultado | 422, "A consulta chama funções que não são permitidas aqui: …" |
| `confirm_sql` com `OFFSET` calculado | 200 | 422, "O deslocamento de linhas (`offset`) precisa ser um número escrito" |
| `POST /ai/actions/{id}/approve` de quem perdeu a permissão | 200, executado | 200, `status: "failed"` com o motivo em `error` |
| `POST /ai/actions/{id}/approve` simultâneo | 200 nos dois | 200 num, **409** no outro |

## 7. Regras

1. **Nenhuma chamada de função fora de `ALLOWED_FUNCTIONS`**, em profundidade nenhuma da
   árvore. Allowlist, nunca denylist: `set_config` foi a que alguém achou primeiro, e
   `pg_sleep`, `dblink` e `pg_read_file` mostram que a lista do proibido nunca fecha.
2. **`LIMIT` só como literal inteiro.** Qualquer outra forma (`Add`, `Neg`, `Mul`,
   subconsulta, parâmetro, `ALL`) cai no ramo que injeta `MAX_ROWS`. Fecha a **dívida 43**.
3. **`OFFSET` só como literal inteiro.** Esta feature responde uma pergunta; ela não pagina.
4. **O `app.tenant_id` é imutável enquanto a consulta do modelo roda** — por privilégio, não
   por convenção. O papel corrente durante a execução não tem `EXECUTE` em `set_config`.
5. **Uma confirmação humana, uma execução, um registro.** A transição pending→approved é
   atômica, sob `SELECT … FOR UPDATE`.
6. **A permissão vale no momento do ATO.** `approve` e `undo` reconferem perfil e acesso
   financeiro; `approve` sem permissão fecha como `failed`, sem linha de auditoria (nada foi
   executado).
7. **Desfazer é escrita, e escrita da IA vai para o `ai_audit_log`** — com o par antes/depois
   invertido e `tool_name` sufixado com `:undo`. Desfazer duas vezes é recusado.
8. **O catálogo oferecido ao modelo é o recorte de permissão da pessoa**, para leitura *e*
   escrita.
9. **Confiança ausente não é confiança suficiente.** Com `min_confidence > 0`, decisão sem
   número declarado cai no ramo padrão, com o motivo gravado. Com o mínimo em zero, o
   escritório declarou que não exige — e o `None` passa.
10. **Espécie de prazo desconhecida não vira data.** O número de dias continua na tela; a
    data, não. `"úteis"`, `"dias corridos"` e `"CORRIDOS"` são reconhecidos pelo radical.
11. **`deadline_days` é lido como número**, aceitando `15`, `15.0` e `"15"`, dentro da faixa
    de 1 a 365.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | 9 formas de função proibida (OFFSET/HAVING/ORDER BY/subquery/IN/CASE, `pg_sleep`, `dblink`, `pg_read_file`) | `tests/unit/test_sql_guard.py` | ~0,1 s |
| unit | 10 formas do vocabulário analítico legítimo continuam passando | `tests/unit/test_sql_guard.py` | ~0,1 s |
| unit | a recusa nomeia as funções barradas, em português | `tests/unit/test_sql_guard.py` | ~0,1 s |
| unit | a allowlist de funções escrita duas vezes (spec 132) | `tests/unit/test_sql_guard.py` | ~0,1 s |
| unit | dívida 43: `LIMIT 0+5000000`, `5000000-1`, `1000*1000`, `-1` caem no teto | `tests/unit/test_sql_guard.py` | ~0,1 s |
| unit | `OFFSET` calculado recusado; literal passa | `tests/unit/test_sql_guard.py` | ~0,1 s |
| integração | **o payload do achado crítico morre por falta de privilégio** | `tests/integration/test_ai_sql_role.py` | ~0,3 s |
| integração | a mesma troca em `WHERE`/`HAVING`/`ORDER BY`/subconsulta escalar | `tests/integration/test_ai_sql_role.py` | ~0,4 s |
| integração | a tentativa falha e a sessão volta inteira (papel e tenant) | `tests/integration/test_ai_sql_role.py` | ~0,2 s |
| integração | a consulta legítima continua rodando no papel restrito | `tests/integration/test_ai_sql_role.py` | ~0,2 s |
| integração | tabela crua é `permission denied` para `rito_ai` | `tests/integration/test_ai_sql_role.py` | ~0,2 s |
| integração | os `GRANT`s e a `ALLOWED_RELATIONS` dizem a mesma coisa | `tests/integration/test_ai_sql_role.py` | ~0,2 s |
| RLS | **A não soma o processo de B** pela view viva do catálogo | `tests/integration/test_ai_sql_role.py` | ~1,0 s |
| integração | duas aprovações simultâneas: uma executa, a outra leva 409 | `tests/integration/test_ai_actions.py` | ~1,5 s |
| integração | aprovar reconfere a permissão perdida depois de propor | `tests/integration/test_ai_actions.py` | ~0,5 s |
| integração | desfazer grava no `ai_audit_log`, com o par invertido | `tests/integration/test_ai_actions.py` | ~0,5 s |
| integração | desfazer duas vezes é recusado | `tests/integration/test_ai_actions.py` | ~0,5 s |
| integração | o catálogo de escrita é recortado por RBAC | `tests/integration/test_ai_tools.py` | ~0,4 s |
| integração | 4 formas de confiança não numérica caem no padrão | `tests/integration/test_automation_decisions.py` | ~1,2 s |
| integração | mínimo zerado continua aceitando decisão sem número | `tests/integration/test_automation_decisions.py` | ~0,3 s |
| unit | espécie por radical, dias por número, faixa, e os 6 dias de diferença | `tests/unit/test_ai_analysis_parser.py` | ~0,2 s |
| integração | `"dias corridos"` conta corridos; espécie desconhecida não vira data | `tests/integration/test_publication_analysis.py` | ~0,6 s |

**Total estimado:** +6 s (medido: 9,8 s para os quatro arquivos novos/alterados sozinhos,
56,6 s para o conjunto de 486 testes que esta spec exercitou)
**Fixtures externas:** nenhuma. O LLM é sempre `ScriptedProvider`.

## 9. Descobertas

- **As três opções de imutabilidade foram medidas, e só uma funciona sozinha.** O enunciado
  oferecia três: papel sem permissão no GUC, `SET LOCAL` numa conexão separada, e revogar
  `EXECUTE` de `set_config` do `rito_app`. Medidas:
  - *Revogar de `rito_app`* quebra a aplicação inteira: `app/core/rls.py::set_tenant_context`
    **é** um `set_config`, e é a consulta mais executada do sistema. Sozinha, não serve.
  - *Conexão separada* não dá imutabilidade nenhuma se a conexão é do mesmo papel — ela
    continua podendo trocar o GUC. Daria, com um papel de LOGIN próprio, ao custo de um DSN
    novo em `app/core/config.py`, senha em `docker-compose` e no deploy da 099.
  - *Papel restrito*, que é a que ficou, **precisa** da revogação para existir: sem
    `REVOKE … FROM PUBLIC`, um papel recém-criado herda `EXECUTE` em `set_config` por
    `PUBLIC` e a defesa não vale nada. As duas viraram uma só. E `SET LOCAL ROLE` dentro do
    savepoint dispensa a conexão nova, porque o `ROLLBACK TO SAVEPOINT` desfaz o papel junto
    com o resto.

  Medido no banco: `permission denied for function set_config` em todas as cláusulas, e o
  mesmo erro para `set_config('role', 'rito_app', true)` — o caminho de volta.

- **O papel restrito trouxe um segundo guardrail de graça.** A allowlist de relações deixou
  de ser só análise estática: `SELECT name FROM customers` agora morre em
  `permission denied for table customers` mesmo com o parser desligado. É a primeira vez que
  as duas camadas do §5 da 089 falam a mesma língua por meios diferentes.

- **`ai_allowed_metrics` não virou view barreira, e isso foi decisão.** Seria mais simples
  dar a `rito_ai` só as 9 views: bastava trocar `security_invoker=true` por um `WHERE
  tenant_id = current_setting(...)` embutido. Recusado porque inverteria o §4 do `CLAUDE.md`
  para essa relação: hoje quem isola é o RLS de `lawsuits`, e a view barreira trocaria isso
  por um `WHERE` que, no dia em que alguém o apagasse, não seria pego por nenhuma política.
  O preço é o `GRANT SELECT` nas 5 tabelas de apoio, com RLS intacto — e um teste que mede
  exatamente isso.

- **O gate de `SET ROLE` foi ampliado, e é a mudança de teste que esta spec assume.**
  `test_isolation_matrix.py::test_nenhum_modulo_da_app_troca_de_role_ou_usa_conexao_de_migration`
  procurava `\bSET\s+ROLE\b`. `SET LOCAL ROLE` passaria por baixo dele sem ninguém ver — e
  aproveitar isso seria exatamente o "gate que não morde" que a auditoria critica. O regex
  passou a `\bSET\s+(?:LOCAL\s+)?ROLE\b` e ganhou **uma** exceção nomeada, com a razão
  escrita na docstring: o papel assumido pode estritamente MENOS que `rito_app` e vive
  dentro de um savepoint. Trocar de papel para baixo é o contrário de desligar o RLS por
  dentro. É a única edição de teste existente desta spec, e ela deixa o gate mais estrito do
  que estava.

- **O teto de `@pytest.mark.commits` subiu de 70 para 71**, com a justificativa que o próprio
  gate pede. O teste de concorrência precisa de duas conexões de verdade: dentro da transação
  de teste da 105 as duas "requisições" seriam a MESMA conexão, e o `FOR UPDATE` não teria
  contra quem competir.

- **O teste de concorrência não mordia sem uma barreira.** Escrito com `asyncio.gather`
  ingênuo, ele passava verde com a trava REMOVIDA em três execuções seguidas: o `gather`
  deixa a primeira corrotina correr até o commit antes de a segunda tocar no banco. Com um
  `asyncio.Barrier(2)` posicionado depois da leitura e antes do `approve`, ele reprova o
  mutante e passa com a correção. Foi o único teste desta spec que precisou ser provado
  mordendo — e teria entrado inútil sem essa conferência.

- **Duas surpresas dos gates, ambas com a mesma forma.** O gate de OFFSET
  (`test_performance_invariants`) varre **constantes de string** do código, então a frase de
  recusa em português que continha a palavra `OFFSET` virou "listagem com OFFSET". O gate de
  `SET ROLE` varre o **texto do arquivo**, então a docstring que EXPLICAVA por que o `SET
  LOCAL ROLE` é seguro contava como violação. Os dois têm a mesma causa: um gate textual não
  distingue o uso da menção. O primeiro se resolveu reescrevendo a mensagem sem o termo; o
  segundo, com a exceção nomeada acima.

- **CTE está de fato proibida no text-to-SQL, e ninguém tinha escrito isso.** `_relations`
  trata o nome da CTE como relação, então `WITH c AS (…) SELECT * FROM c` é recusado com "usa
  dados fora do catálogo: c". Não é defeito — é o comportamento desde a 089 —, mas a mensagem
  aponta para o lugar errado e nenhuma spec dizia. Fica registrado; corrigir a mensagem é
  trabalho de outra.

- **Dois vermelhos de herança, medidos e alheios a esta spec.** `test_tamanho_de_funcao`
  acusa `lawsuits/listing.py::crm_stats` (32 linhas) e `schedule/router.py::ical_feed` (37) —
  nenhum dos dois arquivos foi tocado aqui; as duas funções desta spec (`approve` e `undo`)
  passaram de 31 e 34 para dentro do teto por extração. `test_registro_de_gates` acusa duas
  regras de ESLint sem linha em `docs/GATES.md`, que é front-end. Os dois vêm de trabalho
  paralelo.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as 11 regras com teste
- [x] Nenhuma tabela nova; o teste de isolamento entre tenants existe assim mesmo, porque a
      spec mexe em quem lê o quê
- [x] Testes dos módulos afetados verdes: 486 testes, 56,6 s
- [x] `ruff` + `black` + `mypy` verdes nos 16 arquivos tocados
- [x] Sem `Any` novo, sem `# type: ignore` novo (um foi apagado, em `_deadline_for`)
- [x] Duplicação da tabela de ordem de perfil reduzida de três cópias para duas
- [ ] `ROADMAP.md` atualizado para ✅ — texto entregue no relatório; o arquivo é de outro dono
- [ ] `docs/DIVIDA-TECNICA.md` fechando a dívida 43 — idem
- [x] Commit `fix(133): a fronteira do text-to-SQL e as ações de IA`
