# 126 — Prazo das intimações roteadas

**Fase:** 12 · **Tipo:** feature · **Orçamento:** +2,6 s
**Depende de:** 038, 045, 086 · **Status:** ✅ concluída

---

## 1. Objetivo

A tarefa "Intimações Judiciais" da spec 045 nasce desde 2026 com `deadline_date` NULL —
**dívida técnica 18**, que já mudou de dono quatro vezes (086 → 122 → 123 → 126). O campo
vazio é indistinguível, na tela, de "o usuário não definiu prazo", e a 050 pôs um aviso
visual em vez de inventar uma conta que não existia.

Esta spec entrega a conta. Ela separa, com cuidado, duas coisas que a dívida tratava como
uma só:

- **a mecânica da contagem** — quando o prazo começa a correr, quais dias contam, quando
  vence. Isso é lei (CPC arts. 219, 220 e 224), é determinístico, e nasce em
  `app/core/dates.py`, ao lado dos dias úteis que a 038 já tinha;
- **quantos dias cada intimação dá** — 15 para contestar, 5 para embargar, 30 para a
  Fazenda. Isso é uma tabela de produto por classe/assunto do CNJ que **ninguém
  especificou neste projeto**, e a 126 **não a inventa**. O número passa a vir de uma
  declaração explícita do escritório.

Um prazo que o escritório configurou é auditável. Um que o software adivinhou não é — e
prazo errado é pior que prazo ausente, porque `NULL` é honesto e um número é confiado.

## 2. Escopo

- `procedural_deadline`, `add_procedural_days`, `publication_date`, `is_procedural_day` e
  `is_court_recess` em `app/core/dates.py` — a cadeia disponibilização → publicação →
  dia 1 → vencimento, em dias úteis ou corridos, com o recesso forense do art. 220.
- `publication_deadline_settings`: o prazo padrão que o escritório declara (dias +
  espécie da contagem), com quem declarou e quando.
- `GET`/`PUT /api/v1/publications/deadline-settings`.
- `PublicationRoutingService` passa a criar a tarefa com `deadline_date` calculado quando
  há configuração, e explicitamente `NULL` quando não há.
- `publications/deadline.py` (a conta da 086) passa a delegar à mecânica única — o que
  **corrige** um erro de contagem descrito na §9.
- Seed de feriados nacionais de **2031 a 2040**, que a 038 deixou pendente e a dívida 18
  cobra junto.

## 3. Fora de escopo

- **A tabela de prazos por classe/assunto do CNJ.** É o coração da dívida 18 e a 126
  deliberadamente não a entrega. A evidência que sustenta essa decisão está na §9: nem o
  levantamento do ADVBOX, nem as migrations, nem os seeds, nem os modelos deste projeto
  têm qualquer taxonomia de prazo em dias — `task_types`, `action_groups`,
  `lawsuit_types` e `stages` não têm campo de dias. O único "prazo em dias" do
  levantamento inteiro é o `fake_days` da etapa de workflow, que é um número que o
  escritório digita. Inventar a tabela aqui seria produzir números plausíveis e errados
  para 100% dos escritórios, e é exatamente o que a spec 101 recusou fazer.
- **Prazo por grupo de ação / tipo de ação / etapa.** O refinamento natural do que esta
  spec entrega, e ele precisa de coluna em `action_groups` — fora dos arquivos desta
  spec. Ver §9.
- **Feriados estaduais e municipais e suspensões por portaria de tribunal.** A tabela
  `holidays` é nacional por design (038). Limitação conhecida e registrada.
- **Tela de configuração no front-end.** O endpoint existe e é testado; a tela não entra
  aqui. Ver §6 e §9.
- Leitura do prazo do TEXTO da intimação → é a spec 086, que já existe.

> Fora de escopo é vinculante. Se durante a implementação surgir algo daqui,
> anote em `## 9. Descobertas` e siga — não implemente.

## 4. Modelo de dados

```sql
CREATE TABLE publication_deadline_settings (
  id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id               UUID NOT NULL REFERENCES tenants(id),
  default_deadline_days   SMALLINT,           -- NULL = o escritório não declarou
  count_in_business_days  BOOLEAN NOT NULL DEFAULT true,
  updated_by              UUID REFERENCES users(id),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
  CONSTRAINT uq_pub_deadline_settings_tenant UNIQUE (tenant_id),
  CONSTRAINT ck_pub_deadline_days_range
    CHECK (default_deadline_days IS NULL OR default_deadline_days BETWEEN 1 AND 365)
);
CREATE INDEX ix_pub_deadline_settings_updated_by ON publication_deadline_settings (updated_by);
-- + ENABLE/FORCE ROW LEVEL SECURITY e política tenant_isolation (enable_rls_statements)

INSERT INTO holidays (date, name, is_national) VALUES ...  -- 2031 a 2040, 130 linhas
  ON CONFLICT (date) DO NOTHING;
```

`default_deadline_days` é anulável **de propósito**: o estado inicial de todo escritório é
"não declarou", e é ele que mantém o `deadline_date` nulo que a 045 produzia.

Migration: `alembic/versions/126_prazo_das_intimacoes.py` (revises `124_relogio_e_fuso`).

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/publications/deadline-settings` | — | `200 {default_deadline_days, count_in_business_days, updated_by, updated_at}` | COLABORADOR |
| PUT | `/api/v1/publications/deadline-settings` | `{default_deadline_days: int\|null, count_in_business_days: bool}` | `200 {...}` | GESTOR |

Erros (RFC 7807): `403` (colaborador tentando declarar), `422` (dias fora de 1–365).

Escritório que nunca configurou responde **200 com campos nulos**, não 404: "não
configurado" é um estado do escritório, não um recurso inexistente.

## 6. Front-end

**Componentes reutilizados:** nenhum — esta spec não tem tela.
**Componentes criados:** nenhum.

O contorno visual da 050 (`PostDetailPage` mostrando "Prazo não calculado" quando a tarefa
é do tipo "Intimações Judiciais" e `deadline_date` é nulo) **continua correto e continua
necessário**: ele passa a descrever o escritório que não declarou prazo, que é a maioria.

A tela de configuração fica pendente e está registrada na §9 — o endpoint é utilizável por
API e por `rito`, mas nenhum gestor vai encontrá-lo na interface até alguém desenhar o
campo.

## 7. Regras de negócio

1. A tarefa da intimação nasce com `deadline_date` calculado **quando, e só quando**, o
   escritório declarou `default_deadline_days`. Sem declaração, `NULL`.
2. O cálculo parte da **disponibilização** (`publications.availability_date`) e segue a
   cadeia do CPC: a **publicação** é o primeiro dia útil seguinte (art. 224 §2); o **dia
   1** é o primeiro dia em que o prazo corre depois dela (art. 224 caput e §3); a
   contagem é em **dias úteis** (art. 219) e **não corre entre 20/12 e 20/01** (art. 220).
3. Feriado nacional não conta, e os feriados vêm da tabela global `holidays` (038) — não
   de uma lista no código. Vencimento de prazo em dias corridos que caia em dia sem
   expediente prorroga para o dia útil seguinte (art. 224 §1).
4. Prazo calculado nasce com a **procedência escrita** no comentário da tarefa: o número
   veio do padrão do escritório, não da leitura desta intimação, e quem abrir precisa
   saber disso para conferir contra o texto.
5. Declarar `null` desliga o cálculo. As intimações seguintes voltam a nascer sem prazo —
   o cálculo é opt-in a cada momento, não um caminho sem volta.
6. Só **GESTOR** ou acima declara; qualquer usuário autenticado lê. Quem declarou fica
   gravado em `updated_by`/`updated_at` — é isso que separa prazo auditável de palpite.
7. `0` e negativos são recusados com 422: "sem prazo" se diz com `null`, não com zero.
   Acima de 365 dias também — é erro de digitação, não prazo de intimação.
8. `scheduled_date` continua sendo a `availability_date` (spec 045, regra 3). O prazo é
   outro campo e não desloca o compromisso.
9. `publication_deadline_settings` é tabela de domínio: `tenant_id NOT NULL` + RLS. O
   escritório B não vê nem herda o que o A declarou.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | publicação = 1º dia útil após a disponibilização (6 casos) | `tests/unit/test_dates.py` | ~0,01 s |
| unit | recesso pega as duas pontas, 20/12 e 20/01 (6 casos) | `tests/unit/test_dates.py` | ~0,01 s |
| unit | dia de recesso não é dia de prazo, mesmo sendo dia útil | `tests/unit/test_dates.py` | ~0,01 s |
| unit | prazo em dias úteis: 1/5/15/30 dias, sexta, véspera de feriado, feriado emendado (8 casos) | `tests/unit/test_dates.py` | ~0,01 s |
| unit | recesso suspende o curso: antes, durante e no meio da contagem (4 casos) | `tests/unit/test_dates.py` | ~0,01 s |
| unit | dias corridos prorrogam o vencimento (3 casos) | `tests/unit/test_dates.py` | ~0,01 s |
| unit | calendário vazio conta a menos — a prova de por que o seed importa | `tests/unit/test_dates.py` | ~0,01 s |
| unit | `days < 1` e offset negativo são erro | `tests/unit/test_dates.py` | ~0,01 s |
| unit | a conta da 086 continua coerente com a mecânica única (11 casos) | `tests/unit/test_publication_deadline.py` | ~0,01 s |
| integração | intimação roteada nasce com o prazo certo | `tests/integration/test_publication_routing.py` | ~0,15 s |
| integração | o comentário traz a procedência do número | `tests/integration/test_publication_routing.py` | ~0,15 s |
| integração | dias corridos quando o escritório escolhe | `tests/integration/test_publication_routing.py` | ~0,15 s |
| integração | feriados e recesso vêm do banco | `tests/integration/test_publication_routing.py` | ~0,15 s |
| integração | **sem configuração, `deadline_date` continua NULL** | `tests/integration/test_publication_routing.py` | ~0,15 s |
| integração | apagar a configuração devolve o prazo a nulo | `tests/integration/test_publication_routing.py` | ~0,25 s |
| integração | GET responde vazio antes de alguém configurar | `tests/integration/test_publication_routing.py` | ~0,1 s |
| integração | PUT grava quem declarou | `tests/integration/test_publication_routing.py` | ~0,15 s |
| integração | colaborador lê, não declara (403) | `tests/integration/test_publication_routing.py` | ~0,2 s |
| integração | 0, negativo e 400 dias → 422 | `tests/integration/test_publication_routing.py` | ~0,2 s |
| RLS | tenant A não vê o prazo padrão do tenant B | `tests/integration/test_publication_routing.py` | ~0,2 s |

**Total medido:** unit 0,05 s; integração de roteamento de 5,74 s para 8,0 s (**+2,3 s**).
**Fixtures externas:** nenhuma chamada de rede — os testes de análise (086) seguem com o
`ScriptedProvider`.

## 9. Descobertas

### A taxonomia de prazo não existe neste projeto, e a busca foi exaustiva

Antes de decidir, procurei nas quatro fontes que poderiam tê-la:

1. **`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md`** — o levantamento fala de prazo em 15
   lugares e em **nenhum** deles há um número de dias por tipo de ato. `date_deadline` é
   um campo de formulário livre (`__/__/____`); "Prazo fatal" é uma seção da caixa de
   entrada e uma coluna de ordenação; a automação promete "calcula prazos" sem dizer
   como. O único "prazo em dias" do documento inteiro é o **`fake_days` da etapa de
   workflow** (§3): "prazo em dias úteis, opcional" — um número que o escritório digita.
   O agente "Justin-e" anuncia "contagem automática de prazo" como marketing, sem
   taxonomia atrás.
2. **Modelos** — `task_types`, `action_groups`, `lawsuit_types` e `stages` não têm campo
   de dias. `workflow_steps.days_offset` tem, e é exatamente o `fake_days` acima.
3. **Migrations e seeds** — os catálogos globais semeados (tribunais, códigos de
   movimento do CNJ, etapas, plano de contas) não incluem prazo. A tabela de classes e
   assuntos do CNJ não existe no schema.
4. **Specs 045, 038, 086 e 101** — a 045 diz textualmente "não invente prazo aqui"; a 101
   registrou que "contagem de dias úteis por classe/assunto do CNJ é um problema em si,
   não um stub esquecido".

Daí a decisão da §3: mecânica implementada e testada; número declarado pelo escritório.

### A conta da 086 estava errada em um dia útil, e a correção está aqui

`publications/deadline.py` fazia `add_business_days(availability_date, days)` e a
docstring afirmava seguir o art. 224. Ela seguia **metade** dele: a data de
**disponibilização** era usada como se fosse a data de **publicação**, e o §2 do art. 224
("considera-se como data da publicação o primeiro dia útil seguinte ao da
disponibilização") nunca acontecia. Todo prazo sugerido pela IA saía **um dia útil mais
curto** que o legal.

O erro era conservador — vencer antes não faz perder prazo —, mas é erro, e ele estava
escondido pelo vocabulário: o parâmetro se chama `availability_date` e o teste chamava a
variável de `publicacao`. Corrigido: `compute_deadline` agora delega a
`procedural_deadline`, que faz os dois passos. As datas esperadas de
`tests/unit/test_publication_deadline.py` e de `tests/integration/test_publication_analysis.py`
andaram junto, e o cabeçalho de cada arquivo explica por quê — **é a única mudança de
comportamento em código anterior que esta spec faz**, e ela é uma correção, não um efeito
colateral.

### O recesso forense não era modelado em lugar nenhum

`grep -rn "recesso\|art. 220"` no repositório inteiro devolve **uma** ocorrência: a
palavra "suspensões" no texto da própria dívida 18. `holidays` só tem feriados nacionais.
Como o art. 220 é lei processual, e não taxonomia de produto, ele entrou — como parâmetro
explícito (`court_recess`, padrão `True`), não como constante escondida, para que um prazo
administrativo possa contar sem ele. É o caso em que a versão anterior errava mais feio:
uma intimação disponibilizada em 23/12/2026 recebia vencimento em 04/01/2027, no meio de
um período em que a lei suspende a contagem.

### O que a 126 NÃO fecha da dívida 18, dito com todas as letras

A dívida 18 pede "contagem de dias úteis, suspensões, tipo de prazo por classe/assunto do
CNJ". Os dois primeiros estão entregues e testados. **O terceiro não está, e não vai estar
por esta spec.** O que substitui o terceiro é uma declaração por escritório — auditável,
mas **uniforme**: uma única contagem para toda intimação que entra, e o advogado ainda
precisa conferir intimação a intimação. Quem quiser o prazo por tipo de ato tem hoje dois
caminhos, os dois já no produto: a leitura do texto pela IA da 086 (com revisão humana) e
a edição manual do campo na tarefa.

Portanto: **a dívida 18 fica parcialmente resolvida**, com o resíduo nomeado — "prazo por
classe/assunto do CNJ" —, que é trabalho de produto, não de código, e precisa de alguém
que decida a tabela antes de alguém escrevê-la.

### Resíduos menores, todos fora dos arquivos desta spec

- **Sem tela.** `GET`/`PUT /publications/deadline-settings` não têm UI. Enquanto não
  tiverem, nenhum escritório vai declarar prazo pela interface e o comportamento visível
  do produto continua sendo o `NULL` de antes. `frontend/` é de outra spec.
- **Refinamento por grupo de ação.** `action_groups` já carrega `publications_user_id`
  (quem recebe as intimações do grupo); um `publications_deadline_days` ao lado seria o
  passo natural, e cai fora dos arquivos desta spec.
- **O seed de feriados expira de novo.** 2031–2040 compra uma década; a tabela esvazia em
  01/01/2041. Vale a lição que a 038 já tinha aprendido e que ninguém agendou: um seed com
  data de validade precisa de um teste que grite antes de vencer, não de um comentário.
- **`updated_by` ganhou índice** que a tabela não precisa para ler (ela tem no máximo uma
  linha por escritório) — é o gate de FK sem índice da 098, e ele está certo: sem o
  índice, apagar um usuário varre a tabela.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (9 regras; 33 casos unitários + 10 de
      integração)
- [x] Teste de isolamento por tenant (tabela nova — `test_configuracao_de_prazo_nao_atravessa_tenant`)
- [x] Testes desta spec verdes: 33 unit (`test_dates.py`) + 11 unit
      (`test_publication_deadline.py`) + 26 integração (`test_publication_routing.py`) +
      14 integração (`test_publication_analysis.py`)
- [x] `ruff`, `black` e `mypy` verdes nos arquivos da spec
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário — o
      `type: ignore` que existia em `analysis.py` continua onde estava, com a mesma
      justificativa
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos — `_advance` unifica o laço
      de `add_business_days` e `add_procedural_days`; a conta da 086 e a do roteamento
      passam pela MESMA `procedural_deadline`
- [ ] `ROADMAP.md` atualizado para ✅ — texto entregue no relatório; o arquivo é de
      escrita compartilhada nesta rodada
- [ ] Commit `feat(126): prazo das intimações roteadas`
