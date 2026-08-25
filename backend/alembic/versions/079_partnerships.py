"""parcerias entre escritórios

Revision ID: 079_partnerships
Revises: 078_aggregate_registry
Create Date: 2026-08-25

Spec 079 §4: `partnerships` (convite por e-mail, aceite bilateral), `shared_lawsuits`
(compartilhamento POR PROCESSO, com escopo explícito) e `partnership_audit_logs`
(regra 11 — toda ação de compartilhamento auditada).

Decisão de isolamento (spec 079 §9): **nenhuma política de RLS das tabelas existentes
muda**. O parceiro continua sem enxergar uma única linha do dono pelas queries normais
— listagens, relatórios e BI seguem exatamente como antes. O acesso cross-tenant vive
inteiro num punhado de funções `SECURITY DEFINER` (dona = superusuário da migration,
mesmo padrão de `lookup_ical_feed`, spec 037), cada uma com o mesmo guarda: existe
compartilhamento ATIVO daquele processo para `current_setting('app.tenant_id')`.
Estender a política de `lawsuits`/`posts` seria mais curto, mas o processo do parceiro
passaria a entrar nas agregações dele (regra 4 proíbe: BI e relatórios do dono são
invisíveis) — o furo apareceria longe daqui, num relatório.

`partnerships`/`shared_lawsuits` não têm `tenant_id`: a linha pertence aos DOIS lados.
Por isso as políticas são escritas à mão em vez de `enable_rls_statements`, e a escrita
é sempre do lado dono (o aceite e o encerramento, que tocam a linha do outro lado,
passam por função `SECURITY DEFINER` — sem política de UPDATE para o parceiro, que
senão poderia ampliar o próprio escopo com um UPDATE direto).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "079_partnerships"
down_revision: str | None = "078_aggregate_registry"
branch_labels: str | None = None
depends_on: str | None = None

partnership_status = postgresql.ENUM(
    "PENDENTE", "ATIVA", "RECUSADA", "ENCERRADA", name="partnership_status"
)

_CURRENT = "current_setting('app.tenant_id', true)::uuid"

# ---------------------------------------------------------------- RLS manual

_POLICIES = [
    # Só o lado que convidou escreve; o outro lado lê e, para aceitar/encerrar, passa
    # pelas funções abaixo.
    f"""CREATE POLICY partnerships_read ON partnerships FOR SELECT
        USING (requester_tenant_id = {_CURRENT} OR partner_tenant_id = {_CURRENT})""",
    f"""CREATE POLICY partnerships_write ON partnerships FOR ALL
        USING (requester_tenant_id = {_CURRENT})
        WITH CHECK (requester_tenant_id = {_CURRENT})""",
    f"""CREATE POLICY shared_lawsuits_read ON shared_lawsuits FOR SELECT
        USING (owner_tenant_id = {_CURRENT} OR partner_tenant_id = {_CURRENT})""",
    f"""CREATE POLICY shared_lawsuits_write ON shared_lawsuits FOR ALL
        USING (owner_tenant_id = {_CURRENT})
        WITH CHECK (owner_tenant_id = {_CURRENT})""",
]

# ---------------------------------------------- funções SECURITY DEFINER

# Guarda único de todo o resto: uma linha se, e só se, o processo está compartilhado
# ATIVO com o tenant da sessão. Toda outra função consulta esta.
_SHARE_FOR = """
CREATE OR REPLACE FUNCTION partner_share_for(p_lawsuit_id uuid)
RETURNS TABLE(
    share_id uuid,
    partnership_id uuid,
    owner_tenant_id uuid,
    can_view_financial boolean,
    can_create_tasks boolean
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT s.id, s.partnership_id, s.owner_tenant_id, s.can_view_financial, s.can_create_tasks
    FROM shared_lawsuits s
    JOIN partnerships p ON p.id = s.partnership_id
    WHERE s.lawsuit_id = p_lawsuit_id
      AND s.partner_tenant_id = current_setting('app.tenant_id', true)::uuid
      AND s.revoked_at IS NULL
      AND p.status = 'ATIVA'
$$;
"""

_SHARED_LIST = """
CREATE OR REPLACE FUNCTION partner_shared_lawsuits()
RETURNS TABLE(
    share_id uuid,
    partnership_id uuid,
    lawsuit_id uuid,
    owner_tenant_id uuid,
    owner_name text,
    process_number text,
    folder text,
    stage_name text,
    step_id smallint,
    can_view_financial boolean,
    can_create_tasks boolean,
    case_value numeric,
    fees_value numeric,
    open_tasks bigint,
    shared_at timestamptz
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT s.id,
           s.partnership_id,
           l.id,
           s.owner_tenant_id,
           t.name,
           l.process_number,
           l.folder,
           st.name,
           st.step_id,
           s.can_view_financial,
           s.can_create_tasks,
           -- Regra 9: valor financeiro só sai do banco com permissão explícita no
           -- compartilhamento — o financial_access do tenant do parceiro não conta.
           CASE WHEN s.can_view_financial THEN l.case_value END,
           CASE WHEN s.can_view_financial THEN l.fees_value END,
           (SELECT count(*) FROM posts po
             JOIN post_users pu ON pu.post_id = po.id
            WHERE po.lawsuit_id = l.id AND pu.completed_at IS NULL),
           s.created_at
    FROM shared_lawsuits s
    JOIN partnerships p ON p.id = s.partnership_id
    JOIN lawsuits l ON l.id = s.lawsuit_id
    JOIN tenants t ON t.id = s.owner_tenant_id
    JOIN stages st ON st.id = l.stage_id
    WHERE s.partner_tenant_id = current_setting('app.tenant_id', true)::uuid
      AND s.revoked_at IS NULL
      AND p.status = 'ATIVA'
$$;
"""

_SHARED_PARTIES = """
CREATE OR REPLACE FUNCTION partner_shared_parties(p_lawsuit_id uuid)
RETURNS TABLE(pole text, name text, is_client boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT lp.pole::text, c.name, lp.is_client
    FROM lawsuit_parties lp
    JOIN customers c ON c.id = lp.customer_id
    WHERE lp.lawsuit_id = p_lawsuit_id
      AND EXISTS (SELECT 1 FROM partner_share_for(p_lawsuit_id))
    ORDER BY lp.pole, c.name
$$;
"""

_SHARED_TIMELINE = """
CREATE OR REPLACE FUNCTION partner_shared_timeline(p_lawsuit_id uuid, p_limit integer)
RETURNS TABLE(id uuid, occurred_at timestamptz, title text, body text, origin text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT m.id, m.occurred_at, m.title, m.body, m.origin::text
    FROM lawsuit_movements m
    WHERE m.lawsuit_id = p_lawsuit_id
      AND EXISTS (SELECT 1 FROM partner_share_for(p_lawsuit_id))
    ORDER BY m.occurred_at DESC
    LIMIT p_limit
$$;
"""

# `from_partner` distingue a demanda que o parceiro pediu da tarefa do próprio dono
# (regra 8: a tarefa criada pelo parceiro é marcada com a origem).
_SHARED_TASKS = """
CREATE OR REPLACE FUNCTION partner_shared_tasks(p_lawsuit_id uuid)
RETURNS TABLE(
    id uuid,
    task_type_name text,
    scheduled_date date,
    deadline_date date,
    comments text,
    completed boolean,
    from_partner boolean,
    created_at timestamptz
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT po.id,
           tt.name,
           po.scheduled_date,
           po.deadline_date,
           po.comments,
           NOT EXISTS (
               SELECT 1 FROM post_users pu
                WHERE pu.post_id = po.id AND pu.completed_at IS NULL
           ),
           po.partner_tenant_id IS NOT NULL,
           po.created_at
    FROM posts po
    JOIN task_types tt ON tt.id = po.task_type_id
    WHERE po.lawsuit_id = p_lawsuit_id
      AND NOT po.is_private
      AND EXISTS (SELECT 1 FROM partner_share_for(p_lawsuit_id))
    ORDER BY po.created_at DESC
$$;
"""

# O parceiro escolhe o tipo de tarefa no catálogo do DONO — a tarefa nasce no tenant do
# dono, é ele quem vai executá-la. Só o par (id, nome) atravessa a fronteira.
_SHARED_TASK_TYPES = """
CREATE OR REPLACE FUNCTION partner_shared_task_types(p_lawsuit_id uuid)
RETURNS TABLE(id uuid, name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT tt.id, tt.name
    FROM task_types tt
    JOIN shared_lawsuits s ON s.lawsuit_id = p_lawsuit_id
                          AND s.owner_tenant_id = tt.tenant_id
                          AND s.partner_tenant_id = current_setting('app.tenant_id', true)::uuid
                          AND s.revoked_at IS NULL
    WHERE tt.is_active
      AND EXISTS (SELECT 1 FROM partner_share_for(p_lawsuit_id))
    ORDER BY tt.name
$$;
"""

# Único caminho de ESCRITA cross-tenant do sistema (regra 5). Levanta exceção quando o
# escopo não permite — o service traduz para 403.
_CREATE_TASK = """
CREATE OR REPLACE FUNCTION partner_create_task(
    p_lawsuit_id uuid,
    p_task_type_id uuid,
    p_author_user_id uuid,
    p_scheduled_date date,
    p_deadline_date date,
    p_comments text
)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_share record;
    v_partner_tenant uuid := current_setting('app.tenant_id', true)::uuid;
    v_reward integer;
    v_owner_user uuid;
    v_post_id uuid;
BEGIN
    SELECT * INTO v_share FROM partner_share_for(p_lawsuit_id);
    IF NOT FOUND OR NOT v_share.can_create_tasks THEN
        RAISE EXCEPTION 'partner_task_forbidden' USING ERRCODE = 'insufficient_privilege';
    END IF;

    SELECT tt.reward INTO v_reward
      FROM task_types tt
     WHERE tt.id = p_task_type_id
       AND tt.tenant_id = v_share.owner_tenant_id
       AND tt.is_active;
    IF v_reward IS NULL THEN
        RAISE EXCEPTION 'partner_task_type_invalid' USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT l.user_id INTO v_owner_user FROM lawsuits l WHERE l.id = p_lawsuit_id;

    INSERT INTO posts (tenant_id, lawsuit_id, task_type_id, created_by, scheduled_date,
                       deadline_date, comments, reward_snapshot, partner_tenant_id)
    VALUES (v_share.owner_tenant_id, p_lawsuit_id, p_task_type_id, p_author_user_id,
            p_scheduled_date, p_deadline_date, p_comments, v_reward, v_partner_tenant)
    RETURNING id INTO v_post_id;

    -- Responsável é o advogado do processo no escritório dono: a demanda do parceiro
    -- cai na caixa de entrada dele (regra 8).
    INSERT INTO post_users (tenant_id, post_id, user_id)
    VALUES (v_share.owner_tenant_id, v_post_id, v_owner_user);

    RETURN v_post_id;
END;
$$;
"""

# Aceite e encerramento tocam a linha do OUTRO lado — por isso passam por função em vez
# de política de UPDATE (uma política de UPDATE para o parceiro deixaria ele mudar
# `can_view_financial` do próprio compartilhamento).
_ACCEPT = """
CREATE OR REPLACE FUNCTION partnership_accept(p_token_hash text, p_email citext)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_tenant uuid := current_setting('app.tenant_id', true)::uuid;
    v_id uuid;
BEGIN
    UPDATE partnerships
       SET partner_tenant_id = v_tenant,
           status = 'ATIVA',
           accepted_at = now(),
           token_hash = NULL
     WHERE token_hash = p_token_hash
       AND status = 'PENDENTE'
       AND invited_email = p_email
       AND requester_tenant_id <> v_tenant
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
"""

_END = """
CREATE OR REPLACE FUNCTION partnership_end(p_partnership_id uuid)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_tenant uuid := current_setting('app.tenant_id', true)::uuid;
    v_found boolean;
BEGIN
    UPDATE partnerships
       SET status = 'ENCERRADA'
     WHERE id = p_partnership_id
       AND status IN ('ATIVA', 'PENDENTE')
       AND (requester_tenant_id = v_tenant OR partner_tenant_id = v_tenant)
    RETURNING true INTO v_found;

    IF v_found THEN
        -- Regra 7: encerrar revoga TODOS os compartilhamentos, dos dois lados.
        UPDATE shared_lawsuits
           SET revoked_at = now()
         WHERE partnership_id = p_partnership_id AND revoked_at IS NULL;
    END IF;
    RETURN coalesce(v_found, false);
END;
$$;
"""

# Regra 2: e-mail sem conta no Rito recebe convite de CADASTRO, não de parceria.
_HAS_ACCOUNT = """
CREATE OR REPLACE FUNCTION partnership_email_has_account(p_email citext)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT EXISTS (SELECT 1 FROM users WHERE email = p_email AND is_active)
$$;
"""

# Cards da regra 10, das duas pontas: "pendente pelo escritório" é o que os MEUS
# usuários devem; "pendente pelo parceiro" é o que está atribuído do outro lado.
_PENDING = """
CREATE OR REPLACE FUNCTION partner_pending_demands()
RETURNS TABLE(shared_count bigint, pending_here bigint, pending_partner bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    WITH me AS (SELECT current_setting('app.tenant_id', true)::uuid AS tenant_id),
    scope AS (
        SELECT s.lawsuit_id
        FROM shared_lawsuits s
        JOIN partnerships p ON p.id = s.partnership_id
        CROSS JOIN me
        WHERE s.revoked_at IS NULL
          AND p.status = 'ATIVA'
          AND (s.owner_tenant_id = me.tenant_id OR s.partner_tenant_id = me.tenant_id)
    ),
    open_tasks AS (
        SELECT sc.lawsuit_id, pu.tenant_id AS assignee_tenant_id
        FROM scope sc
        JOIN posts po ON po.lawsuit_id = sc.lawsuit_id
        JOIN post_users pu ON pu.post_id = po.id AND pu.completed_at IS NULL
    )
    SELECT (SELECT count(DISTINCT lawsuit_id) FROM scope),
           (SELECT count(*) FROM open_tasks, me WHERE assignee_tenant_id = me.tenant_id),
           (SELECT count(*) FROM open_tasks, me WHERE assignee_tenant_id <> me.tenant_id)
$$;
"""

_FUNCTIONS = [
    _SHARE_FOR,
    _SHARED_LIST,
    _SHARED_PARTIES,
    _SHARED_TIMELINE,
    _SHARED_TASKS,
    _SHARED_TASK_TYPES,
    _CREATE_TASK,
    _ACCEPT,
    _END,
    _HAS_ACCOUNT,
    _PENDING,
]

_DROP_FUNCTIONS = [
    "DROP FUNCTION IF EXISTS partner_pending_demands()",
    "DROP FUNCTION IF EXISTS partnership_email_has_account(citext)",
    "DROP FUNCTION IF EXISTS partnership_end(uuid)",
    "DROP FUNCTION IF EXISTS partnership_accept(text, citext)",
    "DROP FUNCTION IF EXISTS partner_create_task(uuid, uuid, uuid, date, date, text)",
    "DROP FUNCTION IF EXISTS partner_shared_task_types(uuid)",
    "DROP FUNCTION IF EXISTS partner_shared_tasks(uuid)",
    "DROP FUNCTION IF EXISTS partner_shared_timeline(uuid, integer)",
    "DROP FUNCTION IF EXISTS partner_shared_parties(uuid)",
    "DROP FUNCTION IF EXISTS partner_shared_lawsuits()",
    "DROP FUNCTION IF EXISTS partner_share_for(uuid)",
]


def upgrade() -> None:
    # O tipo nasce junto com `partnerships` (mesmo idioma da 026): `create_table` emite o
    # CREATE TYPE da coluna — criar antes à mão duplicaria o comando.
    op.create_table(
        "partnerships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "requester_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        # Nulo até o aceite — o convite existe antes de saber qual escritório é o outro.
        sa.Column(
            "partner_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("invited_email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "status", partnership_status, nullable=False, server_default=sa.text("'PENDENTE'")
        ),
        sa.Column("token_hash", sa.Text(), nullable=True, unique=True),
        sa.Column(
            "invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("requester_tenant_id", "invited_email", name="uq_partnership_invite"),
    )

    op.create_table(
        "shared_lawsuits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "partnership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partnerships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "partner_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "can_view_financial", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("can_create_tasks", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "shared_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("lawsuit_id", "partner_tenant_id", name="uq_shared_lawsuit_partner"),
    )
    op.execute(
        "CREATE INDEX ix_shared_partner ON shared_lawsuits (partner_tenant_id) "
        "WHERE revoked_at IS NULL"
    )
    op.execute("CREATE INDEX ix_shared_owner ON shared_lawsuits (owner_tenant_id, lawsuit_id)")

    # Auditoria (regra 11) — tabela de domínio normal: cada lado audita as próprias ações.
    op.create_table(
        "partnership_audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "partnership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partnerships.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("lawsuit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column(
            "detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("partnership_audit_logs"):
        op.execute(statement)

    # Origem da tarefa criada pelo parceiro (regra 8): a tarefa nasce no tenant do DONO
    # e guarda de qual escritório veio a demanda.
    op.add_column(
        "posts",
        sa.Column(
            "partner_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
    )
    op.execute(
        "CREATE INDEX ix_posts_partner ON posts (partner_tenant_id) "
        "WHERE partner_tenant_id IS NOT NULL"
    )

    for table in ("partnerships", "shared_lawsuits"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for policy in _POLICIES:
        op.execute(policy)

    for function in _FUNCTIONS:
        op.execute(function)


def downgrade() -> None:
    for statement in _DROP_FUNCTIONS:
        op.execute(statement)
    op.drop_column("posts", "partner_tenant_id")
    op.drop_table("partnership_audit_logs")
    op.drop_table("shared_lawsuits")
    op.drop_table("partnerships")
    partnership_status.drop(op.get_bind(), checkfirst=True)
