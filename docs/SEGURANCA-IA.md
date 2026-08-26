# Segurança da camada de IA — os sete vetores

> Entregável da spec 090 (refatoração da fase 8). A camada de IA é a mais nova do
> produto e a que mais pode causar dano: ela **escreve no banco**, **lê dado sensível**
> e **gera SQL**. Este documento lista os sete vetores de ataque que a spec exige
> auditar, o que o produto faz contra cada um e **onde está o teste**. Como o inventário
> de RLS (`SEGURANCA-RLS.md`), ele é executável: nenhum vetor aqui é afirmação sem
> arquivo de teste ao lado.

## 0. O princípio

Duas frases explicam quase todas as decisões abaixo.

**O agente é o usuário mais persistente que o sistema já teve.** Ele não tem privilégio
próprio: roda com a sessão do usuário logado, sob o mesmo RLS e o mesmo RBAC. Se uma
ferramenta enxerga mais que a tela, isso é vazamento com cara de feature.

**Nenhuma defesa de prompt é perfeita, então o desenho não depende dela.** As regras de
segurança do prompt (`app/ai/prompts/__init__.py::SAFETY_RULES`) reduzem a chance de o
modelo fazer besteira; o que *impede* a besteira de virar dano é estrutural — confirmação
humana antes de escrever, allowlist antes de consultar, transação somente-leitura,
auditoria que não aceita UPDATE.

---

## 1. Prompt injection

**O ataque.** Dado escrito por terceiros chega ao prompt: nome de cliente, texto de
intimação vinda do DJEN, anotação de processo. Basta cadastrar um cliente chamado
"IGNORE AS INSTRUÇÕES ANTERIORES…" para que a frase entre na conversa do copiloto.

**A defesa.** Não é filtro de string — filtro perde para a primeira variação da frase.
É o **lugar** onde o texto entra:

| Origem | Papel da mensagem |
|---|---|
| Instrução do produto | `system` (primeira mensagem, sempre) |
| Pergunta da pessoa | `user` |
| Dado vindo do banco | `tool` (resultado de ferramenta) |

E a regra 4 de `SAFETY_RULES`, presente em **todo** prompt versionado, diz ao modelo que
resultado de ferramenta é conteúdo, nunca instrução.

**Testes.** `tests/integration/test_ai_security.py`:
`test_injecao_em_campo_de_texto_chega_como_dado_e_nao_como_instrucao` (o texto injetado
chega ao modelo, e só em mensagens `tool`),
`test_todo_prompt_versionado_declara_que_dado_nao_e_instrucao`,
`test_injecao_obedecida_pelo_modelo_ainda_para_na_confirmacao_humana` — este último é o
que importa: ele **assume que a injeção funcionou** e mostra que a escrita ainda assim
para na aprovação humana.

**Resultado:** protegido, sem depender do modelo obedecer.

---

## 2. Vazamento entre tenants

**O ataque.** Uma ferramenta de leitura executada no contexto do escritório A devolvendo
dado do escritório B — por id direto, por busca pelo nome exato, por join esquecido.

**A defesa.** As 16 ferramentas de leitura consultam pelos services do domínio, com a
sessão do usuário e `app.tenant_id` setado. Nenhuma tem SQL próprio (teste meta da 083).
Quem isola é o RLS, não um `WHERE` na ferramenta.

**Testes.** `tests/integration/test_ai_tools.py::test_as_dezesseis_ferramentas_respeitam_o_tenant`
— parametrizado sobre o registro inteiro, com o intruso sendo GESTOR com acesso
financeiro FULL **no próprio escritório**: o que o barra é o RLS, não o RBAC. Reconfirmado
após as specs 085–089 (o teste roda a cada suíte e cobre ferramenta nova automaticamente).
As tabelas novas da fase (`editor_ai_actions`, `ai_sql_queries`, `ai_insights`,
`ai_budgets`, `ai_cache`) entram na auditoria de políticas da 080
(`test_isolation_matrix.py`), que lê o catálogo do Postgres. O cache tem teste próprio:
`test_ai_budget.py::test_cache_e_por_escritorio`.

**Resultado:** protegido, com cobertura que cresce sozinha.

---

## 3. Escalada de privilégio

**O ataque.** Um Colaborador pedir ao agente aquilo que a interface não lhe mostraria —
o faturamento do escritório, a tarefa privada de um colega, o painel financeiro.

**A defesa.** Dois níveis. O catálogo oferecido ao modelo já vem recortado pelo RBAC do
usuário (`tool_specs(user)`), porque oferecer ferramenta proibida só gera tentativa
frustrada e token gasto. E a execução revalida: chamada direta a uma ferramenta fora do
recorte devolve erro tipado, não exceção.

**Testes.** `test_ai_security.py::test_colaborador_nao_obtem_pelo_agente_o_que_a_tela_nao_mostraria`
(o catálogo do Colaborador é subconjunto próprio do de Administrador),
`test_analitica_e_de_administrador_para_cima`,
`test_ai_tools.py::test_ferramenta_financeira_com_acesso_none_devolve_erro_tipado` e
`test_tarefa_privada_de_terceiro_nao_aparece`.

**Resultado:** protegido nos dois níveis.

---

## 4. Escrita sem aprovação

**O ataque.** Um caminho de código que chame o service de escrita direto a partir de uma
ferramenta, pulando `ai_actions`. Não apareceria em teste de comportamento nenhum — o
fluxo aprovado continuaria funcionando ao lado.

**A defesa.** `WriteToolDef.execute` é a única porta da escrita, e o único módulo que a
chama é `app/domain/ai/actions.py`, depois de um humano aprovar. A ferramenta chamada
pelo modelo produz **proposta**, nunca gravação.

**Testes.** `test_ai_security.py::test_nenhum_caminho_de_codigo_executa_ferramenta_de_escrita_fora_de_ai_actions`
(o grep que a spec pede, virado teste sobre a árvore de `app/`),
`test_o_registro_de_ferramentas_de_escrita_sempre_avisa_que_exige_confirmacao`, e a
bateria da 084 (`test_ai_actions.py`): proposta não grava, aprovação executa e audita,
recusa não deixa rastro, ação expira em uma hora.

**Achado corrigido nesta auditoria.** Cinco das dez ferramentas de escrita
(`create_task`, `create_transaction`, `link_publication`, `apply_workflow`,
`update_lawsuit`) tinham descrição **sem** o aviso "Exige confirmação" — a descrição é o
que o modelo lê, e uma ferramenta que se anuncia como imediata convida o modelo a
prometer ao usuário o que não fez. Corrigido, com teste que impede a regressão.

**Resultado:** protegido; um achado real, corrigido.

---

## 5. Text-to-SQL (as quatro camadas)

**O ataque.** O modelo gera o SQL. Se o SQL gerado for executado como veio, o modelo tem
o banco.

**A defesa.** Quatro camadas independentes, em `app/domain/ai/sql_guard.py` e
`app/domain/ai/analytics.py`. Cada uma sozinha já barra o caso comum; juntas, quebrar uma
não basta:

1. **Uma instrução só.** `sqlglot` parseia; mais de um statement é recusado — mata
   `; DROP TABLE` antes de qualquer análise de texto.
2. **Só leitura, por tipo de nó da AST.** A raiz precisa ser `Select`/`Union`/`Subquery`,
   e qualquer `Insert`/`Update`/`Delete`/`Drop`/`Create`/`Alter`/`Truncate`/`Grant` em
   **qualquer** ponto da árvore reprova. Não é regex: `WHERE stage = 'delete me'` passa,
   e existe teste provando isso.
3. **Allowlist de relações.** Toda tabela encontrada na árvore (inclusive dentro de CTE e
   subconsulta) precisa estar em `ALLOWED_RELATIONS` — nove visões de indicadores, mais
   nada. Colunas e relações financeiras exigem acesso financeiro do usuário.
4. **Conexão somente-leitura.** A execução acontece dentro de um SAVEPOINT com
   `SET LOCAL transaction_read_only = on` e `statement_timeout = 5s`, com `LIMIT` imposto
   em 1.000 linhas. Esta camada não depende de análise de texto nenhuma: mesmo que as
   três primeiras falhassem, o Postgres recusa a escrita.

**Testes.** `tests/unit/test_sql_guard.py` (20 casos, cada camada isolada e quebrada de
propósito para confirmar que a seguinte segura) e
`tests/integration/test_ai_analytics.py`, onde um `INSERT` injetado à mão na conexão
somente-leitura é recusado **pelo banco**.

**Resultado:** protegido em profundidade.

---

## 6. Exfiltração por SQL

**O ataque.** Mesmo sem escrever, uma consulta permitida pode *ler* o que não devia: nome
de cliente, CPF, texto de intimação. A allowlist é o perímetro — o que estiver dentro
dela, o modelo pode pedir.

**A defesa.** As nove relações permitidas são visões de **indicador agregado**. Nenhuma
carrega nome, documento, e-mail, telefone, endereço ou texto livre; indicador não precisa
saber de quem é. A `ai_allowed_metrics` foi criada com `security_invoker = true`, então a
leitura acontece com o RLS de quem pergunta.

**Testes.** `test_ai_security.py::test_catalogo_analitico_nao_expoe_coluna_com_dado_pessoal`
lê `information_schema.columns` de cada relação da allowlist e reprova nomes de coluna
com cara de dado pessoal; `test_toda_relacao_da_allowlist_existe_de_fato` impede que um
nome errado na lista passe na revisão parecendo proteção.

**Resultado:** protegido, e a proteção falha ruidosamente se alguém adicionar uma visão
com PII à allowlist.

---

## 7. Auditoria imutável

**O ataque.** Apagar ou reescrever o registro do que a IA fez. Auditoria editável é
anotação, não prova.

**A defesa.** `ai_audit_log` é append-only por privilégio de banco: `rito_app` recebe
apenas `INSERT` e `SELECT`, e um trigger recusa UPDATE/DELETE. Não depende de o código
lembrar de não apagar.

**Testes.** `test_ai_actions.py::test_ai_audit_log_recusa_update_e_delete` e a
reconfirmação pós-fase em
`test_ai_security.py::test_ai_audit_log_continua_recusando_update_e_delete`, que lê os
privilégios do catálogo do Postgres.

**Resultado:** protegido no nível do banco.

---

## 8. Custo como questão de segurança

Um agente em laço é um incidente de custo, e chega sem aviso. Três defesas, todas da
spec 090:

- **Teto de passos.** 25 por execução, imposto pelo runtime (082, regra 9) — e agora
  verificado sobre os grafos **reais**, não só sobre grafos de teste
  (`tests/integration/test_graph_contract.py`, parametrizado pelo registro: grafo novo
  entra sozinho).
- **Timeout por nó e por execução.** Mesmo arquivo.
- **Orçamento mensal por escritório.** Alerta em 80%, bloqueio em 100%, verificado
  **antes** de chamar o modelo — bloquear depois seria pagar a chamada e negar o
  resultado. Desligar o bloqueio mantém o alerta, porque há escritório que prefere
  estourar o teto a parar no meio de um prazo. Mais o alerta de anomalia: feature gastando
  hoje ≥3× a média diária dos 30 dias anteriores **dela mesma**
  (`tests/integration/test_ai_budget.py`).

---

## 9. O que esta auditoria mudou

1. Descrição de cinco ferramentas de escrita passou a avisar que exige confirmação
   (vetor 4), com teste de regressão.
2. Todo prompt de sistema virou arquivo versionado em `app/ai/prompts/`, com as regras de
   segurança em **um** lugar (`SAFETY_RULES`) — antes eram quatro textos com as mesmas
   proibições ditas de quatro jeitos, que divergiriam na primeira correção.
3. Contrato de grafo passou a ser verificado sobre o registro real, não sobre grafos de
   teste.
4. Teto de gasto, cache de entrada idêntica e alerta de anomalia passaram a existir.

**Nenhum vetor em aberto.**
