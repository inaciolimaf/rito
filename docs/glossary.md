# Glossário

Termo do produto (em português, como o usuário o vê) → nome no código (em inglês). Todo nome de
domínio sai daqui. Um termo novo entra na mesma alteração que o introduz.

## Convenções de nome

- Python: `snake_case` para funções e módulos; `PascalCase` para classes.
- Pastas de domínio: plural `snake_case` (`lawsuits`, `customer_origins`).
- Tabelas: plural `snake_case`; colunas `snake_case`.
- Rotas HTTP: plural `kebab-case`, sem verbo (`/api/v1/lawsuits`).
- Código, comentários, identificadores, nomes de arquivo, tipos de erro (`domínio/motivo`) e
  documentação: inglês.

## O que continua em português

- Textos da interface (rótulos, mensagens, estados vazios).
- `detail` dos erros `problem+json` (o que o usuário lê).
- PDFs, e-mails e modelos de documento.
- Prompts enviados ao LLM quando tratam de documentos em português.
- Caminhos das telas do frontend, se o usuário os vê e compartilha.

## Termos

| Termo no produto | Código | Pasta ou módulo |
|---|---|---|
| Escritório | tenant | `tenant_id` em todas as tabelas de domínio |
| Usuário | user | `backend/app/domain/users/` |
| Processo | lawsuit | `backend/app/domain/lawsuits/` |
| Contato (pessoa física ou jurídica) | customer | `backend/app/domain/customers/` |
| Origem do contato | customer origin | `backend/app/domain/customer_origins/` |
| Tribunal | court | `backend/app/domain/courts/` |
| Publicação / intimação (DJEN) | publication | `backend/app/domain/publications/` |
| Termo monitorado | monitored term | `backend/app/domain/monitored_terms/` |
| Andamento do DataJud | datajud | `backend/app/domain/datajud/`, `backend/app/integrations/datajud/` |
| Fase processual | stage | `backend/app/domain/stages/` |
| CRM (kanban) | crm | `backend/app/domain/crm/` |
| Fluxo de trabalho | workflow | `backend/app/domain/workflows/` |
| Tipo de tarefa | task type | `backend/app/domain/task_types/` |
| Grupo de tipos de ação | action group | `backend/app/domain/action_groups/` |
| Taskscore (metas e ranking) | taskscore | `backend/app/domain/taskscore/` |
| Caixa de entrada (Meu Painel) | inbox | `backend/app/domain/inbox/` |
| Agenda | schedule | `backend/app/domain/schedule/` |
| Time | squad | `backend/app/domain/squads/` |
| Parceiro (escritório parceiro) | partnership | `backend/app/domain/partnerships/` |
| Modelo (texto ou PDF) | template | `backend/app/domain/templates/` |
| Documento gerado | document | `backend/app/domain/documents/` |
| Automação | automation | `backend/app/domain/automations/` |
| Financeiro | financial | `backend/app/domain/financial/` |
| Cobrança e inadimplência | dunning | `backend/app/domain/dunning/` |
| Relatório | report | `backend/app/domain/reports/` |
| BI (painéis) | bi | `backend/app/domain/bi/` |
| Busca | search | `backend/app/domain/search/` |
| Notificação | notification | `backend/app/domain/notifications/` |
| Comentário | comment | `backend/app/domain/comments/` |
| Anexo | attachment | `backend/app/domain/attachments/` |
| Webhook | webhook | `backend/app/domain/webhooks/` |
| Token de API | api token | `backend/app/domain/api_tokens/` |
| Agente jurídico (IA) | legal agent | `backend/app/domain/legal_agents/` |
| Localidade | location | `backend/app/domain/locations/` |
| Alerta de integração | integration alert | `backend/app/domain/integration_alerts/` |
| Chamada externa registrada | external request | `backend/app/domain/external_requests/` |
