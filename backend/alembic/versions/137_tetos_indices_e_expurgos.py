"""137: os índices que o RLS desligava, os tetos que faltavam e o expurgo que sobrou

Revision ID: 137_tetos_indices
Revises: 126_prazo_das_intimacoes
Create Date: 2026-09-08

## Parte 1 — o motivo real de nenhum índice trigram ser usado

A auditoria apontou que a busca de contatos escrevia `unaccent(lower(name))` no `WHERE`
enquanto o índice era sobre `immutable_unaccent(lower(name))`, e que por isso o planner
nunca casava os dois. Está certo, e a troca da função está em `core/listing.py`. Mas
trocar a função **não bastava**, e a medição mostrou por quê.

Sob Row Level Security, um predicado só pode virar condição de índice se for
`LEAKPROOF` — senão ele seria avaliado ANTES da política de tenant, sobre linhas de
outros escritórios, e um erro ou um tempo de resposta dependente do dado vazaria o que a
política existe para esconder. O Postgres implementa isso literalmente
(`restriction_is_securely_promotable`): a política tem nível de segurança 0, o filtro do
usuário tem nível 1, e nível 1 só é promovido a condição de índice se for leakproof.

Nenhuma peça do predicado de busca era leakproof — nem o operador `~~*`, nem `lower()`,
nem `immutable_unaccent()`. Resultado medido com 100 mil contatos, sob RLS, com o índice
existindo e correto: `Parallel Seq Scan`, 139 ms. Como superusuário, onde o RLS não se
aplica, o MESMO predicado usa o índice em 3,2 ms. Os seis índices `gin_trgm_ops` do
schema (contatos, pasta do processo, comentário e local da tarefa, cidade, tribunal)
estavam mortos desde que foram criados.

O que esta migration faz a respeito, e o que decidiu NÃO fazer:

- **`texticlike(text,text)` (o operador `ILIKE`) passa a LEAKPROOF.** É a única peça de
  catálogo tocada, e é a mínima possível: sem ela nenhum índice trigram pode ser usado
  sob RLS, com ou sem as outras mudanças. A função é total sobre texto — não levanta erro
  em função do DADO (só de um padrão malformado, que vem da consulta, não da linha), e o
  projeto já depende de o planner avaliar `texteq` sobre linhas de outros tenants em todo
  índice de igualdade que existe: `=` é leakproof desde sempre. `textlike` (`LIKE`, sem
  ignorar caixa) fica como está, porque nenhuma busca do Rito o usa.
- **`immutable_unaccent(text)` passa a LEAKPROOF.** É nossa, é `SELECT unaccent(...)`,
  não erra em função do dado.
- **`lower()` NÃO é marcada.** Em vez de tocá-la, o predicado deixou de usá-la: `ILIKE`
  já ignora caixa por conta própria, então `immutable_unaccent(name) ILIKE '%q%'` dá o
  mesmo resultado com uma função a menos na expressão. Por isso o índice de contatos é
  recriado sem o `lower()`.

Medido depois, sob RLS, com 100 mil contatos: `Bitmap Index Scan`, **4,5 ms** contra os
139 ms de antes. E `transactions.description`, que ganhou índice nesta migration:
**7,0 ms** contra 66 ms.

> **Isto não sobrevive a um `pg_restore`.** `pg_dump` não emite `ALTER FUNCTION` de
> objeto de catálogo. Depois de restaurar um backup, os índices trigram voltam a ser
> ignorados em silêncio — plano pior, resultado igual. É o que
> `tests/integration/test_indices_de_busca.py` guarda: ele falha se o `proleakproof`
> não estiver de pé, e é a única forma de esse estado voltar a ser notado.

## Parte 2 — os índices que faltavam

- `ix_customers_name_trgm` recriado sobre `immutable_unaccent(name)` (ver Parte 1).
- `ix_transactions_description_trgm`: o filtro `q` do financeiro fazia
  `description ILIKE '%…%'` sem índice, e a requisição paga a varredura duas vezes
  (página e cartões de topo). Medido em 200 mil lançamentos: 66 ms por varredura.
- `ix_posts_schedule` e `ix_posts_schedule_deadline`: a agenda filtra por
  `show_in_schedule` + eixo (compromisso ou prazo fatal) e não havia índice para isso —
  `Seq Scan` em 200 mil tarefas, 21 ms por navegação de mês.
- `ix_notifications_recent`: a listagem padrão do sino é
  `user_id = ? ORDER BY created_at DESC` e o único índice que serviria
  (`ix_notifications_unread`) é PARCIAL em `read_at IS NULL` — não serve a lista completa.
  `Parallel Seq Scan` com 100 mil linhas.
- `ix_deliveries_created`: o expurgo de webhooks passou a apagar por
  `created_at < corte` (spec 137, defeito 1) e precisa de um índice para o `LIMIT` do
  lote não varrer a tabela.

## Parte 3 — nenhum índice para a ordenação de Atividades, e o motivo

A auditoria pediu índice de expressão para `coalesce(scheduled_date, …)` em
`GET /api/v1/posts`. Foi construído e medido: o índice é USADO, e a página fica **mais
lenta** — 176 ms contra 126 ms. O `count(*) OVER ()` do contrato de listagem obriga a ler
todas as linhas de qualquer forma, e o índice troca uma varredura sequencial por 200 mil
acessos aleatórios ao heap. O gargalo não é a ordenação, é a janela; a correção mora em
`app/domain/posts/listing.py` e custa uma query a mais, que não cabe nas 3 do §11. Está
registrado como dívida, sem índice órfão deixado para trás.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "137_tetos_indices"
down_revision: str | None = "136_competencia_do_escritorio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nome, tabela, definição depois do nome) — a lista que sobe e desce.
_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "ix_customers_name_trgm",
        "ON customers USING gin (immutable_unaccent(name) gin_trgm_ops)",
    ),
    (
        "ix_transactions_description_trgm",
        "ON transactions USING gin (description gin_trgm_ops) WHERE description IS NOT NULL",
    ),
    (
        "ix_posts_schedule",
        "ON posts (tenant_id, scheduled_date) "
        "WHERE show_in_schedule AND scheduled_date IS NOT NULL",
    ),
    (
        "ix_posts_schedule_deadline",
        "ON posts (tenant_id, deadline_date) WHERE show_in_schedule AND deadline_date IS NOT NULL",
    ),
    (
        "ix_notifications_recent",
        "ON notifications (tenant_id, user_id, created_at DESC, id DESC)",
    ),
    (
        "ix_deliveries_created",
        "ON webhook_deliveries (tenant_id, created_at)",
    ),
)


def upgrade() -> None:
    # Parte 1. As duas únicas funções marcadas, e a razão de cada uma está no cabeçalho.
    op.execute("ALTER FUNCTION pg_catalog.texticlike(text, text) LEAKPROOF")
    op.execute("ALTER FUNCTION public.immutable_unaccent(text) LEAKPROOF")

    # O índice de contatos é RECRIADO: a expressão antiga carregava um `lower()` que
    # impede a promoção do predicado sob RLS (Parte 1).
    op.execute("DROP INDEX IF EXISTS ix_customers_name_trgm")
    for nome, definicao in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {nome} {definicao}")


def downgrade() -> None:
    for nome, _definicao in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {nome}")
    # Volta a expressão da migration 017.
    op.execute(
        "CREATE INDEX ix_customers_name_trgm ON customers "
        "USING gin (immutable_unaccent(lower(name)) gin_trgm_ops)"
    )
    op.execute("ALTER FUNCTION public.immutable_unaccent(text) NOT LEAKPROOF")
    op.execute("ALTER FUNCTION pg_catalog.texticlike(text, text) NOT LEAKPROOF")
