# 136 — O dia do escritório atravessa o SQL

**Fase:** 13 · **Tipo:** correção · **Orçamento:** +2 s
**Depende de:** 011, 057, 059, 060, 077, 114, 124, 128 · **Status:** ✅ concluída

---

## 1. Objetivo

A spec 114 deu ao Python o «hoje» do escritório. Ela parou na fronteira do SQL: cinco
expressões continuavam perguntando o dia ao **Postgres**, que responde em UTC. Esta spec
termina a travessia — e fecha, no caminho, os defeitos de dinheiro que a auditoria de
08/09/2026 mediu: uma transferência entre contas próprias inflando o card «Atrasados», três
visões «deste mês» sem teto, o mês do CAC e o do custo por ponto cortados em UTC, a
planilha exportada com um dia e a tela com outro, e o parcelamento que respondia 500.

São oito defeitos, todos com prova. Nenhum levanta exceção — é por isso que passaram.

## 2. Por que o gate estava verde sobre isto

O `DTZ011` do Ruff e o meta-teste `test_nenhum_date_today_em_app` procuram `date.today()`.
`func.current_date()` não é `date.today()`: é uma função do Postgres, e o Postgres da
aplicação roda em UTC. Os dois guardas mais caros do projeto olhavam para o lado certo da
fronteira e para o lado errado do problema.

O caso que melhor mostra isso nasceu na spec **128**, há poucas horas: `posts/listing.py`
**recebe** `today` (o do escritório) para ROTULAR a linha e perguntava o dia ao banco para
FILTRAR. Entre 21h e a meia-noite em Brasília — até cinco horas em Rio Branco — a mesma
requisição afirmava as duas coisas: a tarefa que vence hoje voltava dentro de «Atrasadas» e
vinha marcada PENDENTE. Um arquivo, duas respostas, escritas com um dia de diferença.

## 3. Escopo

**A. O dia do escritório no SQL (4 dos 5 pontos do inventário da auditoria; o 5º na §4).**

| onde | era | virou |
|---|---|---|
| `posts/listing.py` (visão «Atrasadas») | `func.current_date()` | o `today` que a função já recebia |
| `lawsuits/listing.py` (`moved_today`) | `date_trunc('day', now())` | `_office_instant(_office_today())` |
| `lawsuits/listing.py` (3 visões «deste mês») | `date_trunc('month', current_date())` | `_this_month(coluna)`, com piso **e** teto |
| `lawsuits/listing.py` (`crm_stats`, «recebidos este mês») | `date_trunc('month', now())` | `_office_instant(_office_month_start())` |
| `bi/repository.py` (`new_customers`, `_allocated_costs_cte`) | `created_at`/`completed_at` cortados em UTC | `_office_month(coluna, fuso)` |

**B. «Atrasado», uma definição só.** `financial/dashboard.py::overdue_conditions` passa a
ser a única, e `dunning/repository.py::_overdue_condition` a chama.

**C. A competência dos pontos na matview.** Migration 136 substitui `bi_cost_allocation`.

**D. Export com o dia do escritório.** `customers/export.py` e `lawsuits/export.py`.

**E. Parcelamento que não pode dar 500.** Distribuição centavo a centavo em
`financial/service.py::_split_amount` + 422 no schema.

**F. Dívida 44.** `automations/conditions.py::_same` para de coagir string a booleano.

## 4. Fora de escopo

- **O `toISOString().slice(0,10)` do front** (`PayTransactionDialog`,
  `RetroactiveDateField`, `FinancialReportPage`): é o mesmo bug do outro lado da fronteira,
  e é o achado 2 da auditoria. Arquivo de outro dono neste ciclo.
- **O espelho de `_split_amount` em `frontend/src/lib/installments.ts`**: precisa da mesma
  distribuição, senão o preview mostra uma parcela e o servidor grava outra. Descrito na §10.
- **Threading do `Clock` real até os dois exports.** Ver §10.
- **As outras truncagens em UTC de `bi/repository.py`** (coorte do funil, ano do vintage):
  não dividem dinheiro e exigem o mesmo encanamento em mais três classes. §10.
- **`customers/repository.py:30`, o quinto ponto do inventário** — `age(current_date(),
  birthdate)` na faixa etária da estatística de contatos. Mesma família, e o arquivo é de
  outro dono neste ciclo. O conserto é o mesmo `_office_today()`; o efeito é de um dia na
  idade de quem faz aniversário hoje, o menor da lista.

## 5. Modelo de dados

Nenhuma tabela nova. Uma migration, que troca a definição de uma view materializada:

```sql
-- alembic/versions/136_competencia_do_escritorio.py
monthly_points AS (
  SELECT pu.tenant_id,
         date_trunc('month', timezone(COALESCE(a.timezone, 'America/Sao_Paulo'),
                                      pu.completed_at))::date AS competence,
         SUM(pu.points_earned) AS points
  FROM post_users pu
  LEFT JOIN accounts a ON a.tenant_id = pu.tenant_id   -- tenant_id é UNIQUE (011)
  WHERE pu.completed_at IS NOT NULL
  GROUP BY 1, 2
)
```

A 077 **não** foi editada (`CLAUDE.md` §9). `CREATE OR REPLACE` não existe para matview, e
por isso a migration derruba e recria também a view barreira
`bi_cost_allocation_visible`, o índice único do `REFRESH CONCURRENTLY` e os **dois**
`GRANT` (o de `rito_app`, da 077, e o de `rito_ai`, da 133). O `downgrade` volta ao SQL da
077, palavra por palavra.

## 6. Contratos de API

Nenhuma rota nova. Duas respostas mudam, e é o ponto da spec:

| Método | Rota | Antes | Agora |
|---|---|---|---|
| GET | `/api/v1/transactions/stats` | `overdue` somava transferência e despesa | só receita vencida em aberto |
| POST | `/api/v1/transactions` | **500** com parcelamento impossível | **422** `application/problem+json` com o mínimo necessário |

O 422 diz o motivo e o valor: *«Valor insuficiente para 100 parcelas: cada parcela precisa
de ao menos R$ 0,01 (mínimo R$ 1,00 para esse número de parcelas).»*

## 7. Front-end

**Componentes reutilizados:** nenhum — esta spec não desenha tela.
**Componentes criados:** nenhum.
O que muda para a UI: o card «Atrasados» passa a bater com o total da aba
«Inadimplência», e o formulário de parcelamento recebe uma mensagem em vez de um erro de
servidor.

## 8. Regras de negócio

1. **«Hoje» é sempre o do escritório, do Python ao SQL.** Onde o `Clock` chega, ele é o
   caminho (`posts`, `bi`, exports). Onde não chega — a listagem de processos e o CRM, que
   são chamados por `service.py`/`board_service.py` —, o fuso vem de `accounts.timezone`
   por subconsulta não correlacionada: uma linha por tenant, RLS aplicado, zero query nova.
2. **«Este mês» tem piso e teto.** `coluna >= inicio AND coluna < inicio + interval '1
   month'`. Data futura deixa de contar como produtividade do mês corrente.
3. **«Atrasado» tem uma definição só:** vencido, em aberto, não interno e **RECEITA**.
   Mora em `financial/dashboard.py::overdue_conditions`; a régua de cobrança a importa.
4. **A competência dos pontos e a dos custos são o mesmo mês** — o do escritório — nos dois
   lugares que precisam concordar: a matview e o CTE de rateio.
5. **O export formata o dia do escritório**, não o de UTC. A planilha e a tela mostram a
   mesma data para o mesmo registro.
6. **Toda parcela é maior que zero, e a soma fecha com o total.** A diferença entre a maior
   e a menor parcela é de no máximo um centavo.
7. **Parcelamento impossível é 422, não 500.** Menos de R$ 0,01 por parcela é recusado no
   schema, antes de qualquer escrita.
8. **Comparação booleana exige que os dois lados NOMEIEM um booleano.** `"false"` é falso;
   `"banana"` e `2` não são comparáveis com booleano e não casam.

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | visão «Atrasadas» usa o dia recebido, e não `CURRENT_DATE` | `tests/unit/test_dia_do_escritorio_no_sql.py` | ~0,1 s |
| unit | nenhuma das 4 visões de atividade pergunta o dia ao servidor | idem | ~0,1 s |
| unit | nenhuma das 12 visões de processo pergunta o dia ao servidor | idem | ~0,1 s |
| unit | as visões de dia/mês leem `accounts.timezone` | idem | ~0,1 s |
| unit | as três visões «deste mês» têm teto | idem | ~0,1 s |
| unit | «atrasado» tem uma definição só (financeiro == cobrança) | idem | ~0,1 s |
| unit | nenhuma parcela ≤ 0 e diferença máxima de um centavo (6 totais × 99 N) | `tests/unit/test_installment_split.py` | ~0,2 s |
| unit | valor que não dá um centavo por parcela levanta | idem | ~0,1 s |
| unit | `"false"` não casa com `True` (dívida 44), nos dois sentidos | `tests/unit/test_automation_conditions.py` | ~0,1 s |
| unit | texto que não nomeia booleano nunca casa | idem | ~0,1 s |
| integração | transferência vencida não entra no card «Atrasados» | `tests/integration/test_financial_dashboard.py` | ~0,4 s |
| integração | card e painel de inadimplência dão o mesmo número | idem | ~0,5 s |
| integração | visão «Atrasadas» e rótulo da linha nunca discordam | `tests/integration/test_posts.py` | ~0,5 s |
| integração | as três visões «deste mês» não alcançam o ano que vem | `tests/integration/test_lawsuits_listing.py` | ~0,7 s |
| integração/RLS | o dia do SQL é o do `Clock` de CADA tenant | idem | ~0,4 s |
| integração | planilha de processos traz o dia do escritório | idem | ~0,4 s |
| integração | planilha de contatos traz o dia do escritório | `tests/integration/test_customers_listing.py` | ~0,4 s |
| integração | contato das 23h47 de 31/08 conta em agosto (CAC) | `tests/integration/test_bi_costs.py` | ~0,4 s |
| integração | competência dos pontos é a do escritório (matview) | idem | ~1,0 s |
| integração | parcelamento impossível → 422 com o motivo | `tests/integration/test_transaction_series.py` | ~0,5 s |
| integração | R$ 1,00 em 100× gera cem parcelas de R$ 0,01 | idem | ~0,4 s |

**Total estimado:** +2 s
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

**Por que os testes de fuso olham a QUERY e não só o resultado.** A afirmação
comportamental («a tarefa que vence hoje não está atrasada») só distingue o certo do errado
nas três horas por dia em que o servidor virou o dia e o escritório não. Um teste assim é a
**dívida 30** de novo — suíte vermelha por causa da hora —, e o remédio não pode ter a
doença. A afirmação sobre o SQL vale 24 horas por dia. É o mesmo raciocínio que o cabeçalho
de `tests/integration/test_clock_tenant.py` já tinha escrito para a spec 114.

## 10. Descobertas

- **A migration 136 nasceu com o head em 133 e outra spec encadeou a 137 nela** no mesmo
  ciclo. Sem branch: `alembic heads` devolve um só.
- **`crm_stats` estourou o teto de 30 linhas por dois comentários.** `linhas_liquidas`
  (spec 121) conta do primeiro ao último statement, e comentário no meio conta — a mensagem
  de erro diz o contrário («a contagem já ignora»). A explicação foi para o docstring, que
  de fato não conta. Vale como achado sobre o gate, não sobre o código.
- **O teto de `@pytest.mark.commits` (spec 105) é 71 e estava em 71.** O teste da
  competência dos pontos precisa de `REFRESH MATERIALIZED VIEW` com commit real, então em
  vez de um teste novo o cenário entrou no que já existia
  (`test_custo_por_ponto_e_custo_fixo_dividido_por_pontos`), que agora conclui as tarefas às
  22h30 do último dia de um mês fixo no passado. **É uma mudança de comportamento desejada
  num teste existente**, e a razão é literal: aquele teste usava `_this_month_moment()`,
  cujo docstring diz que ele existe para «nunca cruzar a virada de mês». Ele contornava
  exatamente o caso quebrado. Agora a virada é o teste.
- **`tests/unit/test_installment_split.py` mudou em duas linhas, e as duas são desejadas.**
  `Decimal("0.01")` saiu da lista de totais da varredura de 2 a 100 parcelas e ganhou teste
  próprio: um centavo em duas parcelas não é um parcelamento com resto difícil, é um
  parcelamento **impossível**. A passagem dele por ali é o que escondia o defeito — o teste
  só olhava a soma, e a soma fechava mesmo com uma parcela de `0,00`.
- **`_split_amount` mantém o resto no fim da série.** A conta virou centavos com divisão
  inteira, mas quem recebe o centavo a mais continua sendo o fim da série: `999,97 ÷ 4` e
  `100,00 ÷ 3` dão exatamente o mesmo resultado de antes, e os dois testes que os afirmam
  não foram tocados.
- **`QuickViews` saiu de `posts/listing.py`.** As fábricas da infra de listagem (spec 030)
  não recebem parâmetro, e a visão «Atrasadas» precisa do dia. O registro virou um dicionário
  local de `Callable[[date], Predicate | None]`. `lawsuits/listing.py` continua com
  `QuickViews`, porque lá o dia vem de dentro do SQL e a fábrica segue sem parâmetro.
- **Os exports recebem `Clock | None`, com `Clock()` como padrão.** O `Clock` da requisição
  chega em `customers/router.py`, mas atravessá-lo até a coluna passa por
  `customers/service.py` e `lawsuits/router.py` — arquivos de outros donos neste ciclo. O
  padrão é o mesmo fallback que o `Clock` já usa para conta sem fuso configurado
  (`America/Sao_Paulo`), nunca o do servidor: o defeito medido está corrigido, e o
  escritório em Manaus ganha o dia certo quando o parâmetro for ligado na ponta.
- **`_office_day_br` está duplicado nos dois exports.** São dois usos; a regra dos 3 usos
  (`CLAUDE.md` §6) dispara no terceiro, e quando disparar o lugar dela é `app/core/export.py`,
  junto do `TableExport`.
- **Dívida 44: alcançável pela API, latente pela UI.** O `AutomationBuilder` da spec 092 não
  tem editor de condição — ele manda `condition: null` — e o diálogo de teste não tem campo
  de payload. Mas `condition` é `dict[str, Any]` no schema e o payload de
  `POST /automations/{id}/simulate` também: os dois lados são digitados por quem usa a API, e
  `{op: "eq", value: "false"}` contra um campo `true` casava. Corrigido de qualquer forma —
  a alternativa é deixar uma armadilha armada esperando a tela que vai editar condições.
- **O `-p no:logging` do runner esconde a fixture `caplog`.** Dois testes que a usam viram
  erro de setup quando se roda com esse flag. Não é defeito do repositório; é armadilha de
  quem depura.

## 11. O gate que falta, e o texto dele

O `DTZ` e o `test_nenhum_date_today_em_app` não alcançam `func.current_date()`. Esta spec
não pode criar meta-teste novo (arquivo de outro dono no ciclo), então o texto proposto fica
registrado aqui — e a §9 do relatório o repete para quem for aplicá-lo:

```python
def test_nenhum_hoje_do_servidor_em_app() -> None:
    """Spec 136: `date.today()` saiu do Python na 114; `current_date()` continuou no SQL.

    `func.current_date()`, `func.now()` e `func.statement_timestamp()` respondem no fuso do
    SERVIDOR. Como duração (`now() - interval '30 days'`) isso é correto e continua
    permitido; como DIA — dentro de `date_trunc`, comparado com uma coluna `date` ou
    truncado com `cast(..., Date)` — é o bug que a 114 tirou do Python e que este gate
    impede de voltar pelo SQL.
    """
    proibidas = {"current_date": None, "now": "date_trunc", "statement_timestamp": "date_trunc"}
    ...  # AST: ast.Call cujo func é Attribute("current_date"/"now") sobre Name("func"),
         # reprovando `current_date` sempre e `now`/`statement_timestamp` quando o nó pai é
         # `date_trunc(...)` ou um `cast(..., Date)`.
    assert ofensores == [], (
        "«hoje» no SQL é o dia do servidor (UTC), não o do escritório (spec 114/136). "
        "Receba o dia por parâmetro (`Clock.today()`) ou derive-o de `accounts.timezone` "
        "como `lawsuits/listing.py::_office_today`.\n" + "\n".join(ofensores)
    )
```

A exceção legítima a declarar junto: `app/domain/lawsuits/listing.py::_office_today`, que
usa `statement_timestamp()` **para convertê-lo** ao fuso da conta — é a implementação do
conserto, não uma violação.

## 12. Definição de pronto

- [x] Os 8 defeitos corrigidos, nada além
- [x] Todas as 8 regras com teste (21 testes, 11 deles vindos das provas da auditoria)
- [x] Teste de isolamento por tenant para a leitura nova de `accounts` (§8, regra 1)
- [x] Nenhuma tabela nova; a matview trocada mantém as duas concessões de leitura
- [x] Testes dos domínios tocados verdes; as duas mudanças em teste existente justificadas na §10
- [x] Sem `Any`, `# type: ignore` ou `# noqa` novos
- [ ] `ROADMAP.md` atualizado para ✅ — texto no relatório; o arquivo é de outro dono no ciclo
- [ ] `docs/DIVIDA-TECNICA.md` fechando a dívida 44 — idem
- [x] Commit `fix(136): o dia do escritório atravessa o SQL`
