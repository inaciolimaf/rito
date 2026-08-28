"""098: índice em toda chave estrangeira.

Spec 098, regra 4. A auditoria encontrou 94 chaves estrangeiras sem índice
que as cobrisse — de 228 no total.

FK sem índice custa em dois lugares que ninguém liga a ela:

1. **Toda leitura pela relação vira Seq Scan.** `WHERE lawsuit_id = $1` numa tabela de
   um milhão de movimentações lê a tabela inteira. É o custo óbvio.
2. **Todo DELETE ou UPDATE do lado PAI varre a tabela FILHA inteira**, uma vez por
   linha apagada, para checar a integridade referencial. É o custo não óbvio, e é o que
   transforma "excluir um cliente" em trinta segundos de banco travado quando o volume
   chega. O Postgres não cria esse índice sozinho — só o do lado da PK.

Os nomes seguem `ix_<tabela>_<colunas>`, o mesmo padrão dos índices já existentes.
`IF NOT EXISTS` porque parte destes índices pode ter sido criada à mão num ambiente
antes desta migration.

Revision ID: 098_fk_indexes
Revises: 097 (a 097 não teve migration — nenhuma tabela nova)
"""

from collections.abc import Sequence

from alembic import op

revision: str = "098_fk_indexes"
down_revision: str | None = "096_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nome do índice, tabela, colunas) — gerado a partir do catálogo do Postgres com a
# mesma consulta que o teste `test_toda_fk_tem_indice` usa como gate permanente.
FK_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_access_logs_user_id", "access_logs", ["user_id"]),
    ("ix_accounts_default_publications_user_id", "accounts", ["default_publications_user_id"]),
    ("ix_agent_generations_agent_id", "agent_generations", ["agent_id"]),
    ("ix_agent_generations_generated_by", "agent_generations", ["generated_by"]),
    ("ix_agent_generations_saved_template_id", "agent_generations", ["saved_template_id"]),
    ("ix_agent_generations_template_used_id", "agent_generations", ["template_used_id"]),
    ("ix_agent_generations_thread_id", "agent_generations", ["thread_id"]),
    ("ix_ai_actions_decided_by", "ai_actions", ["decided_by"]),
    ("ix_ai_actions_thread_id", "ai_actions", ["thread_id"]),
    ("ix_ai_actions_user_id", "ai_actions", ["user_id"]),
    ("ix_ai_audit_log_action_id", "ai_audit_log", ["action_id"]),
    ("ix_ai_audit_log_user_id", "ai_audit_log", ["user_id"]),
    ("ix_ai_budgets_updated_by", "ai_budgets", ["updated_by"]),
    ("ix_ai_feature_config_updated_by", "ai_feature_config", ["updated_by"]),
    ("ix_ai_insights_dismissed_by", "ai_insights", ["dismissed_by"]),
    ("ix_ai_messages_action_id", "ai_messages", ["action_id"]),
    ("ix_ai_messages_tool_call_id", "ai_messages", ["tool_call_id"]),
    ("ix_ai_sql_queries_user_id", "ai_sql_queries", ["user_id"]),
    ("ix_ai_threads_user_id", "ai_threads", ["user_id"]),
    ("ix_ai_tool_calls_user_id", "ai_tool_calls", ["user_id"]),
    ("ix_ai_usage_user_id", "ai_usage", ["user_id"]),
    ("ix_api_tokens_created_by", "api_tokens", ["created_by"]),
    ("ix_attachments_uploaded_by", "attachments", ["uploaded_by"]),
    ("ix_automation_decisions_action_id", "automation_decisions", ["action_id"]),
    ("ix_automations_created_by", "automations", ["created_by"]),
    ("ix_bank_accounts_institution_id", "bank_accounts", ["institution_id"]),
    ("ix_closure_goals_action_group_id", "closure_goals", ["action_group_id"]),
    ("ix_cnj_movement_codes_parent_code", "cnj_movement_codes", ["parent_code"]),
    ("ix_court_system_links_system_id", "court_system_links", ["system_id"]),
    ("ix_document_extractions_action_id", "document_extractions", ["action_id"]),
    ("ix_document_extractions_attachment_id", "document_extractions", ["attachment_id"]),
    ("ix_document_extractions_user_id", "document_extractions", ["user_id"]),
    ("ix_document_folders_created_by", "document_folders", ["created_by"]),
    ("ix_documents_folder_id", "documents", ["folder_id"]),
    ("ix_documents_uploaded_by", "documents", ["uploaded_by"]),
    ("ix_dunning_attempts_rule_id", "dunning_attempts", ["rule_id"]),
    ("ix_editor_ai_actions_user_id", "editor_ai_actions", ["user_id"]),
    ("ix_financial_categories_dre_group_id", "financial_categories", ["dre_group_id"]),
    ("ix_integration_alerts_resolved_by", "integration_alerts", ["resolved_by"]),
    ("ix_integration_alerts_responsible_user_id", "integration_alerts", ["responsible_user_id"]),
    ("ix_integration_alerts_tenant_id", "integration_alerts", ["tenant_id"]),
    ("ix_lawsuit_movements_created_by", "lawsuit_movements", ["created_by"]),
    ("ix_lawsuit_parties_customer_id", "lawsuit_parties", ["customer_id"]),
    ("ix_lawsuit_stage_history_changed_by", "lawsuit_stage_history", ["changed_by"]),
    ("ix_lawsuit_stage_history_from_stage_id", "lawsuit_stage_history", ["from_stage_id"]),
    ("ix_lawsuit_stage_history_to_stage_id", "lawsuit_stage_history", ["to_stage_id"]),
    ("ix_lawsuits_court_id", "lawsuits", ["court_id"]),
    ("ix_lawsuits_court_system_id", "lawsuits", ["court_system_id"]),
    ("ix_lawsuits_lawsuit_type_id", "lawsuits", ["lawsuit_type_id"]),
    ("ix_lawsuits_stage_id", "lawsuits", ["stage_id"]),
    ("ix_lawsuits_user_id", "lawsuits", ["user_id"]),
    ("ix_legal_agents_default_template_id", "legal_agents", ["default_template_id"]),
    ("ix_monitored_terms_alert_id", "monitored_terms", ["alert_id"]),
    ("ix_monitored_terms_oab_state", "monitored_terms", ["oab_state"]),
    ("ix_monitored_terms_user_id", "monitored_terms", ["user_id"]),
    ("ix_notification_rules_responsible_user_id", "notification_rules", ["responsible_user_id"]),
    ("ix_notifications_user_id", "notifications", ["user_id"]),
    ("ix_partnership_audit_logs_actor_user_id", "partnership_audit_logs", ["actor_user_id"]),
    ("ix_partnership_audit_logs_partnership_id", "partnership_audit_logs", ["partnership_id"]),
    ("ix_partnerships_invited_by", "partnerships", ["invited_by"]),
    ("ix_partnerships_partner_tenant_id", "partnerships", ["partner_tenant_id"]),
    ("ix_post_comments_author_id", "post_comments", ["author_id"]),
    ("ix_post_users_completed_by", "post_users", ["completed_by"]),
    ("ix_post_users_user_id", "post_users", ["user_id"]),
    ("ix_posts_created_by", "posts", ["created_by"]),
    ("ix_posts_task_type_id", "posts", ["task_type_id"]),
    ("ix_publication_analyses_reviewed_by", "publication_analyses", ["reviewed_by"]),
    (
        "ix_publication_analyses_suggested_task_type_id",
        "publication_analyses",
        ["suggested_task_type_id"],
    ),
    ("ix_publication_analyses_suggested_user_id", "publication_analyses", ["suggested_user_id"]),
    ("ix_publication_lawyers_publication_id", "publication_lawyers", ["publication_id"]),
    ("ix_publication_reads_user_id", "publication_reads", ["user_id"]),
    ("ix_publication_recipients_publication_id", "publication_recipients", ["publication_id"]),
    ("ix_publications_post_id", "publications", ["post_id"]),
    ("ix_publications_routed_to", "publications", ["routed_to"]),
    ("ix_shared_lawsuits_partnership_id", "shared_lawsuits", ["partnership_id"]),
    ("ix_shared_lawsuits_shared_by", "shared_lawsuits", ["shared_by"]),
    ("ix_stages_suggested_workflow_id", "stages", ["suggested_workflow_id"]),
    ("ix_task_types_step_id", "task_types", ["step_id"]),
    ("ix_templates_created_by", "templates", ["created_by"]),
    ("ix_transactions_category_id", "transactions", ["category_id"]),
    ("ix_transactions_cost_center_id", "transactions", ["cost_center_id"]),
    ("ix_transactions_credit_account_id", "transactions", ["credit_account_id"]),
    ("ix_transactions_customer_id", "transactions", ["customer_id"]),
    ("ix_transactions_debit_account_id", "transactions", ["debit_account_id"]),
    ("ix_transactions_user_id", "transactions", ["user_id"]),
    ("ix_user_invitations_occupation_id", "user_invitations", ["occupation_id"]),
    ("ix_user_notification_preferences_user_id", "user_notification_preferences", ["user_id"]),
    ("ix_webhook_deliveries_run_id", "webhook_deliveries", ["run_id"]),
    ("ix_workflow_applications_applied_by", "workflow_applications", ["applied_by"]),
    ("ix_workflow_applications_stage_id", "workflow_applications", ["stage_id"]),
    ("ix_workflow_applications_workflow_id", "workflow_applications", ["workflow_id"]),
    ("ix_workflow_steps_task_type_id", "workflow_steps", ["task_type_id"]),
    ("ix_workflow_steps_user_id", "workflow_steps", ["user_id"]),
    ("ix_workflow_suppressions_stage_id", "workflow_suppressions", ["stage_id"]),
]


def upgrade() -> None:
    for nome, tabela, colunas in FK_INDEXES:
        op.execute(f'CREATE INDEX IF NOT EXISTS {nome} ON "{tabela}" ({", ".join(colunas)})')


def downgrade() -> None:
    for nome, _tabela, _colunas in FK_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {nome}")
