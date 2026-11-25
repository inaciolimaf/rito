# Documentação do sistema

Esta pasta explica **como o Rito funciona hoje**. Ela não conta o que foi pedido (isso é
`specs/`) nem como trabalhar no código (isso é o `CLAUDE.md`). Quem vai mexer num domínio lê o
arquivo dele aqui antes de tocar no código.

- [overview.md](overview.md): arquitetura, camadas, isolamento, configuração, erros, log, testes.
- Um arquivo por domínio, no formato abaixo. Enquanto um domínio estiver como **pendente**, a
  descrição deste índice é tudo o que ele tem aqui: o código é a fonte.

## Índice

Cada pasta exigida pelo gate `make docs` aparece nesta tabela. Estado `pendente` = ainda não há
arquivo de domínio com o formato completo.

| Pasta | O que é | Estado |
|---|---|---|
| `backend/app/domain/account/` | Conta do escritório: dados e configurações do tenant | pendente |
| `backend/app/domain/action_groups/` | Grupos de tipos de ação | pendente |
| `backend/app/domain/aggregates/` | Agregados de leitura (base dos painéis) | pendente |
| `backend/app/domain/ai/` | Configuração e uso da IA por escritório | pendente |
| `backend/app/domain/api_tokens/` | Tokens de API para integrações externas | pendente |
| `backend/app/domain/attachments/` | Anexos, guardados no storage S3/MinIO | pendente |
| `backend/app/domain/auth/` | Login, sessão, refresh e RBAC | pendente |
| `backend/app/domain/automations/` | Automações: quando X acontece, faça Y | pendente |
| `backend/app/domain/bi/` | Painéis de BI: estoque, safra, tempo e custos | pendente |
| `backend/app/domain/comments/` | Comentários em processos e tarefas | pendente |
| `backend/app/domain/courts/` | Tribunais e sistemas judiciais | pendente |
| `backend/app/domain/crm/` | Kanban de CRM por fase processual | pendente |
| `backend/app/domain/customer_origins/` | Origem dos contatos | pendente |
| `backend/app/domain/customers/` | Contatos: pessoa física e jurídica | pendente |
| `backend/app/domain/datajud/` | Domínio do DataJud: andamentos vindos do tribunal | pendente |
| `backend/app/domain/documents/` | Documentos e geração de PDF | pendente |
| `backend/app/domain/dunning/` | Cobrança e inadimplência | pendente |
| `backend/app/domain/external_requests/` | Registro de chamadas HTTP externas | pendente |
| `backend/app/domain/financial/` | Financeiro: plano de contas, contas, lançamentos e fluxo | pendente |
| `backend/app/domain/inbox/` | Caixa de entrada (Meu Painel) | pendente |
| `backend/app/domain/integration_alerts/` | Alertas de falha nas integrações | pendente |
| `backend/app/domain/integrations/` | Estado e configuração das integrações | pendente |
| `backend/app/domain/lawsuits/` | Processos: cadastro, partes, movimentações e listagem | pendente |
| `backend/app/domain/legal_agents/` | Agentes jurídicos (IA) | pendente |
| `backend/app/domain/locations/` | Localidades | pendente |
| `backend/app/domain/monitored_terms/` | Termos monitorados do DJEN | pendente |
| `backend/app/domain/notifications/` | Notificações | pendente |
| `backend/app/domain/partnerships/` | Parcerias entre escritórios | pendente |
| `backend/app/domain/posts/` | Publicações internas do escritório | pendente |
| `backend/app/domain/publications/` | Publicações do DJEN (intimações) | pendente |
| `backend/app/domain/reports/` | Relatórios tabulares | pendente |
| `backend/app/domain/schedule/` | Agenda | pendente |
| `backend/app/domain/search/` | Busca global | pendente |
| `backend/app/domain/squads/` | Times (squads) | pendente |
| `backend/app/domain/stages/` | Fases processuais | pendente |
| `backend/app/domain/taskscore/` | Taskscore: metas e ranking | pendente |
| `backend/app/domain/task_types/` | Tipos de tarefa (catálogo) | pendente |
| `backend/app/domain/templates/` | Modelos de texto e de PDF | pendente |
| `backend/app/domain/users/` | Usuários do escritório | pendente |
| `backend/app/domain/webhooks/` | Webhooks do escritório | pendente |
| `backend/app/domain/workflows/` | Fluxos de trabalho disparados ao mover no CRM | pendente |
| `backend/app/integrations/datajud/` | Cliente e parser do DataJud | pendente |
| `backend/app/integrations/djen/` | Cliente e parser do DJEN | pendente |
| `backend/app/integrations/http/` | Saída HTTP única, com registro de chamadas | pendente |
| `backend/app/integrations/messaging/` | Envio de e-mail e mensagens | pendente |
| `backend/app/integrations/ocr/` | OCR de documentos | pendente |
| `backend/app/integrations/openrouter/` | Gateway único de LLM (OpenRouter) | pendente |
| `backend/app/integrations/storage/` | Armazenamento de arquivos (S3/MinIO) | pendente |
| `backend/app/core/` | Núcleo: configuração, banco, RLS, erros, log, health, segurança e utilidades que todo módulo usa | parcial (ver overview.md) |
| `backend/app/ai/` | Grafos LangGraph, ferramentas de tool calling e prompts | pendente |
| `backend/app/public/` | API pública (`/api/public/v1`) com as mesmas regras | pendente |
| `backend/app/workers/` | Tarefas Celery e agendamentos | pendente |

Os termos do produto e os nomes que eles têm no código estão em `docs/glossary.md`.

## Regra de atualização

1. **O sistema mudou, a documentação muda no mesmo commit**: rota, tabela, fluxo, regra,
   variável de ambiente, arquivo novo, removido ou renomeado. O arquivo do domínio é atualizado
   (ou o índice, enquanto o domínio estiver pendente).
2. **Domínio novo** = pasta nova em `backend/app/...` + linha neste índice. Se ela não estiver
   aqui, `make docs` falha (DOC001).
3. **Caminho citado tem que existir.** `make docs` também falha (DOC002) se um caminho entre
   crases sumiu.
4. Divergência entre código e spec vai para o arquivo do domínio, em "Pontos de atenção". A spec
   fica como histórico.

## Formato de um arquivo de domínio

Um arquivo por domínio, entre 100 e 300 linhas, sem seções que não se aplicam:

```markdown
# <Domínio>
Um parágrafo: para que serve e a spec de origem.
## Onde está            tabela Arquivo | Papel (backend, frontend, testes)
## Dados                tabelas e a migration que as criou; arquivos em disco; cache
## Rotas                tabela Método e caminho | O que faz | Erros (tipo problem+json)
## Como funciona        fluxos principais, em ordem, com nomes de função
## Regras e garantias   cada invariante e o teste que a garante (`tests/...py::nome`)
## Configuração         variáveis de ambiente do domínio
## Pontos de atenção    armadilhas, decisões não óbvias, divergências da spec
```

Identificadores e caminhos exatamente como estão no código, entre crases e relativos à raiz do
repositório.
