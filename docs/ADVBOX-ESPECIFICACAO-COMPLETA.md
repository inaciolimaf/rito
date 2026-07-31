# ADVBOX — Especificação Completa para Replicação

> Levantamento feito em 29/07/2026 via Playwright, cobrindo: site institucional (advbox.com.br), documentação oficial da API (api.softwareadvbox.com.br), Central de Ajuda (guia.advbox.com.br — 112 artigos) e **o app real logado** (app.advbox.com.br, conta trial).
>
> **Nota sobre cobertura:** a conta usada é um trial de 7 dias no nível Essencial/CRM. Módulos exclusivos dos planos superiores (Business Intelligence: Estoque e Prospecção, Safra e Qualidade, Tempo e Honorários, Custos; Contingenciamento; Setores/Unidades) não puderam ser abertos na interface — estão documentados aqui a partir da Central de Ajuda e da matriz de planos, e estão marcados como `[não verificado na UI]`.

---

## Sumário

1. [Arquitetura de navegação do app](#1-arquitetura-de-navegação-do-app)
2. [Modelo de dados e formulários (campo a campo)](#2-modelo-de-dados-e-formulários-campo-a-campo)
3. [Taxonomias e listas padrão do sistema](#3-taxonomias-e-listas-padrão-do-sistema)
4. [Módulos e funcionalidades](#4-módulos-e-funcionalidades)
5. [Integrações](#5-integrações)
6. [API REST — 22 endpoints](#6-api-rest--22-endpoints)
7. [Inteligência Artificial (21 agentes)](#7-inteligência-artificial-21-agentes)
8. [Flowter — motor de automação](#8-flowter--motor-de-automação)
9. [Monitoramento de intimações](#9-monitoramento-de-intimações-termos-monitorados)
10. [Planos e matriz completa de funcionalidades](#10-planos-e-matriz-completa-de-funcionalidades)
11. [Roteiro de replicação](#11-roteiro-de-replicação)

---

## 1. Arquitetura de navegação do app

**Base:** `https://app.advbox.com.br`

### Menu lateral principal

| # | Item | Rota | Função |
|---|------|------|--------|
| 1 | Meu Painel | `/home` | Dashboard pessoal + caixa de entrada de tarefas |
| 2 | Agenda | `/schedules` | Calendário (mês/semana/dia/agenda) |
| 3 | Atividades | `/posts` | Lista global de tarefas |
| 4 | CRM | `/crm` | Kanban por fase processual |
| 5 | Contatos | `/customers` | Clientes e partes contrárias |
| 6 | Processos | `/lawsuits` | Processos judiciais/administrativos |
| 7 | Intimações | `/publications` | Publicações capturadas |
| 8 | Parceiros | `/friendship` | Rede de escritórios parceiros |
| 9 | Modelos | `/library` | Editor de documentos e templates |
| 10 | Financeiro | `/transactions` | Lançamentos, contas, fluxo de caixa |
| 11 | Relatórios | `/management` | Gestão / BI |
| 12 | Configurações | `/settings` | 16 sub-seções |
| 13 | Conta e assinatura | `/subscription` | Dados, plano, IA, produtos |
| 14 | Suporte | modal | Chat / chamado |
| 15 | Indicar a ADVBOX | modal | Programa de indicação |

### Sub-abas de "Meu Painel" (`/home`)
`Visão Geral` (overview) · `Lista` (list) · `Quadro` (board) · `Desempenho` (analytics) · `Configurações` (settings?page=inbox)

### Sub-seções de Configurações (`/settings?page=<slug>`)

| Slug | Seção | Conteúdo |
|------|-------|----------|
| `users` | Usuários | Abas **Colaboradores** e **Times**; toggle "Habilitar registro de acessos" |
| `bots` | Inteligência Artificial | Catálogo dos 21 agentes + config da Justin-e |
| `terms` | Termos monitorados | OAB/CPF/CNPJ monitorados + certificado A1 |
| `financial` | Financeiro | Abas **Contas e cartões**, **Categorias**, **Centros de custos** |
| `tasks` | Tarefas | Catálogo de tarefas + pontuação Taskscore |
| `workflow` | Workflow | Sequências automáticas de tarefas |
| `groups` | Grupos de ação | Áreas do direito + responsável por intimações |
| `typeLawsuits` | Tipos de ação | Tipos vinculados a grupos |
| `stages` | Etapas | Etapas do funil + regra de estagnação |
| `goals` | Metas | Meta mensal de fechamentos por grupo de ação |
| `origins` | Origem de pessoas | Origens de lead |
| `partners` | Parceiros | Escritórios parceiros |
| `inbox` | Caixa de entrada | Ordem das seções da inbox |
| `receiveNotifications` | Notificações | Responsável por cada tipo de alerta |
| `integrations` | Integrações e API | 14 integrações |
| `rdstation` | RD Station Marketing | Token e webhooks |

### Detalhe técnico da SPA (útil para clonar o comportamento)
- Páginas são shells; o conteúdo vem por AJAX de `GET /content/<slug>` com header `X-Requested-With: XMLHttpRequest` **e `Referer` da página correspondente** (sem o Referer correto retorna 404).
- Modais de criação/edição vêm de `GET /<entidade>/create?data=` e `GET /<entidade>/<id>/edit?data=`.
- Listagens usam **DataTables** server-side: `GET /content/<entidade>?sEcho=&iColumns=&sColumns=&iDisplayStart=&iDisplayLength=&...&_token=<CSRF>`.
- Botão "Adicionar" global no header: Nova tarefa · Novo contato · Novo processo · Nova receita/despesa.
- Busca global no topo (atalho `/`), com facetas: **Tudo · Pessoas · Processos**.
- Paginação padrão: 50/100/200/500/1.000/2.000/3.000/4.000/5.000 registros por página.
- Toda listagem tem: Buscar · Filtrar · Ordenar · Exportar (**Excel .xlsx** e **Imprimir .pdf**).

---

## 2. Modelo de dados e formulários (campo a campo)

### 2.1 Contato / Cliente (`customers`)

Modal **"Criar novo contato"**. Alterna entre **Pessoa física** e **Pessoa jurídica** (radio `type`).

| Campo (name) | Tipo | Label | Máscara/Validação | Obrig. |
|---|---|---|---|---|
| `image` | file | Foto do cliente | — | Não |
| `identification` | text | CPF/CNPJ | `999.999.999-99` — validação real de CPF/CNPJ, bloqueia duplicidade | Não |
| `name` | text | Nome | Nome completo | **Sim** |
| `customers_origins_id` | select | Origem da pessoa | lista de origens | **Sim** |
| `notes` | textarea | Anotações gerais | "Anotações, senhas e outros" | Não |
| `type` | radio | Pessoa física / Pessoa jurídica | — | Sim |
| `country` | select | País | ~250 países, default BRASIL | Não |
| `document` | text | RG | Número | Não |
| `birthdate` | text | Data de nascimento | `DD/MM/AAAA` | Não |
| `maritalstatus_id` | select | Estado civil | CASADO(A), DIVORCIADO(A), SEPARADO(A), SOLTEIRO(A), UNIÃO ESTÁVEL, VIÚVO(A) | Não |
| `occupation` | text | Profissão | — | Não |
| `gender` | select | Sexo | Feminino, Masculino | Não |
| `nationality` | text | Nacionalidade | — | Não |
| `cellphone` | text | Celular | `(99) 99999-9999` | Não |
| `phone` | text | Telefone | `(99) 99999-9999` | Não |
| `email` | text | E-mail | validado, permite duplicidade | Não |
| `postalcode` | text | CEP | `99999-999` (hífen obrigatório na API) | Não |
| `state` | select | Estado | 27 UFs | Não |
| `city` | select | Cidade | dependente do estado | Não |
| `street` | text | Endereço | "Rua Exemplo, 123" | Não |
| `region` | text | Bairro | — | Não |
| `number_pis` | text | PIS/PASEP | `999.9999.999-9` | Não |
| `number_ctps` | text | CTPS | — | Não |
| `number_cid` | text | CID | — | Não |
| `mother` | text | Nome da mãe | — | Não |
| `representative` | checkbox | Adicionar representante | abre bloco abaixo | Não |

**Bloco Representante** (quando `representative` = true):
`rep_name` (obrig.), `rep_identification` (CPF/CNPJ), `rep_document` (RG), `rep_birthdate`, `rep_country`, `rep_state`, `rep_city`, `rep_street`, `rep_region`, `rep_postalcode`.

**Filtros da listagem de Contatos:** `type` (Clientes / Partes contrárias / Com processos em andamento / Sem processos em andamento / Aniversariantes do dia / Aniversariantes do mês), `state`, `city`, `customer_origin_id[]`, `partner_id`, `date_from`/`date_until` (período de cadastro), `archive`.

**Dashboard de Contatos:** Contatos cadastrados (com % vs mês anterior) · Com processo ativo · Sem processo ativo · gráficos **Top Origens**, **Faixa etária**, **Top Profissões**.

**Colunas da lista:** Nome do cliente · Celular (link direto para WhatsApp Web) · Cidade · Data do cadastro.

---

### 2.2 Processo (`lawsuits`)

Modal **"Criar novo processo"**.

| Campo (name) | Tipo | Label | Observação | Obrig. |
|---|---|---|---|---|
| `customer_list[]` | multiselect | Adicionar partes envolvidas | clientes do escritório | **Sim** |
| `contrary_list[]` | multiselect | Partes contrárias | — | Não |
| `users_id` | select | Responsável | usuários do escritório | **Sim** |
| `notes` | textarea | Anotações gerais | "Anotações, tags, fatos e fundamentos" | Não |
| `groups_id` | select | Grupo de ação | área do direito | **Sim** |
| `type_lawsuits_id` | select | Tipo de ação | filtrado pelo grupo | **Sim** |
| `steps_id` | select | Fase | 9 fases fixas | **Sim** |
| `stages_id` | select | Etapa | filtrada pela fase | **Sim** |
| `process_number` | text | Número do processo (CNJ) | `9999999-99.9999.9.99.9999` — a API valida se o CNJ existe de fato | Não |
| `year` | text | Ano do ajuizamento | `9999` | Não |
| `judiciary` | text | Segmento do Judiciário | — | Não |
| `county` | text | Comarca | — | Não |
| `stick` | text | Vara | — | Não |
| `courts_id` | select | Tribunal | 182 tribunais | Não |
| `systems_id` | select | Sistema processual | 13 sistemas | Não |
| `protocol_number` | text | Número do protocolo/requerimento | `123456789-0` | Não |
| `originating_process` | text | Processo originário | formato CNJ | Não |
| `folder` | text | Pasta/Caso | máx. 30 caracteres (API) | Não |
| `date` | text | Data do requerimento | `DD/MM/AAAA` | Não |
| `fees_expec` | text | Valor da causa | `999.999,99` | Não |
| `fees_money` | text | Valor dos honorários | `999.999,99` | Não |
| `fees_percentage` | text | Percentual de honorários | `99%` | Não |
| `contingency` | select | Contingenciamento | PROVÁVEL/CHANCE ALTA · POSSÍVEL/TALVEZ · REMOTA/DIFÍCIL | Não |
| `account_list[]` | multiselect | Contas vinculadas | — | Não |
| `file[]` | file | Anexos (nuvem do processo) | pastas + upload | Não |

**Campos derivados automaticamente (não enviar):** `group_id`/`group` (de `type_lawsuits_id`), `steps_id`/`step` (de `stages_id`).

**Campos adicionais no registro (via API):** `status_closure` (data de fechamento), `exit_production` (trânsito em julgado), `exit_execution` (arquivamento), `created_at`.

**Visões rápidas da lista (`captured`):** Todos os processos · Processos ativos · Movimentados nos últimos 30 dias · nos últimos 7 dias · hoje · Nunca capturados · Não movimentados há +30 dias · +45 dias · +90 dias · Fechamentos no mês · Processos ajuizados no mês · Processos arquivados no mês.

**Filtros avançados:** `customer`, `customer_type` (PF/PJ), `groups_id[]`, `type_lawsuits_id[]`, `steps_id[]`, `stages_id[]`, `courts_id[]`, `systems_id`, `partner_id`, `users_id[]`, `contingency`, `customer_origin_id[]`, período de cadastro, e toggles de exibição na timeline: `show_transactions`, `show_tasks`, `show_publications`, `show_manual_movements`, `show_auto_movements`, `archive`.

**Dashboard de Processos:** Processos ativos · Fechamentos (com variação) · Arquivados este mês · gráfico **Volume por fase** · **Meta de fechamentos**.

**Colunas da lista:** Partes · Tipo de ação · Número do processo · Data cadastro · Último andamento · Data andamento.

---

### 2.3 Tarefa (`posts`)

Modal **"Criar nova tarefa"**. É a entidade central do sistema (tarefa, compromisso, intimação e comentário são todos `posts`).

| Campo (name) | Tipo | Label | Observação | Obrig. |
|---|---|---|---|---|
| `lawsuits_id` | select | Processo ou caso | busca por nome do cliente ou nº do processo | **Sim** |
| `user` | multiselect | Adicionar responsáveis | "Quem vai trabalhar nesta tarefa?" | **Sim** |
| `squad` | select | Selecionar time | atribuição a um time inteiro | Não |
| `tasks_id` | select | Tarefa | "O que essa pessoa irá fazer?" — catálogo com pontuação | **Sim** |
| `workflow` | select | Selecionar workflow | dispara sequência automática | Não |
| `stages_id` | select | Alteração de Etapa processual | move o processo ao concluir | Não |
| `send_sms` | checkbox | Notificar cliente por SMS | — | Não |
| `send_email` | checkbox | Notificar cliente por E-mail | — | Não |
| `date` | text | Data | `__/__/____` | Não |
| `hour` | text | Hora | `__:__` | Não |
| `date_deadline` | text | Prazo fatal | `__/__/____` | Não |
| `display_schedule` | checkbox | Mostrar na agenda | — | Não |
| `toggle_end` | checkbox | Informar término | libera `date_end`/`hour_end` | Não |
| `all_day` | checkbox | Dia inteiro | — | Não |
| `date_end` / `hour_end` | text | Término | — | Não |
| `local` | text | Local | "Local do evento" | Não |
| `comments` | textarea | Descrição | suporta `@menções` | Não |
| `file[]` | file | Anexos | múltiplos | Não |
| `important` | checkbox | Importante | flag | Não |
| `urgent` | checkbox | Urgente | flag | Não |
| `display_date` | checkbox | Futura | oculta até a data | Não |
| `is_recurring` | checkbox | Recorrente | libera os 2 campos abaixo | Não |
| `recurrence` | select | Periodicidade | Diária · Semanal · Quinzenal · Mensal · Bimestral · Trimestral · Semestral · Anual | Não |
| `repeat_on_week` | select | Repetir em | No dia exato · 1ª/2ª/3ª/última semana do mês | Não |
| `private` | checkbox | Privada | visível só aos envolvidos | Não |
| `retroactive` | checkbox | Retroativa | libera `date_completed` | Não |
| `date_completed` | text | Conclusão | para lançamento retroativo | Não |

**Caixa de entrada (`/home` → Lista):** agrupada em seções configuráveis — **Prazo fatal · Intimações · Não lidas · Urgentes · Importantes · Todas as demais**.
Colunas: checkbox de conclusão · favorito (★) · prioridade (!) · status (●) · Tarefa · Partes · Data compromisso · Prazo fatal · Responsáveis (avatares).
Ações por linha: Abrir/Responder · Ver cliente · Imprimir · Histórico do processo · Nova tarefa no mesmo processo.

**Filtros de Atividades:** `column` (Data do compromisso / Prazo fatal / Data de conclusão / Data de criação), período, `tasks_id`, `page` (Tarefas / Pauta de audiência), `sender` (Que eu recebi / Que eu enviei), `completed` (Pendentes/Concluídas), `steps_id`, `groups_id[]`, `type_lawsuits_id[]`, `priority[]`, `future`.

---

### 2.4 Lançamento financeiro (`transactions`)

Modal **"Novo lançamento"**.

| Campo (name) | Tipo | Label | Observação | Obrig. |
|---|---|---|---|---|
| `type` | select | Tipo | **DESPESA · RECEITA · TRANSFERÊNCIA** | **Sim** |
| `debit_account_transfer` | select | Saiu da conta | só em TRANSFERÊNCIA | cond. |
| `credit_account` | select | Entrou na conta | só em TRANSFERÊNCIA | cond. |
| `debit_account` | select | Conta/cartão | contas + cartões cadastrados | **Sim** |
| `cost_centers_id` | select | Centro de custo | — | **Sim** |
| `categories_expense` | select | Categoria (despesa) | plano de contas de despesa | cond. |
| `categories_revenue` | select | Categoria (receita) | plano de contas de receita | cond. |
| `customers_id` | select | Pessoa | cliente vinculado | Não |
| `lawsuits_id` | select | Processo | exige `customers_id` junto (API) | Não |
| `description` | text | Descrição | "Identificação da cobrança" — convertida para MAIÚSCULAS | Não |
| `amount` | text | Valor | `999,99` — vírgula decimal | **Sim** |
| `date_due` | text | Vencimento | `DD/MM/AAAA` | **Sim** |
| `competence` | text | Competência | `DD/MM/AAAA` — derivada de `date_due` na API | **Sim** |
| `date_payment` | text | Pagamento | não pode ser futura | Não |
| `is_internal` | checkbox | Apenas registro interno | não afeta saldo bancário | Não |
| `is_recurrent` | checkbox | Recorrente | + `date_cycle` | Não |
| `installment` | checkbox | Parcelado | + `number_of_installments` (2 a 100) | Não |
| `enable_ticket` | checkbox | Gerar cobrança no boleto ou cartão | requer conta Asaas | Não |
| `billing_type` | select | Forma | Boleto · Cartão de crédito | cond. |
| `file[]` | file | Anexar arquivo | — | Não |

**Regra crítica:** `entry_type` deve casar com o tipo da categoria — `income` só aceita categorias de CRÉDITO, `expense` só aceita DÉBITO.

**Dashboard Financeiro:** Saldo (vs mês anterior) · Receita mensal prevista vs realizada · Despesa mensal prevista vs realizada · Pagamentos atrasados · gráfico **Receitas x Despesas por vencimento** · cards de saldo por conta bancária.

**Regimes de visualização (`regime`):** Data de pagamento · Data de vencimento · Data de competência · **Fluxo de caixa**.

**Filtros:** `bank`, `cost_center[]`, `groups[]` (grupo DRE), `type`, `customer`, `categories_id[]`, `status` (Atrasados / Futuros / Pendentes / Pagos-Recebidos / Receita mensal prevista / Despesa mensal prevista), período, `internal`, `archive`.

**Colunas:** Vencimento · Pagamento · Competência · Lançamento · Categoria · Valor. Rodapé com **total do período · saldo · previsto**.

---

### 2.5 Usuário (`users`)

**Criação** (`users/create`) — envia e-mail para o usuário concluir o cadastro:
`name` (obrig.), `email` (obrig.), `role` (Gestor / Administrador / Colaborador), `occupations_id` (66 cargos), `financial` (Sem acesso / Apenas visualização / Acesso completo).

**Edição completa** (`users/<id>/edit`):

| Campo | Tipo | Observação |
|---|---|---|
| `image` | file | Foto do perfil |
| `name` | text | obrigatório |
| `identification` | text | CPF `999.999.999-99` |
| `document` | text | RG |
| `birthdate` | text | `DD/MM/AAAA` |
| `number_ctps` | text | CTPS |
| `number_oab` | text | **OAB/UF** — usado no monitoramento |
| `cellphone`, `phone` | text | — |
| `email` | text | obrigatório |
| `password` / `password_confirmation` | password | mín. 8 caracteres, 1 número, 1 minúscula, 1 maiúscula, 1 especial |
| `occupations_id` | select | Cargo (66 opções) |
| `role` | select | Perfil: Gestor · Administrador · Colaborador |
| `financial` | select | Sem acesso · Somente visualizador · Acesso completo |
| `salary` | text | `9.999,99` |
| `admission` / `resignation` | text | datas |
| `work_start` / `work_interval` / `work_end` | text | jornada `00:00` — base do **livro de ponto** |
| `report_deadline` | checkbox | recebe relatório de prazos |
| `report_deleted` | checkbox | recebe relatório de exclusões |
| `is_responsible` | checkbox | responsável padrão |
| `is_active` | checkbox | ativo/inativo |
| `certified` + `certified_name` + `password` | file/text/password | **Certificado digital A1** (.pfx/.p12) |
| (meta de pontos) | number | meta mensal de Taskscore |

**Time / Squad** (`squads/create`): `name` (obrig.) + `user_id[]` (checkboxes de colaboradores).

---

### 2.6 Entidades de configuração

| Entidade | Rota | Campos |
|---|---|---|
| **Grupo de ação** | `groups/create` | `group` (obrig.) · `users_id` (responsável pelas intimações do grupo) |
| **Tipo de ação** | `typeLawsuits/create` | `type` (obrig.) · `groups_id` (obrig.) · função "Transferir tipos de ação" |
| **Etapa** | `stages/create` | `stage` (obrig.) · `steps_id` (fase, obrig.) · `workflows_id` ("CRM - Sugerir workflow ao mover processo") · `enable_stagnant_days` · `stagnant_days` (nº de dias p/ marcar estagnado) · "Transferir etapas" |
| **Tarefa (catálogo)** | `tasks/create` | `task` (obrig.) · `steps_id` (fase, ou TODAS) · `complexity` (Simples/Média/Média alta/Alta/Altíssima) · `time` (8 min/15 min/30 min/1 h/+2 h) · `reward` (pontos — **calculado automaticamente a partir de complexidade × tempo**, editável) · `schedule` (mostrar na agenda geral) |
| **Workflow** | `workflows/create` | `name` (obrig.) + N etapas, cada uma com: `fake_task` (tarefa, obrig.) · `fake_user` (responsável, opcional) · `fake_days` (prazo em dias úteis, opcional) |
| **Origem de pessoas** | `origins/create` | `origin` (obrig.) · "Transferir origem" |
| **Centro de custo** | `cost_centers/create` | `cost_center` (obrig.) |
| **Categoria financeira** | `categories/create` | `category` (obrig.) · `type` (DESPESA/RECEITA) · `indexes_id` (grupo DRE, obrig.) |
| **Conta / Cartão** | `bank_accounts/create` | `type` (CORRENTE·POUPANÇA·INVESTIMENTO·CARTÃO DE CRÉDITO·OUTRO) · `name` (obrig.) · `institutions_id` (~95 instituições) · `agency` · `number` · `cycle_day` (fechamento 1-31) · `due_day` (vencimento 1-31) · `initial_amount` · `default` |
| **Parceiro** | `partners/create` | `email` do parceiro → busca e retorna Razão social, Nome fantasia, CPF/CNPJ, E-mail principal → "Convidar parceiro" |
| **Metas** | `settings?page=goals` | `goal[]` — meta mensal de fechamentos **por grupo de ação** |
| **Notificações** | `settings?page=receiveNotifications` | `user[]` por evento: Novo cliente cadastrado · Novo processo cadastrado · Compartilhamentos e Parceiros · Intimações Judiciais (opção "Não notificar") |
| **Caixa de entrada** | `settings?page=inbox` | `orders` — ordem das seções |

### 2.7 Dados do escritório (`account?tab=0`)

`image` (logotipo) · `name` (Razão social, obrig.) · `alternatename` (Nome fantasia, obrig.) · `country` · `city` (obrig.) · `state` (obrig.) · `identification` (CPF/CNPJ, obrig.) · `cellphone` (obrig.) · `phone` (obrig.) · `postalcode` (obrig.) · `street` (obrig.) · `region` (obrig.) · `email` (principal, obrig.) · `email_admin` (financeiro, obrig.) · `site` · `timezone` (8 opções: Brasil Brasília/Fernando de Noronha/Belém/Manaus/Rio Branco; Portugal Continental/Madeira/Açores) · `terms`.

**Checkout:** `plans_id` (radio: Essencial / Banca jurídica / Banca max / Elite) · `number_installments` da taxa de ativação (À vista / 2x / 3x) · `type` (Pix / Cartão de crédito) · `card_number`, `card_name`, `card_expiration`, `card_code` · `auth_agreement`.

---

## 3. Taxonomias e listas padrão do sistema

### 3.1 Fases do processo (`steps`) — 9, fixas
`Marketing` · `Negociação` · `Consultoria` · `Administrativo` · `Judicial` · `Recursal` · `Execução/cobrança` · `Rh/financeiro` · `Arquivamento`

### 3.2 Etapas padrão (`stages`) — 59
ANÁLISE DO CASO · AGUARDANDO DOCUMENTOS · APRESENTAÇÃO DE PROPOSTA · AGENDAR CONSULTA · COBRANÇA INICIAL · DEFINIÇÃO DE INTERESSES · ELABORAÇÃO DE PARECER JURÍDICO · FECHAMENTO · PLANEJAMENTO · AGENDADO ATENDIMENTO NO ÓRGÃO · REQUERIMENTO PROTOCOLADO · ATENDENDO EXIGÊNCIAS · AGUARDANDO DECISÃO DO ÓRGÃO · DECISÃO PROFERIDA · RECURSO ADMINISTRATIVO PROTOCOLADO · AGUARDANDO DECISÃO DO RECURSO · DECISÃO DO RECURSO PROFERIDA · AGUARDANDO CÓPIA DO PROCESSO ADMINISTRATIVO · DESENVOLVENDO INICIAL DE AÇÃO JUDICIAL · AÇÃO PROTOCOLADA/INICIADA · COM JUIZ(A) PARA ANÁLISE · AGUARDANDO MANIFESTAÇÃO DA PARTE CONTRÁRIA · AGUARDANDO AUDIÊNCIA · AGUARDANDO JULGAMENTO · SENTENÇA PROFERIDA · TRANSITO EM JULGADO/PROCESSO FINALIZADO · DESENVOLVENDO RECURSO · RECURSO PROTOCOLADO/INICIADO · APRESENTADA RESPOSTA A RECURSO DA PARTE CONTRÁRIA (CONTRARRAZÕES) · AGUARDANDO JULGAMENTO DO RECURSO · RECURSO JULGADO · TRANSITO EM JULGADO/NÃO CABE MAIS RECURSO · DESENVOLVENDO RECURSO AOS TRIBUNAIS SUPERIORES · ELABORAÇÃO DE CÁLCULO · CITAÇÃO DO DEVEDOR PARA PAGAMENTO · AGUARDANDO PENHORA · AGUARDANDO JULGAMENTO DA EXECUÇÃO · EXECUÇÃO JULGADA · APRESENTADO RECURSO · RESPOSTA A RECURSO · AGUARDANDO SENTENÇA DE LIQUIDAÇÃO · AGUARDANDO DECISÃO DO TRIBUNAL · RPV EMITIDO · AGUARDANDO PAGAMENTO DE CONDENAÇÃO · ELABORAÇÃO DE CONTRATO · ELABORAÇÃO DE PARECER · ENVIADA NOTIFICAÇÃO EXTRAJUDICIAL · ELABORAÇÃO DE TERMO DE ACORDO · AGENDADA REUNIÃO DE COMPOSIÇÃO DE ACORDO · PROCESSO RH PENDENTE · ANALISADO E NÃO DISTRIBUÍDO · ARQUIVADO POR DESINTERESSE CLIENTE · ARQUIVADO POR DETERMINAÇÃO JUDICIAL · ARQUIVADO/ENCERRADO · ANÁLISE DE RESULTADOS · PLANEJAMENTO · PRODUÇÃO · PROMOÇÃO · RELACIONAMENTO

> Etapas com sufixo "(ENTRE EM CONTATO CONOSCO)" são gatilhos sugeridos de comunicação com o cliente.

### 3.3 Grupos de ação padrão — 6
ADMINISTRATIVO · CÍVEL · FINANCEIRO/RH · PENAL · PREVIDENCIÁRIO · TRABALHISTA

### 3.4 Tipos de ação padrão — 10 (exemplos da conta demo)
ACUSAÇÃO DE ESTELIONATO · ADMISSÃO DE FUNCIONÁRIO · APOSENTADORIA POR IDADE · CONCESSÃO DE FÉRIAS · CONCESSÃO DE FOLGA · DEMISSÃO DE FUNCIONÁRIO · JUSTIFICAÇÃO DE FALTA · NULIDADE DE LICITAÇÃO · RECLAMATÓRIA TRABALHISTA · REINTEGRAÇÃO DE POSSE

### 3.5 Origens de pessoas padrão — 8
ANÚNCIO · ESCRITÓRIO · FACEBOOK · GOOGLE · INDICAÇÃO · INSTAGRAM · PARTE CONTRÁRIA · SITE DO ESCRITÓRIO

### 3.6 Sistemas processuais — 13
APOLO · CRETA · e-JUR-TRF1 · EPROC · ESAJ · FÍSICO · i-STJ · PJD/JURIS-TRF1 e-STF · PJE · PROJUDI · SEEU · THEMIS/RS · TUCUJURIS/AP

### 3.7 Tribunais — 182 códigos
Cobertura completa: CNJ · Justiça Federal (JFAC…JFTO, 27) · Superiores (STF, STJ, STM, TSE, TST) · Tribunais de Alçada (TACMG, TACPR, TACRIMSP, TACSP1, TACSP2) · Tribunais de Contas (TCU + 34 estaduais/municipais) · Tribunais de Justiça (TJAC…TJTO, incluindo variantes PROJUDI/ESAJ/EPROC) · TREs (27) · TRFs (1 a 6) · TRTs (1 a 24).

### 3.8 Catálogo de tarefas padrão — 152 + 3 sistêmicas
**Sistêmicas:** `Intimações Judiciais` · `Pauta de audiências` · `RECADO/RESPOSTAS`

**Catálogo (152):** 1º CONTATO COM O LEAD · ABERTURA DE DIT PERANTE A FAZENDA ESTADUAL · ACOMPANHAR CITAÇÃO · ACOMPANHAR DECISÃO/ACÓRDÃO · ACOMPANHAR DECISÃO/DESPACHO · ACOMPANHAR PAGAMENTO · ACOMPANHAR PERÍCIA · ACOMPANHAR TRÂNSITO EM JULGADO · AGRAVO DE INSTRUMENTO · AGRAVO INTERNO · AGUARDANDO DOCUMENTOS CLIENTE · AGUARDANDO DOCUMENTOS PARCEIRO · ALEGAÇÕES FINAIS COMPLEXAS · ALEGAÇÕES FINAIS SIMPLES · ANÁLISE DE CASO DO PARCEIRO · ANÁLISE DE PROPOSTA DE ACORDO · ANÁLISE DE PROPOSTA DE ACORDO COMPLEXA · ANÁLISE DO CASO · ARQUIVAR - AGUARDA PAGAMENTO CUSTAS OU HONORÁRIOS · ARQUIVAR - CASO ANALISADO E NÃO DISTRIBUÍDO · ARQUIVAR POR DESINTERESSE DO CLIENTE · ARQUIVAR POR DETERMINAÇÃO JUDICIAL · ATENDER NOVA DEMANDA DO PARCEIRO · ATENDER NOVO CLIENTE · ATENDIMENTO AO CLIENTE - EXTERNO · ATENDIMENTO AO CLIENTE - INTERNO · ATRIBUIR E-MAIL/NOTA DE EXPEDIENTE E TAREFA · AUDIÊNCIA DE CONCILIAÇÃO · AUDIÊNCIA DE INSTRUÇÃO/JULGAMENTO · AVALIAR DOCUMENTAÇÃO PROBATÓRIA · AVISAR CLIENTE DA AUDIÊNCIA · AVISAR CLIENTE DA DATA DA SUSTENTAÇÃO ORAL · AVISAR CLIENTE DA PERÍCIA · BUSCAR INFORMAÇÕES EM ÓRGÃO PÚBLICO · CARGA DE PROCESSO · COBRAR HONORÁRIOS/ENVIAR BOLETO · COLETA DE PROVAS · COMPRAR MATERIAL PARA O ESCRITÓRIO · CONEXÃO FEITA · CONFERIR CÁLCULO DO PERITO/DA PARTE · CONFERIR/REVISAR PETIÇÃO · CONTESTAÇÃO COM MODELO · CONTESTAÇÃO COMPLEXA · CONTESTAÇÃO SEM MODELO · CONTRATAR CORRESPONDENTE/PARCEIRO · CUMPRIMENTO DE EXIGÊNCIAS · DAR PALESTRA EM EVENTO · DESPACHO COM JUIZ · DESPACHO COM O DESEMBARGADOR · DESPACHO COM O MINISTRO · DESPACHO/PROTOCOLO NO CARTÓRIO · DEVOLUÇÃO DE DOCUMENTOS/PROCESSO · DIGILITALIZAÇÃO DE DOCUMENTOS · DILIGÊNCIA EM CARTÓRIO · EDIÇÃO DE ARTE PARA REDE SOCIAL · EFETUAR PAGAMENTO · ELABORAR CÁLCULO SIMPLES · ELABORAR CONTRARRAZÕES · ELABORAR DECLARAÇÕES FINAIS · ELABORAR DECLARAÇÕES INICIAIS · ELABORAR ESBOÇO DE PARTILHA · ELABORAR NOTIFICAÇÃO EXTRAJUDICIAL · ELABORAR PETIÇÃO COMPLEXA · ELABORAR PETIÇÃO DE ACORDO · ELABORAR PETIÇÃO DE CUMPRIMENTO DE SENTENÇA · ELABORAR PETIÇÃO DE EXECUÇÃO · ELABORAR PETIÇÃO DE LIQUIDAÇÃO (TRABALHISTA) · ELABORAR PETIÇÃO INICIAL COM MODELO · ELABORAR PETIÇÃO INICIAL SEM MODELO · ELABORAR PLANO DE CARTILHA · ELABORAR PROPOSTA DE ACORDO · ELABORAR QUESITOS · ELABORAR RECURSO ADMINISTRATIVO · ELABORAR RELATÓRIO PROCESSUAL · ELABORAR REQUERIMENTO ADMINSITRATIVO · ELABORAR RESUMO DA DECISÃO PARA O INSS · EMBARGOS À EXECUÇÃO · EMBARGOS DE DECLARAÇÃO · EMBARGOS INFRINGENTES · EMENDA À INICIAL · EMISSÃO DE PARECER · EMITIR BOLETO · EMITIR CONTRATO DE HONORÁRIOS · ENTREGA DE DOCUMENTOS · ENTREGAR CARTA DE CONVITE PARA TESTEMUNHA · ENTREGAR GUIA DO ITCD PARA O INVENTARIANTE · ESCREVER ARTIGO · EXPEDIÇÃO DE ALVARÁ · EXPEDIR CERTIDÕES · FAZER ADMISSÃO DE COLABORADOR · FAZER ALTERAÇÕES REQUERIDAS PELA FAZENDA · FAZER DEMISSÃO DE COLABORADOR · FAZER ENTREVISTA DE COLABORADOR · FAZER O BRIEFING · FAZER RELATÓRIO DE COMISSÃO MENSAL DO PARCEIRO · FECHAMENTO COM COBRANÇA INICIAIS · FECHAMENTO COM HONORÁRIOS RECORRENTES · FECHAMENTO SEM COBRANÇA INICIAIS · GERENCIAR ANÚNCIOS DO ESCRITÓRIO SEMANAL · IMPUGNAÇÃO À PENHORA · IMPUGNAÇÃO AO CÁLCULO · INFORMAR CLIENTE DO ANDAMENTO DO PROCESSO · INFORMAR O CLIENTE DA DECISÃO · INTIMAÇÃO INSS PARA IMPLANTAR BENEFÍCIO · INVESTIGAÇÃO PRIVADA · IR AO BANCO · LEVANTAMENTO DE ALVARÁ · LEVANTAMENTO DE RPV · LIGAR PARA A PARTE CONTRÁRIA/ADVOGADO · LIMPEZA DO ESCRITÓRIO · NEGOCIAR CONTRATO DE PARCERIA · OBTER PROVA · OPORTUNIDADE GERADA · OPORTUNIDADE PERDIDA · ORGANIZAR AGENDAS · ORGANIZAR CONTAS A PAGAR · ORGANIZAR DOCUMENTOS · PAGAR CONTAS INTERNET BANKING · PAGAR PARCEIROS · PAGAR SALÁRIO · PAGAR/REPASSAR VALOR PARA CLIENTE · PARTICIPAR DE EVENTO · PETIÇÃO INTERMEDIÁRIA · PREPARAR SUSTENTAÇÃO ORAL · PREPARAR TESTEMUNHAS · PROCESSO GANHO · PROCESSO PERDIDO · PROTESTO ANTI PRECLUSIVO · PROTOCOLO REQUERIMENTO · PROTOCOLO/ENVIO CORREIOS · RECURSO DE APELAÇÃO/INOMINADO · RECURSO ESPECIAL · RECURSO EXTRAORDINÁRIO · RELATÓRIO DE AUDIÊNCIA · RELATÓRIO FINANCEIRO MENSAL · RÉPLICA/IMPUGNAÇÃO À CONTESTAÇÃO · RESPONDER DÚVIDAS DO CLIENTE · REUNIÃO COM PARCEIRO · REVOGAÇÃO DE MANDATO · SAQUE DOS HONORÁRIOS NO BANCO · SOLICITAR DESISTÊNCIA · SOLICITAR DOCUMENTOS · SOLICITAR INFORMAÇÕES DO CLIENTE · SOLICITAR REEMBOLSO PARA O CLIENTE · SUSTENTAÇÃO ORAL TRT TRF TJ · SUSTENTAÇÃO ORAL TST STJ STF · TENTAR ACORDO EXTRAJUDICIAL · VIDEOCHAMADA OU LIGAÇÃO +30MIN · VISITAR POSSÍVEIS CLIENTES

**Exemplos de pontuação Taskscore observados:** ANÁLISE DE CASO DO PARCEIRO 50 pts · ATENDER NOVA DEMANDA DO PARCEIRO 25 · ATENDIMENTO AO CLIENTE EXTERNO 80 · ATENDIMENTO AO CLIENTE INTERNO 50 · COBRAR HONORÁRIOS/ENVIAR BOLETO 30 · DAR PALESTRA EM EVENTO 25 · DEVOLUÇÃO DE DOCUMENTOS 5 · DIGITALIZAÇÃO DE DOCUMENTOS 10 · EDIÇÃO DE ARTE PARA REDE SOCIAL 20 · ESCREVER ARTIGO 100 · FAZER O BRIEFING 40 · RELATÓRIO DE COMISSÃO MENSAL 50 · GERENCIAR ANÚNCIOS SEMANAL 200 · NEGOCIAR CONTRATO DE PARCERIA 100 · ORGANIZAR DOCUMENTOS 10 · PARTICIPAR DE EVENTO 50 · REUNIÃO COM PARCEIRO 50 · SOLICITAR DOCUMENTOS 10 · SOLICITAR INFORMAÇÕES DO CLIENTE 10.

### 3.9 Plano de contas financeiro padrão

**Grupos DRE (`indexes_id`) — 10:**
`0` Deduções da receita bruta · `1` Receitas · `2` Folha de pagamento · `3` Encargos sociais · `4` Tributos · `5` Despesas fixas · `6` Despesas variáveis · `7` Despesas bancárias · `8` Marketing e comercial · `9` Distribuição de lucros e participação

**Categorias de RECEITA (14):**
1. HONORÁRIOS INICIAIS · 1. HONORÁRIOS FINAIS · 1. HONORÁRIOS DE SUCUMBÊNCIA · 1. HONORÁRIOS CONSULTORIAS · 1. HONORÁRIOS POR MENSALIDADE · 1. RPVS · 1. PRECATÓRIOS · 1. ALVARÁS · 1. MULTA E JUROS · 1. APLICAÇÕES FINANCEIRAS · 1. APORTE DE SÓCIO · 1. INTEGRALIZAÇÃO DE SÓCIO · 5. PAGAMENTO DE FATURA · 6. REEMBOLSO DE CUSTO POR CLIENTES

**Categorias de DESPESA (47):**
0. HONORÁRIOS DE PARCEIROS · 0. HONORÁRIOS DE ADVOGADOS ASSOCIADOS · 2. ADIANTAMENTOS · 2. RESCISÃO DO CONTRATO DE TRABALHO · 2. ABONO PRODUTIVIDADE · 2. REMUNERAÇÃO DE FUNCIONÁRIOS · 2. HORAS EXTRAS · 2. FÉRIAS · 2. SALÁRIOS · 2. PRÓ-LABORE · 2. VALE TRANSPORTE · 2. VALE ALIMENTAÇÃO · 3. FGTS · 4. SIMPLES NACIONAL · 4. IPTU · 4. IOF · 4. INSS · 4. OUTROS IMPOSTOS · 5. ÁGUA · 5. CONTADOR · 5. TELEFONIA · 5. CONDOMÍNIO · 5. ANUIDADE OAB · 5. ENERGIA ELÉTRICA · 5. ALUGUEL · 5. INTERNET · 6. MULTAS JUDICIAIS · 6. DESPESAS DE CARTÓRIO · 6. RESSARCIMENTO CUSTO AO FUNCIONÁRIO · 6. MÓVEIS · 6. CURSOS E TREINAMENTOS · 6. MATERIAIS DE CONSTRUÇÃO · 6. HOTEL · 6. MATERIAIS DO ESCRITÓRIO · 6. CORREIOS · 6. MATERIAIS DE LIMPEZA E ALIMENTAÇÃO · 6. GUIA DE CUSTAS PAGAS PARA O CLIENTE · 6. CONFRATERNIZAÇÕES DO ESCRITÓRIO · 6. COMBUSTÍVEL · 6. EQUIPAMENTOS ELETRÔNICOS · 6. PASSAGENS AÉREAS E RODOVIÁRIAS · 6. ALARMES E SEGURANÇA · 6. DEVOLUÇÃO APORTE DO SÓCIO · 7. TAXAS BANCÁRIAS · 7. JUROS BANCÁRIOS · 8. MARKETING JURÍDICO E PUBLICIDADE · 9. DISTRIBUIÇÃO DE LUCROS

**Contas padrão criadas na conta nova:** CONTA PRINCIPAL · DINHEIRO · INVESTIMENTOS · CARTÃO DE CRÉDITO. **Centro de custo padrão:** GERAL.

### 3.10 Cargos (`occupations_id`) — 66
Advogado Gestor · Advogado Técnico · Advogado Comercial · Advogado Marketing · Controller Jurídico · Financeiro · Parceiro · Analista de Suporte · Gerente de Tecnologia · Departamento · Desenvolvedor · Diretor · Assistente Administrativo · Analista de Dados · Estagiário · Financeiro e RH · Programador ou TI · Administrador · Médico · Motorista · Assistente Jurídico · Analista de CS · Psicólogo · Recepcionista · Profissional de RH · SDR - Pré-Vendas · Secretário · Advogado Sócio Sem Atuação · Suporte · Supervisor · Técnico · Terceirizado · Tesoureira · Trainee · Treinador · Zelador · Outra Função Não Listada · Assistente Financeiro · Administrativo e Financeiro · Usuário Externo · Secretaria · Agente ou Captador · Assistente Jurídico · Auxiliar Jurídico · Estagiário de Direito · Estagiário de Marketing · Estagiário de Administrativo · Estagiário de Financeiro · Estagiário Outras Áreas · Analista Jurídico · Assessor Jurídico · Atendente · Assistente de Marketing · Administrativo · Gestor Jurídico · Coordenador Jurídico · Coordenador Comercial · Coordenador de Marketing · Coordenador de Atendimento · Gerente Jurídico · Gerente de Marketing · Gerente de Atendimento · Gerente Comercial · Fechador de Contratos · Consultor Jurídico · Contador · Advogado Parceiro · Correspondente

### 3.11 Perfis de acesso — 3
| Perfil | Descrição |
|---|---|
| **Gestor** | Acesso total; único que cria/edita tarefas do catálogo, metas e configurações |
| **Administrador** | Acesso amplo, sem parte das configurações estruturais |
| **Colaborador** | Acesso operacional |

**Acesso financeiro** é dimensão independente: `Sem acesso` · `Somente visualizador` · `Acesso completo`.

---

## 4. Módulos e funcionalidades

### 4.1 Meu Painel
- **Cards:** Tarefas concluídas (com % vs mês anterior) · Pontos acumulados · Tarefas pendentes · Alcance da meta.
- **Gráfico Taskscore:** comparativo Mês atual × Mês passado × Meta, alternável entre visão *mensal* e *diária*.
- **Atividades concluídas:** feed do mês.
- **Mini-calendário** com contagem de tarefas/intimações por dia.
- **Caixa de entrada** (seções configuráveis) com ações em massa.
- **Tour guiado** embutido (play/pause).
- **Modo escuro** (planos Banca Max e Elite).

### 4.2 Agenda
Visões **Mês · Semana · Dia · Agenda**. Filtros: usuário, `column` (Data do compromisso / Prazo fatal), "Mostrar concluídos". Status coloridos: Pendentes · Concluídas · Atrasadas. Sincronização unidirecional (ADVBOX → calendário externo) via URL iCal por usuário.

### 4.3 Atividades
Lista global de tarefas com todos os filtros da seção 2.3, exportação Excel/PDF, ordenação por Tarefa, Partes, Data compromisso, Prazo fatal e Responsável.

### 4.4 CRM
- **Kanban por fase processual** — colunas: Marketing · Negociação · Consultoria · Administrativo · Judicial · Recursal · Execução · Financeiro · Arquivamento.
- Arrastar card entre etapas **altera a fase do processo** e pode disparar workflow (config. na Etapa) ou Flowter.
- **Controle de estagnação:** filtro `display_stagnant` (Todos / Somente estagnados / Somente em andamento); a marcação de estagnado é definida por etapa (`stagnant_days`).
- Cards de topo: Processos · Recebidos este mês · Valor · Estagnado.
- Sub-visões: `board-crm` (quadro) e `crm-performance` (desempenho).
- Ação em massa: **Alterar fase**.

### 4.5 Contatos
Ver 2.1. Inclui **nuvem de documentos por contato** (pastas, upload múltiplo, busca em todas as pastas, extrair ZIP, ordenar por nome/data/tamanho/tipo) e notificação de aniversariantes (ícone 🎂).

### 4.6 Processos
Ver 2.2. Cada processo tem: **timeline unificada** (tarefas, movimentações automáticas, movimentações manuais, publicações e lançamentos financeiros, cada um com toggle), **nuvem de documentos**, **financeiro individual**, **histórico de tarefas** e **partes/parceiros**.

### 4.7 Intimações
Lista de publicações capturadas. Filtros: `interval` (Hoje / últimos 3 dias / últimos 7 dias / período), usuário responsável, cliente, tribunal (lista nominal completa), número do processo, data de entrega. Cada intimação vira **tarefa** distribuída conforme o Grupo de ação ou o Responsável geral.

### 4.8 Parceiros
Rede de escritórios parceiros com compartilhamento de processos. Cards: Processos compartilhados (ativos) · Demanda pendente pelo escritório · Demanda pendente pelo parceiro. Filtros `report` (Tarefas pendentes no escritório / Aguardando retorno do parceiro / Processos ativos / Todos inclusive arquivados), `status` (Atrasados / Futuros / Pendentes / Recebidos), fases processuais (checkboxes), período.

### 4.9 Modelos (editor de documentos)
- Abas **Modelos do Escritório** e **Biblioteca Pública**.
- Filtro por tipo: Todos · **Contratos · Petições · Recursos · Documentos** · Somente os excluídos.
- Iniciar documento **Em branco** ou a partir de modelo.
- **Editor completo:** desfazer/refazer, localizar e substituir, inserir imagem/tabela/quebra de página, cabeçalho, rodapé, marca d'água, cabeçalho e rodapé timbrado, **digitação por voz**, fonte/tamanho/cor, negrito/itálico/sublinhado/tachado, alinhamentos, listas numeradas/marcadores/checklist, indentação.
- Ações: salvar na nuvem · gerar documento (PDF) · imprimir · enviar por e-mail · fazer cópia · editar · excluir.

**Variáveis de preenchimento automático:**
- *Cliente:* nome completo, CPF/CNPJ, RG, data de nascimento (numérica e por extenso), estado civil, nacionalidade, profissão, endereço, e-mail, telefone, nome da mãe, dados do representante (nome, CPF/CNPJ, RG, endereço).
- *Processo:* número CNJ, tipo de ação, tribunal, comarca, vara, fase, responsável, valor dos honorários, valor da causa (numérico e por extenso), data do ajuizamento, data do arquivamento, resultado.
- *Escritório/Usuário:* razão social, CNPJ, endereço, telefone, e-mail, site, nome do usuário, cargo, CPF, OAB, celular.

### 4.10 Financeiro
Ver 2.4. Inclui contas a pagar/receber, contas e cartões (com fechamento e vencimento de fatura), centros de custo, fluxo de caixa por conta, DRE/DFC por agrupamento, inadimplência, cobrança recorrente e parcelada (até 100x), emissão de boleto/cartão via Asaas, registro interno e anexos por lançamento.

### 4.11 Relatórios / Gestão
**Disponível em Banca Jurídica, Banca Max e Elite:**
- **Painel de Agilidade:** gráfico Concluídas em dia / Concluídas em atraso / Pendentes; Tarefas com mais atrasos; Colaboradores com mais tarefas atrasadas; Agilidade geral (média de cumprimento e média de atraso).
- **Painel de Produtividade:** tarefas atribuídas, concluídas, atrasadas, prazo fatal nos próximos 5 dias; gráfico semanal (seg–sex); ranking individual com filtros "Classificar por" (Pontuação / Volume de tarefas / Tarefas atrasadas / Envolvimento) e "Período" (mês ou **VIDA TODA — ELTV**).
- **Relatórios tabulares (`page`):** Produtividade · Tarefas atrasadas · Registros de acesso · Novos clientes · Novos processos · Processos ganhos · Processos perdidos. Filtros por colaborador, busca e período; exportação Excel/PDF.

**Business Intelligence — plano Elite** `[não verificado na UI]`:
| Aba | Conteúdo |
|---|---|
| **Estoque e Prospecção** | Oportunidades do mês · Processos ativos · Processos arquivados · Processos +120 dias parados · Fechamentos do mês (variação e evolução 6 meses) · Em atendimento · resumo da carteira por fase e período · gráficos por grupo de ação e taxa de conversão |
| **Safra e Qualidade** | Taxa de sucesso (ganhos/perdas) por grupo de ação · análise por safra (ano de fechamento) · ciclo de vida das ações · comparações históricas |
| **Tempo e Honorários** | Média de honorários por processo · média mensal de honorários · **tempo perdido** · ciclos Prospecção / Produção / Execução / Rotação completa · tempo médio por fase e por grupo de ação |
| **Custos** | Custo de Prospecção (**CAC**) · custo médio na Produção · na Execução · da rotação completa · **custo por ponto (esforço)** · gráfico de tempo por etapa |

> Gráficos de BI atualizam a cada 8 horas; as tabelas de relatório operam em tempo real. Acesso restrito a Gestor/Administrador.

### 4.12 Recursos transversais
- **Livro de ponto online** (baseado em `work_start`/`work_interval`/`work_end`).
- **Registro de acessos** (data, IP, primeiro e último login) — toggle em Configurações > Usuários.
- **Nuvem:** 50/70/90/100 GB conforme plano; excedente a **R$ 0,50/GB/mês**.
- **Certificado Digital A1** (.pfx/.p12) por usuário, criptografado; A3 não é aceito.
- **Notificações ao cliente** por E-mail, SMS e WhatsApp.
- **Programa de indicação** com link próprio.
- **Temas** (claro/escuro).

---

## 5. Integrações

### 5.1 Catálogo completo (Configurações > Integrações e API) — 14

| # | Integração | Descrição oficial | Categoria |
|---|---|---|---|
| 1 | **API ADVBOX** | Conecte seu escritório a centenas de apps com segurança e facilidade | Plataforma |
| 2 | **App Mindchat** | Organize atendimentos no WhatsApp com IA. Parceiro oficial Meta | WhatsApp/IA |
| 3 | **Atende Direito** | Sistema de atendimento inteligente multicanal | Atendimento |
| 4 | **Briefing Jurídico Ria** | IA no WhatsApp para atender clientes automaticamente | WhatsApp/IA |
| 5 | **Chat Jurídico** | Centralize atendimentos no WhatsApp com IA | WhatsApp/IA |
| 6 | **Chatguru** | Melhore o atendimento de maneira simples, rápida e eficaz | WhatsApp/IA |
| 7 | **Guimoo** | Automatize o setor comercial do escritório com uma I.A. | Comercial/IA |
| 8 | **Idvzap** | Gerencie todas as mensagens dos clientes em um único lugar | WhatsApp |
| 9 | **Liderhub** | Agentes de IA humanizados e inteligentes 24h por dia | WhatsApp/IA |
| 10 | **Sabio Adv** | Atendimento com IA de forma humanizada para advogados | WhatsApp/IA |
| 11 | **Touchworks** | Automatize seu WhatsApp com Inteligência Artificial | WhatsApp/IA |
| 12 | **Asaas** | Automatize a cobrança de honorários por boleto e cartão de crédito | Financeiro |
| 13 | **Agenda** | Sincronize com Google Calendar, Apple ou Outlook | Produtividade |
| 14 | **RD Station Marketing** | Envie e receba dados de leads do RD Station Marketing | Marketing |

> A ADVBOX declara não prestar suporte técnico às plataformas parceiras de WhatsApp/IA (itens 2–11).

### 5.2 Asaas (financeiro) — configuração e regras

**Fluxo:** conta Asaas aprovada → Minha conta → aba *Integração* → sub-aba *Chave de API* → **Gerar chave de API** (nome + expiração opcional) → confirmar código por **SMS** → copiar token → ADVBOX: *Configurações > Integrações e API > Asaas* → colar token → **Salvar dados**.

**Comportamento:**
- Ao lançar uma receita, selecionar a conta Asaas no campo **Conta/Cartão** habilita a geração de cobrança por **boleto, cartão ou carnê**.
- Baixa automática do pagamento após confirmação do Asaas (**em até 48 h**).
- Taxas das transações são lançadas automaticamente como **despesa** na ADVBOX.

**Limitações (importantes para replicar a lógica):**
1. Cobrança só é gerada se a conta Asaas estiver selecionada no lançamento.
2. Integração única por escritório (nível de conta, não de usuário).
3. Alterar manualmente o status de uma cobrança **quebra o vínculo** com o Asaas (para de receber atualizações).
4. Cancelamento deve partir da ADVBOX — cancela o boleto/link no Asaas e remove o vínculo.
5. Trocar a chave no Asaas exige atualizar o token na ADVBOX manualmente.
6. Notificações ao cliente (SMS/e-mail da cobrança) são configuradas no painel do Asaas.

### 5.3 Agenda (Google / Outlook / Apple)
- Cada **usuário** recebe uma **URL iCal única**, exibida em *Configurações > Integrações > Agenda* após ativar a chave de exibição ("Ver URL").
- Só aparecem no calendário externo as tarefas com **"Mostrar na agenda"** ativado.
- **Sincronização unidirecional** (ADVBOX → calendário). Alterações feitas fora não retornam.
- Google Agenda: *Outras agendas* → `+` → *Do URL* → colar → *Adicionar agenda*. O Google pode atrasar a atualização; a ADVBOX envia imediatamente.

### 5.4 RD Station Marketing
- Campo **Configurar token** (obtido em `app.rdstation.com.br/integracoes/tokens`).
- Tabela de automações com: **Nome da automação · Webhook URL · Última interação**.
- Envio e recebimento de dados de leads (bidirecional).

### 5.5 API ADVBOX
Ver seção 6. Comercialmente: **API para Escritórios** a partir de R$ 280/mês; **Parceiros Homologados** a partir de R$ 3.500/mês (rotas personalizadas, IPs autorizados por chave, custos zerados para escritórios usuários).

### 5.6 Outros produtos integráveis (menu Conta e assinatura > Nossos produtos)
`API ADVBOX` · `FLOWTER + API ADVBOX` · `INSS GERID` · `PLANO INTELIGENTE` · `NEUROBOX`

**Previdia / INSS GERID:** extensão de navegador que varre a lista de processos exibida no GERID e identifica novas movimentações (incluindo movimentações internas em requerimentos com perícia). Sincronização **manual** (botão SINCRONIZAR); as movimentações encontradas podem gerar tarefas na ADVBOX. Importante: só analisa os processos visíveis na página — recomenda-se exibir 500 por página.

### 5.7 n8n
Há artigo oficial de integração ADVBOX ↔ n8n (via API + Flowter webhooks) — `guia.advbox.com.br/api/integracao-advbox-n8n`.

---

## 6. API REST — 22 endpoints

**Base URL:** `https://app.advbox.com.br/api/v1`
**Auth:** `Authorization: Bearer <TOKEN>` (fornecido pela ADVBOX a parceiros/integradores aprovados)
**Docs:** `https://api.softwareadvbox.com.br/docs` · versão completa em `/llms-full.txt`
**CORS:** bloqueado — não há "try it out" no navegador; usar Postman/Insomnia/cURL.

### Rate limits
| Método | Limite | Período |
|---|---|---|
| GET | 30 requisições | por minuto |
| POST | 500 requisições | por dia (por rota) |
| PUT | 500 requisições | por dia |

Erro `429 Too Many Requests` ao estourar. `401 {"error":"Unauthenticated."}` sem token válido.

### 6.1 Settings — **consultar primeiro**
`GET /settings` — retorna todos os IDs de referência da conta:

```json
{
  "users":   [{ "id", "name", "email", "cellphone" }],
  "origins": [{ "id", "origin" }],
  "tasks":   [{ "id", "task", "reward" }],
  "stages":  [{ "id", "stage", "step" }],
  "lawsuit_types": [{ "id", "type", "group" }],
  "financial": {
    "banks":        [{ "id", "name", "institution" }],
    "categories":   [{ "id", "category", "type": "income|expense" }],
    "cost_centers": [{ "id", "cost_center" }],
    "departments":  [{ "id", "department" }]
  }
}
```

| Campo | Usado como | Em |
|---|---|---|
| `users[].id` | `users_id` / `from` / `guests[]` | customers, lawsuits, posts, transactions |
| `origins[].id` | `customers_origins_id` | customers |
| `tasks[].id` | `tasks_id` | posts |
| `stages[].id` | `stages_id` | lawsuits |
| `lawsuit_types[].id` | `type_lawsuits_id` | lawsuits |
| `financial.banks[].id` | `debit_account` | transactions |
| `financial.categories[].id` | `categories_id` | transactions |
| `financial.cost_centers[].id` | `cost_centers_id` | transactions |
| `financial.departments[].id` | `sectors_id` | transactions |

### 6.2 Customers (4 endpoints)

**`POST /customers`** — obrigatórios: `users_id`, `customers_origins_id`, `name`.
Opcionais: `email`, `document`, `identification`, `phone`, `cellphone`, `birthdate` (YYYY-MM-DD), `occupation`, `postalcode` (**99999-999 com hífen obrigatório**), `city`, `state` (2 letras), `notes`, `gender`, `street`, `region`, `country`, `number_ctps`, `number_pis`, `number_cid`.
Validações: CPF/CNPJ com algoritmo real e sem duplicação; e-mail validado mas duplicável; telefone com DDD **sem código do país** (enviar `55`/`+` grava `ERROR`; sem DDD → 422).
Resposta `201`: `{"success":true,"customers_id":12345678}`

**`GET /customers`** — filtros: `name` (parcial), `phone`, `identification`, `document`, `email`, `city`, `state`, `occupation`, `birthdays` (bool), `created_start`+`created_end`, `limit` (máx. 1000), `offset`.
Resposta: `{offset, limit, totalCount, data[], query}` — cada item traz `id, name, identification, document, cellphone, gender, civil_status, phone, email, occupation, street, postalcode, region, city, state, country, birthdate, number_ctps, number_pis, number_cid, notes, origin, created_at, lawsuits[]`.

**`GET /customers/{id}`** — mesmos campos + `lawsuits[]` com `lawsuit_id`, `process_number`, `protocol_number`.

**`GET /customers/birthdays`** — filtros `month` (1-12), `limit`, `offset`.

### 6.3 Lawsuits (8 endpoints)

**`POST /lawsuits`** — obrigatórios: `users_id`, `customers_id` (array, mín. 1), `stages_id`, `type_lawsuits_id`.
Opcionais: `process_number` (**CNJ real e oficialmente distribuído — validado contra as bases do Judiciário**), `protocol_number`, `folder` (máx. 30), `date`, `notes`, `fees_expec`, `fees_money`, `contingency`, `status_closure`, `exit_production`, `exit_execution`.
Derivados (não enviar): `group_id`/`group`, `steps_id`/`step`.
Resposta `201`: `{"success":true,"lawsuits_id":12358596}`

**`PUT /lawsuits/{id}`** — mesmos campos.

**`GET /lawsuits`** — 24 filtros: `name`, `customer_id`, `identification`, `process_number`, `protocol_number`, `folder`, `notes`, `group`, `type`, `responsible`, `stage`, `step`, `process_date_start/_end`, `status_closure_start/_end`, `exit_production_start/_end`, `exit_execution_start/_end`, `created_start/_end`, `limit`, `offset`.
Busca parcial: name, group, type, responsible, stage, step, notes. Valor exato: customer_id, process_number, protocol_number, folder, identification. Múltiplos filtros combinam com AND.
Item da resposta: `id, process_number, protocol_number, folder, process_date, fees_expec, fees_money, contingency, type_lawsuit_id, type, group_id, group, created_at, status_closure, exit_production, exit_execution, responsible_id, responsible, stages_id, stage, steps_id, step, notes, customers[{customer_id,name,identification,origin}]`.

**`GET /lawsuits/{id}`** — idem, registro único.

**`GET /history/{lawsuit_id}`** — filtro `status` (`pending`/`completed`). Retorna `process_number, protocol_number, task, reward, start, date_deadline, comments, local, created_at, author, responsible, customers`.

**`GET /movements/{lawsuit_id}`** — filtro `origin` (`TRIBUNAL`/`MANUAL`). Retorna `lawsuit_id, date, title, header, process_number, protocol_number, customers`.

**`POST /lawsuits/movement`** — cria movimentação manual.

**`GET /last_movements`** — última movimentação de cada processo. Filtros: `lawsuit_id`, `process_number`, `protocol_number`, `date_start`, `date_end`.

### 6.4 Tasks / Posts (2 endpoints)

**`POST /posts`** — obrigatórios: `from`, `guests` (array, mín. 1), `tasks_id`, `lawsuits_id`, `start_date` (YYYY-MM-DD ou DD/MM/YYYY).
Opcionais: `start_time` (HH:MM), `end_date`, `end_time` (**exige `end_date`**), `date_deadline`, `local`, `comments`, `urgent`, `important`, `display_schedule`.
A API detecta e impede tarefas duplicadas. Resposta `200`: `{"success":true,"posts_id":180922743}`

**`GET /posts`** — filtros: `date_start`+`date_end`, `created_start`+`created_end`, `deadline_start`+`deadline_end`, `completed_start`+`completed_end` (todos em pares obrigatórios), `user_id`, `user_name`, `task_id`, `id`, `lawsuit_id`, `limit`, `offset`.
Item: `id, date, date_deadline, task, reward, notes, local, lawsuits_id, created_at, lawsuit{id,process_number,protocol_number,customers[]}, users[{user_id,name,completed,important,urgent}]`.

### 6.5 Publications (1 endpoint)
**`GET /publications/{lawsuit_id}`** — `process_number, protocol_number, start, date_deadline, local, created_at, author, responsible, customers, publication, date`.

### 6.6 Transactions (4 endpoints)

**`POST /transactions`** — obrigatórios: `users_id`, `entry_type` (`income`/`expense`), `debit_account`, `categories_id`, `cost_centers_id`, `amount`, `date_due`.
Opcionais: `customers_id`, `lawsuits_id` (**exige `customers_id`**), `sectors_id`, `description`, `date_payment`.
Regras: `entry_type` deve casar com o tipo da categoria; `amount` usa **vírgula** decimal (`"250,50"` — ponto é descartado, `15.00` vira 1500); `amount` = 0 causa erro 500; `date_payment` não pode ser futura; `description` vira MAIÚSCULAS; `competence` é derivada de `date_due`.

**`PUT /transactions/{id}`** · **`GET /transactions/{id}`** · **`GET /transactions`** — filtros: `lawsuit_id`, `category`, `responsible`, `customer_name`, `debit_bank`, `cost_center`, `description`, `process_number`, `protocol_number`, `customer_identification` (CPF/CNPJ válido obrigatório), e pares `created_*`, `date_due_*`, `date_payment_*`, `competence_*` (MM/YYYY).
Item: `id, entry_type, date_due, date_payment, competence, amount, description, responsible, category, lawsuit_id, process_number, protocol_number, name, identification, debit_bank, credit_bank, cost_center`.

### 6.7 Documents (2 endpoints)
**`GET /documents`** — pelo menos um filtro obrigatório: `name` (parcial, mín. 3 caracteres, com extensão), `customer_id`, `transaction_id`, `post_id`. Item: `id, name, size, links.download, attached_to{type,id,label}, uploaded_at`.

**`GET /documents/{id}/download`** — retorna URL temporária do **Amazon S3**, válida por **300 segundos**.

### 6.8 Changelog
API em produção desde **v1.0.0 (26/11/2025)**, atualmente **v1.24.0 (07/07/2026)** — 24 releases documentadas.

---

## 7. Inteligência Artificial (21 agentes)

Acesso: **Conta e assinatura > Agentes de IA** (ou Configurações > Inteligência Artificial). Todos a **R$ 200/mês por agente**.

### 7.1 Agentes de plataforma (2)

| Agente | Papel | O que faz |
|---|---|---|
| **Justin-e** | Auxiliar de Controller — Expertise em Intimações Judiciais | 1) Recebe intimações diárias e centraliza; 2) Gera resumos objetivos; 3) Faz análise estratégica (impacto no caso + próximos passos); 4) Sugere tarefas automaticamente conforme contexto e prazos; 5) **Contagem automática de prazo**. Métricas divulgadas: +1.200 escritórios, 8× mais rápida que uma pessoa, 99,9% de precisão |
| **Donn@** | Business Intelligence — Agente estratégica / copiloto | 1) Consulta inteligente em tempo real (processos, clientes, tarefas, agenda, financeiro, indicadores); 2) Automação de cadastros (cria clientes e processos por comando); 3) Atualizações automáticas (altera fases, registra movimentações, organiza tarefas); 4) Relatórios sob demanda (produtividade, desempenho da equipe, contratos fechados, inadimplência) |

**Configuração da Justin-e:** mapeamento entre as **tarefas do escritório** e as **nomenclaturas usadas pela Justin-e** + toggle **"Habilitar leitura automática"** (interpreta o conteúdo ao abrir a intimação, sem ativação manual).

### 7.2 Agentes jurídicos por área (19) — geração de petições

| Código | Área do Direito |
|---|---|
| `Consu-3` | Direito do Consumidor |
| `Assis-10` | Direito Assistencial |
| `Tribut-7` | Direito Tributário |
| `Tran-7` | Direito de Trânsito |
| `Banc-1` | Direito Bancário |
| `Trab-2` | Direito Trabalhista |
| `Ambien-3` | Direito Ambiental |
| `Imob-7` | Direito Imobiliário |
| `Crim-1` | Direito Penal e Processual Penal |
| `Gener-4` | Direito Cível Generalista |
| `Respon-7` | Direito da Responsabilidade Civil |
| `Fami-2` | Direito de Família |
| `Digi-2` | Direito Digital |
| `Contratu-4` | Direito Contratual |
| `Adminis-3` | Direito Administrativo |
| `Empresa-9` | Direito Empresarial |
| `Prev-7` | Direito Previdenciário |
| `Intelec-2` | Direito da Propriedade Intelectual |
| `Sau-10` | Direito da Saúde |

### 7.3 Preços comerciais (site)
Justin-e a partir de R$ 200/mês · Donna a partir de R$ 200/mês · Agentes IA a partir de R$ 200/mês **por agente** · Flowter a partir de R$ 280/mês.
Economia divulgada: **+166 h/mês**; 8× mais rápido que humano; 500 intimações/mês ≈ mais de 1 colaborador full-time por ano.

---

## 8. Flowter — motor de automação

Automação sem código, no modelo **gatilho → ação → tempo**.

### 8.1 Estrutura
| Etapa | Descrição |
|---|---|
| **1. O gatilho** | Define quando o fluxo começa: **conclusão de uma tarefa específica** ou **mudança de etapa de um processo** |
| **2. A ação** | Cria tarefas, distribui responsáveis, calcula prazos, aguarda condições ou **integra com sistemas externos via HTTP Request** |
| **3. O tempo** | Imediato, após dias úteis ou corridos, ou condicionado à conclusão de uma etapa anterior |

### 8.2 Comportamento técnico
- É um **webhook outbound**: a ADVBOX envia um JSON padronizado ao sistema externo (n8n, CRM, ERP…). O destino **não precisa devolver resposta**.
- Também executa **ações internas** na própria ADVBOX (criar tarefa, definir responsável, preencher informações).
- Não é plug-and-play: exige mapeamento/tradução de campos no destino.

### 8.3 Payload — gatilho "Tarefa Concluída"

```json
{
  "id": 987654321,
  "process_owner": 456789,
  "accounts_id": 12,
  "sender": 123456,
  "date": "2025-03-15 00:00:00",
  "date_deadline": "2025-03-20 00:00:00",
  "task": "Revisar contrato de prestação de serviços",
  "notes": "Cliente solicitou análise urgente das cláusulas",
  "local": "Escritório Central",
  "lawsuits_id": 5432198,
  "created_at": "2025-03-15 10:30:45",
  "token": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "lawsuit": {
    "id": 5432198,
    "process_number": "1234567-89.2025.8.26.0100",
    "protocol_number": "PROT-2025-0315",
    "lawsuit_owner": 456789,
    "customers": [{
      "customer_id": 8765432, "name": "MARIA SILVA SOUZA",
      "identification": "123.456.789-00", "customers_origins_id": 101,
      "origin": "Indicação", "cellphone": "(11) 98765-4321",
      "phone": "(11) 3456-7890", "email": "maria.silva@email.com"
    }]
  },
  "users": [{
    "user_id": 123456, "name": "JOÃO CARLOS SANTOS",
    "completed": "2025-03-15 14:25:30", "important": 1, "urgent": 1
  }]
}
```

| Campo | Descrição |
|---|---|
| `id` | ID interno da tarefa |
| `task` / `notes` / `local` | Título, observações e local da tarefa |
| `created_at` / `date` / `date_deadline` | Criação, data vinculada e prazo |
| `sender` | ID do usuário que executou a ação |
| `process_owner` | ID do responsável pelo processo |
| `accounts_id` | ID da conta/escritório |
| `token` | Token de verificação do envio |
| `users[]` | `user_id`, `name`, `completed`, `important` (1/0), `urgent` (1/0) |

### 8.4 Payload — gatilho "Mudança de Etapa"

```json
{
  "id": 8765432,
  "lawsuits_id": 8765432,
  "process_owner": 345678,
  "process_number": null,
  "protocol_number": "54321",
  "notes": "Audiência inicial agendada...",
  "customers": [{
    "customer_id": 9876543, "name": "SILVA & ASSOCIADOS ADVOCACIA",
    "identification": "12.345.678/0001-90", "customers_origins_id": 112233,
    "origin": "INDICAÇÃO", "cellphone": "(11) 98765-4321",
    "phone": "(11) 3456-7890", "email": "CONTATO@SILVAASSOCIADOS.COM.BR"
  }]
}
```

| | Tarefa Concluída | Mudança de Etapa |
|---|---|---|
| Natureza | Ação operacional | Ação estrutural |
| Escopo | Afeta uma tarefa | Afeta o processo inteiro |
| Uso típico | Notificações, produtividade, criar nova tarefa | Integração com CRM/financeiro, e-mails automáticos, fluxos estratégicos |

---

## 9. Monitoramento de intimações (Termos Monitorados)

### 9.1 Conceito
Cadastra-se **OAB, CPF ou CNPJ** como *termo monitorado*; o sistema varre Diários Oficiais e sistemas eletrônicos e entrega a intimação **como tarefa** ao responsável.

### 9.2 Duas fontes, características distintas

| | **Intimações Eletrônicas** | **Intimações em Diários (DJEN)** |
|---|---|---|
| Origem | Painéis dos sistemas dos tribunais (PJe, EPROC, PROJUDI, SEEU…) | DJEN — Diário da Justiça Eletrônico Nacional + diários estaduais |
| Captura | Via **Certificado A1** (e às vezes QR Code) | Direto do site oficial, sem login |
| Conteúdo | Inteiro teor da decisão **+ anexos** | Texto idêntico ao publicado, pode ser resumido |
| Vantagem | Intimações mais completas | Não exige senha nem certificado |
| Desvantagem | Pela Resolução CNJ 569/24 **não tem força de intimação** | Nem todos os tribunais publicam integralmente no DJEN |

> Recomendação oficial: usar **as duas fontes combinadas**.

### 9.3 Distribuição das intimações
1. **Grupo de Ação** — entrega ao responsável do grupo vinculado ao processo.
2. **Responsável Geral** — usuário padrão, quando o processo não está cadastrado ou o grupo não tem responsável definido.

### 9.4 Status de monitoramento
| Status | Significado | Ação |
|---|---|---|
| **Monitorando** ✅ | Buscando novas informações no tribunal | Nenhuma |
| **Sincronizando** 🔄 | Alinhando dados existentes (até **72 h úteis**) | Aguardar |
| **Monitoramento Ativo** | Estado ideal, recebendo atualizações | Nenhuma |
| **Falha** ❌ | Erro de conexão/autenticação | Corrigir e atualizar o termo |
| **Informe os dados de acesso** | Faltam credenciais | Preencher |

**Erros comuns:** `QRCode inválido` · `Senha inválida` · `Envie um certificado digital válido` · `A senha do certificado é inválida` · `Falha ao validar certificado digital`.
Regra prática: no login do tribunal, usar **somente números** (CPF sem pontos/traços); caracteres `%$&` geram "senha inválida"/"login inválido".
Falhas são notificadas **como tarefa** ao responsável.

### 9.5 Certificado Digital A1
- Somente **A1** nos formatos **.pfx** ou **.p12**. **A3 (token/pen drive/nuvem) não é aceito.**
- Enviado em *Configurações > Termos Monitorados > "Envie o seu certificado digital"*; também há campo no cadastro do usuário.
- Armazenado **criptografado**; uso restrito aos tribunais selecionados. A senha é validada no momento do upload.

### 9.6 Custos de monitoramento
| Item | Valor |
|---|---|
| Clientes antigos (por estado, diário ou sistema eletrônico) | R$ 7,00/mês |
| Novas assinaturas (por estado, diário ou sistema eletrônico) | R$ 35,00/mês |
| SEEU (abrangência nacional) | R$ 40,00/mês |

Termos DJEN inclusos por plano: Essencial 1 · Banca Jurídica 1 · Banca Max 25 · Elite 100.

### 9.7 Cobertura
Todos os 27 estados + DF, com, por estado: diário estadual, DJEN (Estadual, Federal, Trabalho, Eleitoral), diários dos TRFs, TRTs, TREs, STF, STJ, STM, TST, TSE, CNJ, CNMP/MPU/Tribunal Marítimo/Conselho Federal da OAB e DE/OAB.

---

## 10. Planos e matriz completa de funcionalidades

### 10.1 Preços
| Plano | Mensal | Perfil |
|---|---|---|
| **Essencial** | R$ 220 + taxa de ativação | Saindo do papel e das planilhas |
| **Banca Jurídica** | R$ 450 + taxa | Controladoria automatizada e financeiro integrado |
| **Banca Max** *(mais escolhido)* | R$ 900 + taxa | Automação avançada e gestão financeira estratégica |
| **Elite** *(mais completo)* | R$ 1.800 + taxa | BI completo e consultoria personalizada |
| **Big Offices** | a partir de R$ 5.000 | +20 mil processos, API dedicada, banco de dados dedicado, suporte de devs em tempo real |

Teste gratuito de **7 dias**, sem cartão de crédito. Sem fidelidade. Pagamento por **PIX ou cartão**; taxa de ativação à vista, 2x ou 3x.

### 10.2 Matriz completa (SIM = incluso, — = não)

#### Funcionalidades gerais
| Recurso | Essencial | Banca Jurídica | Banca Max | Elite |
|---|---|---|---|---|
| Usuários | Ilimitados | Ilimitados | Ilimitados | Ilimitados |
| Publicações de Diários de Justiça | 1 termo Nacional OAB/CPF/CNPJ | 1 termo Nacional | 25 termos nacionais (DJEN) | 100 termos nacionais (DJEN) |
| Intimações eletrônicas | SIM | SIM | SIM | SIM |
| Processos ativos inclusos (com push) | 500 | 500 | 500 | 500 |
| Captura automática de andamentos (push) | Opcional | Opcional | Opcional | Opcional |
| Automações de atendimento (E-mail, SMS, WhatsApp) | SIM | SIM | SIM | SIM |
| Limite de processos ativos | 2.000 | Ilimitado | Ilimitado | Ilimitado |
| Espaço na nuvem | 50 GB | 70 GB | 90 GB | 100 GB |
| Modo escuro | — | — | SIM | SIM |
| Migração de dados | Simplificada | Avançada c/ dupla validação | Avançada c/ dupla validação | Avançada c/ dupla validação |
| Onboarding | Online gravado | Coletivo ao vivo | Individual personalizado | Individual personalizado |

#### Gestão de tarefas e prazos
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Atribuição de tarefas, prazos e compromissos | SIM | SIM | SIM | SIM |
| Controle de produtividade do escritório | SIM | SIM | SIM | SIM |
| Intimações judiciais com distribuição automática | SIM | SIM | SIM | SIM |
| Pauta de audiências automática por advogado | SIM | SIM | SIM | SIM |
| Agenda integrada Google/Apple/Outlook | SIM | SIM | SIM | SIM |
| Tarefa para múltiplos usuários | SIM | SIM | SIM | SIM |
| Quadro de tarefas Kanban | SIM | — | SIM | SIM |
| Controle de prazos com notificações por e-mail | — | SIM | SIM | SIM |
| IA com sugestão automática da próxima tarefa | SIM | SIM | SIM | SIM |
| Painel de controladoria jurídica digital | — | — | SIM | SIM |
| Criação de times | — | — | SIM | SIM |
| Workflow de tarefas automático | — | — | SIM | SIM |
| Painel para controle de tarefas em tempo real | — | — | — | SIM |

#### Controle de clientes
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Cadastro automatizado por CPF | SIM | SIM | SIM | SIM |
| Controle de origem dos clientes | SIM | SIM | SIM | SIM |
| Notificações de aniversariantes do dia e mês | SIM | SIM | SIM | SIM |
| Relatórios de clientes e partes contrárias (data, cidade, origem) | SIM | SIM | SIM | SIM |
| Análise inteligente da carteira de clientes | SIM | SIM | SIM | SIM |

#### Gestão de processos
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Cadastro de processos de prospecção | SIM | SIM | SIM | SIM |
| Cadastro judicial, administrativo, serviços e consultivo | SIM | SIM | SIM | SIM |
| Controle por fase processual | SIM | SIM | SIM | SIM |
| Histórico de tarefas por processo | SIM | SIM | SIM | SIM |
| Controle financeiro individual por processo | — | SIM | SIM | SIM |
| Relatório de processos com e sem movimentações | — | SIM | SIM | SIM |
| Relatórios moduláveis com filtros dinâmicos | — | SIM | SIM | SIM |
| Contingenciamento de processos | — | — | SIM | SIM |

#### CRM
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Quadro Kanban por fase processual | SIM | SIM | SIM | SIM |
| Controle individual e geral por processos | SIM | SIM | SIM | SIM |
| Controle de processos estagnados | SIM | SIM | SIM | SIM |
| Sequenciamento de etapas personalizável | SIM | SIM | SIM | SIM |
| RD Station Marketing | SIM | SIM | SIM | SIM |
| Workflow automático por etapa | — | — | SIM | SIM |

#### Gestão financeira
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Controle financeiro por cliente e por processo | — | SIM | SIM | SIM |
| Controle financeiro do escritório | — | SIM | SIM | SIM |
| Controle de inadimplência | — | SIM | SIM | SIM |
| Contas a pagar e a receber | — | Limite de 1 opção | SIM | SIM |
| Centros de custos | — | Limite de 1 opção | SIM | SIM |
| Contas e cartões | — | Limite de 1 opção | SIM | SIM |
| Emissão de cobranças por boleto e cartão | — | SIM | SIM | SIM |
| Automação para cobrança recorrente | — | SIM | SIM | SIM |
| Notificações de cobranças (E-mail, SMS, WhatsApp) | — | SIM | SIM | SIM |
| Integração com Asaas | — | SIM | SIM | SIM |
| Fluxo de caixa por conta bancária | — | — | SIM | SIM |
| Relatórios financeiros com agrupamento DRE e DFC | — | — | SIM | SIM |
| Setores/Unidades | — | — | — | SIM |

#### Editor de documentos
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Cadastro ilimitado de modelos | SIM | SIM | SIM | SIM |
| Gerador de documentos com preenchimento automático | SIM | SIM | SIM | SIM |
| Editor de documentos online | SIM | SIM | SIM | SIM |
| Gerador de PDF | SIM | SIM | SIM | SIM |
| Editor integrado ao processo | SIM | SIM | SIM | SIM |

#### Gestão
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Controle de produtividade pessoal básico | SIM | SIM | SIM | SIM |
| Controle de atividades dos colaboradores | SIM | SIM | SIM | SIM |
| Tarefas pendentes por colaborador | SIM | SIM | SIM | SIM |
| Relatório de novos clientes e processos | — | SIM | SIM | SIM |
| Relatório de processos ganhos e perdidos | — | SIM | SIM | SIM |
| Livro de ponto online | — | SIM | SIM | SIM |
| Relatório de processos ajuizados | — | SIM | SIM | SIM |
| Relatório de novos contratos | — | SIM | SIM | SIM |

#### Business Intelligence (exclusivo Elite)
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Controle de produtividade pessoal avançado | — | — | — | SIM |
| Tarefas cumpridas em D-1, D-0 e fora do prazo | — | — | — | SIM |
| Processos ganhos e perdidos | — | — | — | SIM |
| Controle de fechamento de contratos | — | — | — | SIM |
| Controle de processos ajuizados | — | — | — | SIM |
| Controle completo do estoque de processos | — | — | — | SIM |
| Controle de recontratações | — | — | — | SIM |
| Controle de processos parados há mais de 120 dias | — | — | — | SIM |
| Cálculo automático de rentabilidade por Grupo e Tipo de Ação | — | — | — | SIM |
| Cálculo do tempo de demora do processo | — | — | — | SIM |
| Cálculo do tempo de demora do processo total | — | — | — | SIM |
| Controle da safra de processo por ano | — | — | — | SIM |

#### Apps & Integrações
| Recurso | Ess. | B. Jur. | B. Max | Elite |
|---|---|---|---|---|
| Agenda do Google, Apple e Outlook | SIM | SIM | SIM | SIM |
| Asaas | — | SIM | SIM | SIM |
| RD Station Marketing | SIM | SIM | SIM | SIM |

### 10.3 Suporte por plano
- **Essencial:** somente chat interno.
- **Banca Jurídica / Banca Max / Elite:** chat + e-mail + WhatsApp.
- **Banca Jurídica+:** Consultor de Sucesso; **Elite:** Consultor com plano personalizado.

---

## 11. Roteiro de replicação

### 11.1 Entidades do banco (proposta mínima)

```
accounts            (escritório: razão social, fantasia, CNPJ, endereço, e-mails, site, timezone, logo, plano)
users               (+ role, occupations_id, financial, salary, admissão/demissão, jornada, OAB, certificado A1)
squads / squad_user (times)
occupations         (66)
customers           (+ representative_* , type PF/PJ)
customers_origins   (origens)
maritalstatus       (6)
groups              (grupos de ação)
type_lawsuits       (FK groups)
steps               (9 fases, fixas)
stages              (FK steps, + workflows_id, enable_stagnant_days, stagnant_days)
lawsuits            (FK users, groups, type_lawsuits, steps, stages, courts, systems)
lawsuit_customer    (N:N, com flag parte contrária)
courts              (182)
systems             (13)
tasks               (catálogo: complexity, time, reward, steps_id, schedule)
posts               (tarefas/compromissos/intimações/comentários — FK lawsuits, tasks)
post_user           (guests, completed, important, urgent)
workflows / workflow_steps (task, user, days)
publications        (intimações capturadas)
movements           (andamentos: origin TRIBUNAL|MANUAL)
terms               (termos monitorados: OAB/CPF/CNPJ, tribunal, status, custo)
certificates        (A1 por usuário)
bank_accounts       (type, institutions_id, agency, number, cycle_day, due_day, initial_amount, default)
institutions        (~95)
indexes             (10 grupos DRE)
categories          (FK indexes, type income|expense)
cost_centers
departments         (setores — Elite)
transactions        (FK users, bank_accounts, categories, cost_centers, customers, lawsuits, departments)
documents           (S3: attached_to = task | customer | transaction)
library_documents   (modelos: type contrato|petição|recurso|documento, público/privado)
goals               (meta mensal por grupo de ação)
partners / friendships
notifications_config
access_logs         (registro de acessos)
integrations        (asaas_token, rdstation_token, ical_url por usuário)
```

### 11.2 Ordem de implementação sugerida
1. **Fundação:** accounts, users (perfis + acesso financeiro), occupations, autenticação.
2. **Taxonomias:** steps (fixas) → groups → type_lawsuits → stages → origins → courts → systems.
3. **Contatos** (com PF/PJ e representante) e **Processos** (com N:N de partes).
4. **Tarefas + Taskscore:** catálogo com `complexity × time → reward`, depois `posts` e a caixa de entrada.
5. **CRM Kanban** sobre `steps`/`stages`, com estagnação e mudança de fase por drag & drop.
6. **Financeiro:** indexes → categories → cost_centers → bank_accounts → transactions (com regra `entry_type` × tipo da categoria).
7. **Modelos:** editor rich text + engine de variáveis + geração de PDF.
8. **Workflow** e depois **Flowter** (webhooks outbound com os dois payloads da seção 8).
9. **Monitoramento:** termos, certificado A1, captura, criação de tarefa de intimação, roteamento por grupo/responsável.
10. **Relatórios** e por fim **BI** (agregações com cache de 8 h).
11. **API pública** espelhando os 22 endpoints, começando por `/settings`.

### 11.3 Regras de negócio que não podem faltar
- **Taskscore:** pontuação sugerida automaticamente a partir de complexidade × tempo médio (ex.: simples 15 min = 8 pts; complexa 1 h = 150 pts), editável manualmente. Só **Gestor** cria/edita tarefas do catálogo.
- **Tipo de ação herda o grupo**; **etapa herda a fase** — nunca enviar `group_id`/`steps_id` diretamente.
- **`entry_type` deve casar com o tipo da categoria** (income↔CRÉDITO, expense↔DÉBITO).
- **`lawsuits_id` em transação exige `customers_id`.**
- **CEP com hífen obrigatório**; telefone com DDD e **sem** código do país.
- **CNJ é validado contra as bases do Judiciário** — números inventados são rejeitados.
- **Valores monetários com vírgula decimal**; ponto é descartado.
- **`description` de transação é forçada para MAIÚSCULAS**; `competence` é derivada de `date_due`.
- **Estagnação** é por etapa, com nº de dias configurável.
- **Distribuição de intimação:** responsável do Grupo de Ação → senão Responsável Geral.
- **Sincronização de agenda é unidirecional** e só inclui tarefas com "Mostrar na agenda".
- **Nuvem:** cobrar excedente por GB acima do limite do plano.

---

## Anexo — Fontes consultadas

| Fonte | Cobertura |
|---|---|
| `advbox.com.br/software-juridico` | Posicionamento, pilares, IA |
| `advbox.com.br/planos` | Matriz completa de 90+ funcionalidades × 4 planos |
| `advbox.com.br/ia-para-escritorio-de-advocacia` | Justin-e, Donna, Agentes IA, Flowter, preços |
| `advbox.com.br/api` | Proposta comercial da API |
| `advbox.com.br/perguntas-frequentes` | 11 FAQs |
| `api.softwareadvbox.com.br/docs` + `/llms-full.txt` | 22 endpoints, campos, validações, changelog v1.0.0→v1.24.0 |
| `guia.advbox.com.br` | 112 artigos (integrações, Flowter, DJEN, Taskscore, workflow, BI, certificado A1, Previdia) |
| `app.advbox.com.br` (logado) | Navegação real, 16 seções de configuração, todos os formulários e taxonomias |
