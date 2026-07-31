# Autenticação
URL: /docs/autenticacao

🔐 Bearer Token [#-bearer-token]

Todas as requisições requerem autenticação via **Bearer Token** no header `Authorization`:

```http
Authorization: Bearer SEU_TOKEN_AQUI
```

<Callout type="warning">
  **Importante:** O token de acesso é fornecido pela ADVBOX para parceiros e integradores aprovados. Não compartilhe seu token.
</Callout>

🛡️ Segurança do Token [#️-segurança-do-token]

O token de acesso é a chave de entrada da sua integração — qualquer pessoa que o possua pode fazer requisições em nome da sua conta. Por isso, trate-o com o mesmo cuidado que uma senha.

**Boas práticas:**

* **Nunca exponha o token no código-fonte** — armazene-o em variáveis de ambiente (`.env`) e nunca o versione no Git
* **Nunca inclua o token real em exemplos ou documentações internas** — use sempre um placeholder como `SEU_TOKEN_AQUI`
* **Revogue imediatamente** caso suspeite que o token foi comprometido — entre em contato com a ADVBOX para emissão de um novo
* **Não compartilhe o token por canais inseguros** — evite e-mail, WhatsApp ou qualquer mensagem que possa ser interceptada

⚠️ Atenção ao usar assistentes de IA [#️-atenção-ao-usar-assistentes-de-ia]

Ao usar ferramentas de IA (como Claude, ChatGPT ou Cursor) para apoiar sua integração, tome cuidado:

* **Nunca cole seu token real no chat do assistente** — as conversas podem ser armazenadas e revisadas
* Use sempre o placeholder `SEU_TOKEN_AQUI` nos exemplos que enviar ao assistente
* Substitua pelo token real apenas no seu ambiente local, fora do chat
* Lembre-se: o assistente não precisa do token real para gerar o código — ele só precisa saber onde o token deve ser inserido

***

🧪 Testando a API [#-testando-a-api]

<Callout type="info">
  **Nota sobre CORS:** A funcionalidade "Try it out" não está disponível devido às políticas de CORS da API.
</Callout>

**Ferramentas recomendadas:**

* [Postman](https://www.postman.com/)
* [Insomnia](https://insomnia.rest/)
* cURL (linha de comando)

Todos os endpoints incluem exemplos de requisição e resposta para facilitar os testes.

⚡ Rate Limits [#-rate-limits]

Para garantir a estabilidade do serviço, aplicamos os seguintes limites por conta:

| Método | Limite          | Período            |
| ------ | --------------- | ------------------ |
| GET    | 30 requisições  | Por minuto         |
| POST   | 500 requisições | Por dia (por rota) |
| PUT    | 500 requisições | Por dia            |

<Callout type="info">
  Ao atingir o limite, a API retorna o status **429 Too Many Requests**. Aguarde o período indicado antes de novas requisições.
</Callout>

# Changelog
URL: /docs/changelog

Histórico de mudanças da documentação, da versão mais recente para a mais antiga.
Cada endpoint também exibe a data da sua **última atualização** no topo da própria página.

## Histórico de versões

### v1.24.0 — 07/07/2026 · Novo

Novos endpoints de documentos: listar arquivos anexados (GET /documents, com filtros por nome/cliente/lançamento/tarefa) e gerar a URL temporária de download (GET /documents/{id}/download).

Páginas: getDocuments, downloadDocument

### v1.23.0 — 24/06/2026 · Ajuste

Corrigido o nome do campo de tipos de processo na resposta de GET /settings (`lawsuit_types`). Em POST /transactions, esclarecido que `type` e `competence` são derivados de `entry_type` e `date_due` — não precisam ser enviados.

Páginas: getSettings, createTransaction

### v1.22.0 — 16/06/2026 · Melhoria

Formato de `phone`/`cellphone` documentado com precisão: enviar o número local com DDD, sem o código do país (`55`/`+`).

Páginas: createCustomer

### v1.21.0 — 16/06/2026 · Melhoria

Padronização do formato do campo `amount`: use vírgula como separador decimal (ex: `"250,50"`).

Páginas: createTransaction, updateTransaction

### v1.20.0 — 14/05/2026 · Melhoria

Documentação de GET /last_movements atualizada para refletir o comportamento agrupado das movimentações.

Páginas: getLastMovements

### v1.19.0 — 30/04/2026 · Ajuste

Exemplos de data ajustados em POST /lawsuits/movement.

Páginas: createLawsuitMovement

### v1.18.0 — 29/04/2026 · Melhoria

Descrições dos campos `status_closure`, `exit_production` e `exit_execution` revisadas para maior clareza.

Páginas: getLawsuits, getLawsuitById

### v1.17.0 — 17/04/2026 · Melhoria

Respostas de erro dos endpoints documentadas com exemplos reais.

### v1.16.0 — 13/04/2026 · Melhoria

PUT /lawsuits/{id} documentado com todos os campos disponíveis.

Páginas: updateLawsuit

### v1.15.0 — 09/04/2026 · Melhoria

Exemplos de resposta (GET) adicionados com a estrutura real retornada pela API.

### v1.14.0 — 02/04/2026 · Melhoria

Novos campos adicionados em POST /lawsuits e exemplos padronizados.

Páginas: createLawsuit

### v1.13.0 — 23/03/2026 · Melhoria

Documentação de transações e tarefas ampliada e validada.

Páginas: getTransactions, createTransaction, getPosts, createPost

### v1.12.0 — 20/03/2026 · Melhoria

Campos adicionais documentados em POST /customers.

Páginas: createCustomer

### v1.11.0 — 06/03/2026 · Novo

Novo endpoint GET /transactions/{id}; atualização de transações disponível em /transactions/{id}.

Páginas: getTransactionById, updateTransaction

### v1.10.0 — 11/02/2026 · Novo

Novo endpoint PUT /transactions; caminho dos endpoints de clientes padronizado para /customers.

Páginas: updateTransaction, getCustomers, createCustomer, getCustomerById, getCustomersBirthdays

### v1.9.0 — 10/02/2026 · Novo

Novo endpoint POST /transactions.

Páginas: createTransaction

### v1.8.0 — 06/02/2026 · Melhoria

Comportamento de GET /customers/{id} documentado: retorna 404 quando o cliente não é encontrado.

Páginas: getCustomerById

### v1.7.0 — 16/01/2026 · Melhoria

Visibilidade dos parâmetros aprimorada com marcadores [Required] e [Optional].

### v1.6.0 — 09/01/2026 · Melhoria

Comportamento dos filtros de GET /posts documentado em detalhe.

Páginas: getPosts

### v1.5.0 — 08/01/2026 · Melhoria

Referência da API e documentação de GET /settings aprimoradas.

Páginas: getSettings

### v1.4.0 — 06/01/2026 · Melhoria

Endpoints restantes documentados; exemplos com dados genéricos.

### v1.3.0 — 02/01/2026 · Novo

Endpoints de processos (Lawsuits) adicionados à documentação.

Páginas: getLawsuits, createLawsuit, getLawsuitById, updateLawsuit, getHistoryByLawsuitId, getMovementsByLawsuitId, getPublicationsByLawsuitId

### v1.2.0 — 30/12/2025 · Novo

Endpoints de clientes (Contacts) adicionados à documentação.

Páginas: getCustomers, createCustomer, getCustomerById, getCustomersBirthdays

### v1.1.0 — 26/12/2025 · Melhoria

Documentação de GET /lawsuits aprimorada.

Páginas: getLawsuits

### v1.0.0 — 26/11/2025 · Novo

Versão inicial da documentação da API ADVBOX.

# Bem-vindo
URL: /docs

Bem-vindo à API ADVBOX [#bem-vindo-à-api-advbox]

API REST oficial para integração com a plataforma ADVBOX — sistema completo de gestão jurídica.

<Callout type="info">
  **Acesso exclusivo** para parceiros e integradores aprovados pela ADVBOX.
</Callout>

🚀 Visão Geral [#-visão-geral]

A API ADVBOX permite que você integre seu sistema com nossa plataforma, possibilitando:

* **Gestão de Processos Judiciais** — Criar, consultar e atualizar processos
* **Gerenciamento de Contatos** — Clientes, partes processuais e relacionados
* **Acompanhamento de Movimentações** — Publicações, histórico e andamentos processuais
* **Controle de Tarefas** — Organização de atividades e prazos
* **Gestão Financeira** — Transações, honorários e controle de custos

🌐 URL Base [#-url-base]

```
https://app.advbox.com.br/api/v1
```

📚 Comece a Integrar [#-comece-a-integrar]

<Cards>
  <Card title="🔐 Autenticação" href="/docs/autenticacao" description="Como autenticar suas requisições e entender os rate limits" />

  <Card title="📖 Referência Completa" href="/docs/referencia" description="Explore todos os 22 endpoints organizados por categoria" />

  <Card title="🤖 Uso com IAs" href="/docs/uso-com-ias" description="Gere código de integração usando Claude, ChatGPT ou Cursor" />

  <Card title="⚙️ Settings" href="/docs/settings/getSettings" description="Consulte primeiro para obter os IDs necessários para outros endpoints" />
</Cards>

# Visão Geral
URL: /docs/referencia

Esta página reúne todos os 22 endpoints da API ADVBOX organizados por área. Use como ponto de partida para encontrar o recurso que precisa e acessar a documentação detalhada de cada operação.

<Callout type="warning">
  **⚙️ Antes de começar:** A maioria dos endpoints que criam ou atualizam registros exige IDs específicos da sua conta — como o ID do usuário responsável, da fase processual ou da categoria financeira. Esses IDs são obtidos através do endpoint **Settings**, listado ao final desta página. Consulte-o primeiro.
</Callout>

<Callout type="info">
  **🤖 Gerando código de integração?** Cada endpoint tem um botão **Copiar para IA** no topo da página. Cole o conteúdo no assistente de sua preferência para gerar o código automaticamente. Para integrações que envolvem múltiplos endpoints, use a <a href="/llms-full.txt" target="_blank">Documentação Completa</a> com todos os 22 endpoints de uma vez.
</Callout>

📁 Contatos (Customers) [#-contatos-customers]

Gerencie clientes, fornecedores e contatos do escritório. Crie novos leads, busque por CPF/CNPJ/email, e consulte aniversariantes para campanhas de relacionamento.

**IDs necessários (obter em `/settings`):**

* `users_id` - ID do usuário responsável pelo contato
* `customers_origins_id` - ID da origem do lead (Indicação, Facebook, Google, etc.)

<Cards>
  <Card title="GET /customers" href="/docs/customers/getCustomers" description="Listar todos os clientes com filtros avançados (nome, email, CPF, etc.)" />

  <Card title="POST /customers" href="/docs/customers/createCustomer" description="Criar novo contato no sistema" />

  <Card title="GET /customers/{id}" href="/docs/customers/getCustomerById" description="Buscar dados completos de um contato específico por ID" />

  <Card title="GET /customers/birthdays" href="/docs/customers/getCustomersBirthdays" description="Consultar aniversariantes do mês atual ou específico" />
</Cards>

***

⚖️ Processos (Lawsuits) [#️-processos-lawsuits]

Gerencie processos judiciais completos: criação, atualização, consulta de movimentações, histórico processual e publicações. Filtre por cliente, fase processual, tipo de ação, responsável, datas e muito mais.

**IDs necessários (obter em `/settings`):**

* `users_id` - ID do usuário responsável pelo processo
* `customers_id` - ID do cliente vinculado ao processo (obter em `/customers`)
* `stages_id` - ID da fase processual (ex: Planejamento, Produção, Andamento)
* `type_lawsuits_id` - ID do tipo de processo (ex: Trabalhista, Cível, Criminal)

<Cards>
  <Card title="GET /lawsuits" href="/docs/lawsuits/getLawsuits" description="Listar processos com 22+ filtros (cliente, fase, tipo, datas, etc.)" />

  <Card title="POST /lawsuits" href="/docs/lawsuits/createLawsuit" description="Criar novo processo judicial no sistema" />

  <Card title="GET /lawsuits/{id}" href="/docs/lawsuits/getLawsuitById" description="Buscar dados completos de um processo específico" />

  <Card title="PUT /lawsuits/{id}" href="/docs/lawsuits/updateLawsuit" description="Atualizar dados de um processo existente" />

  <Card title="GET /history/{lawsuit_id}" href="/docs/lawsuits/getHistoryByLawsuitId" description="Consultar histórico completo de um processo" />

  <Card title="GET /movements/{lawsuit_id}" href="/docs/lawsuits/getMovementsByLawsuitId" description="Listar todas as movimentações de um processo" />

  <Card title="POST /movements" href="/docs/lawsuits/createLawsuitMovement" description="Adicionar nova movimentação manual a um processo" />

  <Card title="GET /last_movements" href="/docs/lawsuits/getLastMovements" description="Consultar o último andamento de cada processo (agrupado por processo)" />
</Cards>

***

📋 Tarefas (Posts) [#-tarefas-posts]

Gerencie posts, anotações e atividades relacionadas aos processos e clientes. Crie lembretes, registre interações importantes e acompanhe o histórico de comunicação.

**IDs necessários (obter em `/settings`):**

* `tasks_id` - ID do tipo de tarefa (ex: 1º Contato com Lead, Acompanhar Citação, Protocolar Petição)

<Cards>
  <Card title="GET /posts" href="/docs/tasks/getPosts" description="Listar posts e anotações do sistema" />

  <Card title="POST /posts" href="/docs/tasks/createPost" description="Criar novo post ou anotação" />
</Cards>

***

📰 Publicações (Publications) [#-publicações-publications]

Consulte publicações oficiais dos Diários da Justiça vinculadas aos processos judiciais. Acompanhe intimações, sentenças e demais publicações capturadas automaticamente pelo sistema.

<Cards>
  <Card title="GET /publications/{lawsuit_id}" href="/docs/publications/getPublicationsByLawsuitId" description="Listar todas as publicações de um processo específico" />
</Cards>

***

💰 Transações (Transactions) [#-transações-transactions]

Gerencie transações financeiras do escritório: honorários recebidos, despesas processuais, custas judiciais e outras movimentações. Crie novas transações (receitas/despesas), atualize valores e datas, e consulte com filtros avançados.

**IDs necessários (obter em `/settings`):**

* `users_id` - ID do usuário responsável
* `debit_account` - ID da conta bancária (campo `financial.banks[]`)
* `categories_id` - ID da categoria financeira (campo `financial.categories[]`)
* `cost_centers_id` - ID do centro de custo (campo `financial.cost_centers[]`)

<Cards>
  <Card title="GET /transactions" href="/docs/transactions/getTransactions" description="Listar transações financeiras com filtros por data, tipo e status" />

  <Card title="GET /transactions/{id}" href="/docs/transactions/getTransactionById" description="Buscar dados completos de uma transação específica por ID" />

  <Card title="POST /transactions" href="/docs/transactions/createTransaction" description="Criar nova transação (receita ou despesa)" />

  <Card title="PUT /transactions/{id}" href="/docs/transactions/updateTransaction" description="Atualizar transação existente (valor, vencimento, status de pagamento)" />
</Cards>

***

📎 Documentos (Documents) [#-documentos-documents]

Consulte e baixe os arquivos anexados aos registros da conta (tarefas, clientes e lançamentos financeiros). Liste os documentos por filtro e gere uma URL temporária para download direto da Amazon S3.

<Cards>
  <Card title="GET /documents" href="/docs/documents/getDocuments" description="Listar documentos anexados, filtrando por nome, cliente, lançamento ou tarefa" />

  <Card title="GET /documents/{id}/download" href="/docs/documents/downloadDocument" description="Gerar a URL temporária (S3, válida por 5 min) para baixar um documento" />
</Cards>

***

⚙️ Configurações (Settings) [#️-configurações-settings]

**🔑 ENDPOINT ESSENCIAL** - Consulte PRIMEIRO antes de usar outros endpoints!

Este endpoint retorna todos os IDs e dados cadastrais da sua conta necessários para criar/atualizar registros em outros endpoints.

📋 O que este endpoint retorna: [#-o-que-este-endpoint-retorna]

| Campo               | Descrição                                       | Usado em                                     |
| ------------------- | ----------------------------------------------- | -------------------------------------------- |
| **`users`**         | Lista de usuários do escritório                 | /customers, /lawsuits, /posts, /transactions |
| **`origins`**       | Origens de leads (ex: Facebook, Indicação)      | /customers (campo `customers_origins_id`)    |
| **`tasks`**         | Tipos de tarefas cadastradas                    | /posts (campo `tasks_id`)                    |
| **`stages`**        | Fases processuais (ex: Planejamento, Andamento) | /lawsuits (campo `stages_id`)                |
| **`lawsuit_types`** | Tipos de processo (ex: Trabalhista, Cível)      | /lawsuits (campo `type_lawsuits_id`)         |

💡 Como usar: [#-como-usar]

1. **Faça uma requisição GET `/settings`**
2. **Guarde os IDs retornados** (users, origins, tasks, stages, type\_lawsuits)
3. **Use esses IDs** ao criar/atualizar contatos, processos e tarefas

**Exemplo:** Para criar um contato, você precisa informar `users_id` (responsável) e `customers_origins_id` (origem). Ambos vêm do `/settings`.

<Cards>
  <Card title="GET /settings" href="/docs/settings/getSettings" description="Obter todos os IDs e configurações da conta (usuários, origens, tipos de processo, fases, tarefas)" />
</Cards>

***

📊 Resumo dos Recursos [#-resumo-dos-recursos]

| Recurso          | Endpoints | Principais Operações                         |
| ---------------- | --------- | -------------------------------------------- |
| **Customers**    | 4         | Listar, Criar, Buscar, Aniversários          |
| **Lawsuits**     | 8         | CRUD completo + Histórico/Movimentações      |
| **Posts**        | 2         | Listar e Criar tarefas                       |
| **Publications** | 1         | Consultar publicações                        |
| **Transactions** | 4         | Listar, Buscar, Criar e Atualizar transações |
| **Documents**    | 2         | Listar e baixar anexos                       |
| **Settings**     | 1         | Consultar configurações                      |

**Total:** 22 endpoints documentados

# Uso com IAs
URL: /docs/uso-com-ias

🤖 Como funciona [#-como-funciona]

Você pode usar o assistente de IA de sua preferência para gerar o código de integração com a API ADVBOX. Para isso, basta fornecer ao assistente a documentação do endpoint que deseja usar — ele terá todas as informações necessárias para escrever o código por você.

***

📋 Botão "Copiar para IA" [#-botão-copiar-para-ia]

Cada página de endpoint possui um botão &#x2A;*"Copiar para IA"** logo abaixo do título. Ao clicar, o conteúdo completo daquele endpoint é copiado — incluindo parâmetros, campos obrigatórios, exemplos de requisição e resposta.

**Como usar:**

1. Acesse a página do endpoint desejado
2. Clique em **Copiar para IA**
3. Cole no assistente de sua preferência
4. Descreva o que você precisa fazer com esse endpoint — o assistente vai gerar o código com base na documentação copiada.

<Callout type="info">
  Use também o botão **Abrir com IA** para abrir o assistente diretamente já com o contexto da página atual.
</Callout>

***

📄 Documentação completa [#-documentação-completa]

Para integrações que envolvem mais de um endpoint, você pode fornecer toda a documentação de uma vez:

<Cards>
  <Card title="📄 Documentação Completa" href="/llms-full.txt" external="true" description="Todos os 22 endpoints em texto puro — ideal para colar no contexto do assistente" />

  <Card title="🔗 Índice de Páginas" href="/llms.txt" external="true" description="Lista com link para cada endpoint — útil para assistentes que conseguem acessar URLs" />
</Cards>

***

💡 Dicas [#-dicas]

* **Seja específico** — quanto mais detalhes você der sobre o que precisa, melhor será o resultado
* **Descreva o fluxo completo** — se a integração envolver mais de um endpoint, explique a ordem das operações
* **Peça tratamento de erros** — solicite que o código cubra situações inesperadas, como falhas de autenticação ou indisponibilidade da API
* **Nunca compartilhe seu token real** — use sempre um placeholder como `SEU_TOKEN_AQUI` nos exemplos que enviar ao assistente. Substitua pelo token real apenas no seu ambiente local, fora do chat.

<Callout type="warning">
  **Segurança do token:** As conversas com assistentes de IA podem ser armazenadas. Nunca cole seu token real no chat — o assistente não precisa dele para gerar o código, apenas para saber onde ele deve ser inserido. Consulte a página de [Autenticação](/docs/autenticacao) para mais boas práticas.
</Callout>

<Callout type="info">
  A Documentação Completa é gerada automaticamente — qualquer atualização nos endpoints é refletida sem necessidade de edição manual.
</Callout>

# Crie um novo contato
URL: /docs/customers/createCustomer
Última atualização: 16/06/2026 · doc v1.22.0 — Formato de `phone`/`cellphone` documentado com precisão: enviar o número local com DDD, sem o código do país (`55`/`+`). (histórico completo: /docs/changelog)

Cria um novo contato no sistema.

**Campos obrigatórios:**

* `users_id` - ID do usuário responsável (deve pertencer ao escritório)
* `customers_origins_id` - ID da origem do contato (deve pertencer ao escritório)
* `name` - Nome do contato

**Campos opcionais — Pessoais:**

* `email`, `identification` (CPF/CNPJ), `phone`, `cellphone`
* `birthdate` (YYYY-MM-DD), `gender`, `occupation`, `document`

**Campos opcionais — Endereço:**

* `street`, `region`, `city`, `state`, `country`, `postalcode`

**Campos opcionais — Trabalhistas:**

* `number_ctps`, `number_pis`, `number_cid`, `notes`

**Validações importantes:**

* `identification` (CPF/CNPJ) é validado com algoritmo real e bloqueia duplicação
* `email` é validado mas permite duplicação
* `postalcode` DEVE ter formatação 99999-999 (não aceita sem hífen)
* `birthdate` deve ser no formato YYYY-MM-DD
* `phone`/`cellphone`: número local com **DDD**, com ou sem formatação. ⚠️ **Sem o código do país** (`55`/`+`) — o formato internacional não é rejeitado, mas vira `ERROR`; sem DDD retorna 422

## POST /customers

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Crie um novo contato

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

**Campos obrigatórios:** users_id, customers_origins_id, name

| Campo | Tipo | Descrição |
|-------|------|----------|
| users_id | integer | **[Required]** ID do usuário responsável (deve existir e pertencer ao escritório) |
| customers_origins_id | integer | **[Required]** ID da origem do contato (deve existir e pertencer ao escritório) |
| name | string | **[Required]** Nome completo do contato |
| email | string (email) | **[Optional]** Email do contato. Validado mas permite duplicação. |
| document | string | **[Optional]** Número do documento do contato (campo livre, sem validação) |
| identification | string | **[Optional]** CPF ou CNPJ do contato. Aceita com ou sem formatação. Validado com algoritmo real e bloqueia duplicação. |
| phone | string | **[Optional]** Telefone fixo com DDD (10 dígitos). Ex: `(11) 3333-4444` ou `1133334444`. |
| cellphone | string | **[Optional]** Celular com DDD (11 dígitos). Ex: `(31) 98588-5389` ou `31985885389`. |
| birthdate | string (date) | **[Optional]** Data de nascimento no formato YYYY-MM-DD |
| occupation | string | **[Optional]** Profissão ou ocupação do contato |
| postalcode | string | **[Optional]** CEP no formato 99999-999 (hífen obrigatório) |
| city | string | **[Optional]** Cidade do contato |
| state | string | **[Optional]** Estado do contato (sigla com 2 letras) |
| notes | string | **[Optional]** Observações ou notas adicionais sobre o contato |
| gender | string | **[Optional]** Gênero do contato (ex: M, F) |
| street | string | **[Optional]** Logradouro do contato (rua, avenida, etc.) |
| region | string | **[Optional]** Bairro do contato |
| country | string | **[Optional]** País do contato (ex: BRASIL) |
| number_ctps | string | **[Optional]** Número da Carteira de Trabalho (CTPS) |
| number_pis | string | **[Optional]** Número do PIS/PASEP |
| number_cid | string | **[Optional]** Código CID (classificação de doença) |

#### Exemplo: minimo — Criação mínima (campos obrigatórios)

```json
{
  "users_id": 123456,
  "customers_origins_id": 789012,
  "name": "Maria Silva"
}
```

#### Exemplo: completo — Criação completa (todos os campos)

```json
{
  "users_id": 123456,
  "customers_origins_id": 789012,
  "name": "Maria Silva",
  "email": "maria.silva@example.com",
  "identification": "123.456.789-01",
  "phone": "(11) 3333-4444",
  "cellphone": "(11) 98888-7777",
  "birthdate": "1990-05-15",
  "occupation": "Advogada",
  "postalcode": "01234-567",
  "street": "Rua Exemplo, 123",
  "region": "Centro",
  "city": "São Paulo",
  "state": "SP",
  "country": "BRASIL",
  "gender": "F",
  "number_ctps": "12345",
  "number_pis": "67890",
  "number_cid": "CID123",
  "notes": "Contato preferencial"
}
```

### Respostas

#### 201 — Contato criado com sucesso

##### Exemplo

```json
{
  "success": true,
  "customers_id": 12345678
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: campos_obrigatorios — Campos obrigatórios ausentes

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "users_id": [
      "The responsible user is required"
    ],
    "name": [
      "The customer name field is required"
    ],
    "customers_origins_id": [
      "The customer origin is required"
    ]
  }
}
```

##### Exemplo: users_id_invalido — Usuário não pertence ao escritório

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "users_id": [
      "You must enter a user associated with your office"
    ]
  }
}
```

##### Exemplo: origin_invalida — Origem não pertence ao escritório

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "customers_origins_id": [
      "You must enter an origin associated with your office"
    ]
  }
}
```

##### Exemplo: nome_duplicado — Cliente com mesmo nome já existe

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "duplicate": [
      "Client with this name already exists."
    ]
  }
}
```

##### Exemplo: email_invalido — Formato de e-mail inválido

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "email": [
      "The email is invalid"
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```

#### 500 — Erro interno do servidor

_Sem corpo de resposta._



# Obtenha um contato pelo ID
URL: /docs/customers/getCustomerById
Última atualização: 11/02/2026 · doc v1.10.0 — Novo endpoint PUT /transactions; caminho dos endpoints de clientes padronizado para /customers. (histórico completo: /docs/changelog)

Retorna os dados completos de um contato específico baseado no seu ID único.

**Observações importantes:**

* Data de nascimento retorna no formato `DD/MM/YYYY`
* Campos de texto retornam em MAIÚSCULAS
* Inclui array de processos associados (`lawsuits`)

## GET /customers/{id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha um contato pelo ID

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| id | integer | Sim | **[Required]** ID único do contato |

### Respostas

#### 200 — Contato encontrado com sucesso

##### Exemplo: encontrado — Contato encontrado

```json
{
  "id": 9000001,
  "name": "JOAO PEREIRA",
  "identification": "111.222.333-44",
  "gender": "M",
  "cellphone": "(11) 98888-1234",
  "phone": "(11) 3333-5678",
  "email": "joao.pereira@example.com",
  "occupation": "ENGENHEIRO",
  "street": "RUA DAS FLORES, 123",
  "postalcode": "01234-567",
  "region": "JARDIM PRIMAVERA",
  "city": "SAO PAULO",
  "state": "SP",
  "country": "BRASIL",
  "birthdate": "15/05/1985",
  "number_ctps": null,
  "number_pis": null,
  "number_cid": null,
  "notes": "Cliente referenciado pelo parceiro",
  "origin": "ESCRITORIO",
  "created_at": "2026-01-15 10:30:00",
  "lawsuits": [
    {
      "lawsuit_id": 1234501,
      "process_number": "0001234-56.2026.5.15.0001",
      "protocol_number": null
    },
    {
      "lawsuit_id": 1234502,
      "process_number": null,
      "protocol_number": "PROT-2026-002"
    }
  ]
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 404 — Registro não encontrado

##### Exemplo

```json
{
  "error": "Customer not found"
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha uma lista de contatos
URL: /docs/customers/getCustomers
Última atualização: 11/02/2026 · doc v1.10.0 — Novo endpoint PUT /transactions; caminho dos endpoints de clientes padronizado para /customers. (histórico completo: /docs/changelog)

Retorna uma lista de contatos com opções avançadas de filtro e paginação.

**Como funcionam os filtros:**

* Múltiplos filtros são combinados com **AND** (interseção)
* Filtros de texto são **case-insensitive**
* `name` aceita **busca parcial** (qualquer parte do nome)
* Outros campos requerem **busca exata** (email, city, state, document, occupation)
* `identification` aceita CPF **com ou sem pontuação**
* `phone` aceita **com ou sem formatação** (10-11 dígitos)
* Filtros de data (`created_start` e `created_end`) **devem ser usados juntos**

A resposta inclui `totalCount` (total de registros), `data` (array de contatos) e informações de paginação (`limit` e `offset`).

## GET /customers

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha uma lista de contatos

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| name | string | Não | **[Optional]** Busca parcial no nome do contato (qualquer parte do nome). |
| phone | string | Não | **[Optional]** Telefone do contato. Aceita 10-11 dígitos com ou sem formatação. Retorna erro se formato inválido. |
| identification | string | Não | **[Optional]** CPF/CNPJ do contato. Aceita com ou sem pontuação/traços. |
| document | string | Não | **[Optional]** Número do documento do contato (busca exata). |
| email | string (email) | Não | **[Optional]** E-mail do contato (busca exata, case-insensitive). |
| city | string | Não | **[Optional]** Cidade do contato (busca exata, case-insensitive). |
| state | string | Não | **[Optional]** Sigla do estado do contato (ex: SC, SP, PR). |
| occupation | string | Não | **[Optional]** Ocupação ou profissão do contato (busca exata). |
| birthdays | boolean | Não | **[Optional]** Filtra contatos aniversariantes do mês atual (true/false). |
| created_start | string (date) | Não | **[Optional]** Data inicial do range (formato: YYYY-MM-DD). DEVE ser usado COM created_end. |
| created_end | string (date) | Não | **[Optional]** Data final do range (formato: YYYY-MM-DD). DEVE ser usado COM created_start. |
| limit | integer | Não | **[Optional]** Número máximo de registros a retornar (padrão: 1000, máximo: 1000). |
| offset | integer | Não | **[Optional]** Número de registros a pular antes de iniciar a resposta (padrão: 0). |

### Respostas

#### 200 — Lista de contatos retornada com sucesso

##### Exemplo: sem_filtro — Lista sem filtro (primeiros resultados)

```json
{
  "offset": 0,
  "limit": 10,
  "totalCount": 87,
  "data": [
    {
      "id": 9000001,
      "name": "JOAO PEREIRA",
      "identification": "111.222.333-44",
      "document": null,
      "cellphone": "(11) 98888-1234",
      "gender": null,
      "civil_status": null,
      "phone": null,
      "email": null,
      "occupation": null,
      "street": null,
      "postalcode": null,
      "region": null,
      "city": null,
      "state": "SP",
      "country": "BRASIL",
      "birthdate": "15/05/1985",
      "number_ctps": null,
      "number_pis": null,
      "number_cid": null,
      "notes": null,
      "origin": "ESCRITORIO",
      "created_at": "2026-01-15 10:30:00",
      "lawsuits": [
        {
          "lawsuit_id": 1234501,
          "process_number": "0001234-56.2026.5.15.0001",
          "protocol_number": null
        }
      ]
    },
    {
      "id": 9000002,
      "name": "ANA COSTA",
      "identification": null,
      "document": null,
      "cellphone": "(21) 97777-5678",
      "gender": null,
      "civil_status": null,
      "phone": null,
      "email": null,
      "occupation": null,
      "street": null,
      "postalcode": null,
      "region": null,
      "city": null,
      "state": "RJ",
      "country": "BRASIL",
      "birthdate": "",
      "number_ctps": null,
      "number_pis": null,
      "number_cid": null,
      "notes": null,
      "origin": "INDICACAO",
      "created_at": "2026-01-15 10:30:00",
      "lawsuits": []
    }
  ],
  "query": {}
}
```

##### Exemplo: com_filtro — Lista com filtro por nome

```json
{
  "offset": 0,
  "limit": 10,
  "totalCount": 1,
  "data": [
    {
      "id": 9000001,
      "name": "JOAO PEREIRA",
      "identification": "111.222.333-44",
      "document": null,
      "cellphone": "(11) 98888-1234",
      "gender": null,
      "civil_status": null,
      "phone": null,
      "email": null,
      "occupation": null,
      "street": null,
      "postalcode": null,
      "region": null,
      "city": null,
      "state": "SP",
      "country": "BRASIL",
      "birthdate": "15/05/1985",
      "number_ctps": null,
      "number_pis": null,
      "number_cid": null,
      "notes": null,
      "origin": "ESCRITORIO",
      "created_at": "2026-01-15 10:30:00",
      "lawsuits": [
        {
          "lawsuit_id": 1234501,
          "process_number": "0001234-56.2026.5.15.0001",
          "protocol_number": null
        }
      ]
    }
  ],
  "query": {
    "name": "JOAO PEREIRA"
  }
}
```

##### Exemplo: vazio — Nenhum contato encontrado

```json
{
  "offset": 0,
  "limit": 10,
  "totalCount": 0,
  "data": [],
  "query": {
    "name": "NOME INEXISTENTE"
  }
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha aniversariantes do mês
URL: /docs/customers/getCustomersBirthdays
Última atualização: 11/02/2026 · doc v1.10.0 — Novo endpoint PUT /transactions; caminho dos endpoints de clientes padronizado para /customers. (histórico completo: /docs/changelog)

Retorna lista de contatos com aniversário no **mês atual**.

**Observações importantes:**

* Sempre retorna aniversários do **mês atual**
* Data de nascimento retorna no formato `DD/MM/YYYY`
* Campos de texto retornam em MAIÚSCULAS
* Paginação funciona normalmente (limit e offset)
* Limit máximo é 1000

## GET /customers/birthdays

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha aniversariantes do mês

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| month | integer | Não | **[Optional]** Mês para filtrar aniversariantes (1-12). |
| limit | integer | Não | **[Optional]** Número máximo de registros a retornar (padrão e máximo: 1000) |
| offset | integer | Não | **[Optional]** Número de registros a pular para paginação |

### Respostas

#### 200 — Lista de aniversários do mês atual retornada com sucesso

##### Exemplo: com_aniversarios — Contatos com aniversario no mes atual

```json
{
  "offset": 0,
  "limit": 1000,
  "totalCount": 2,
  "data": [
    {
      "id": 9000001,
      "name": "JOAO PEREIRA",
      "identification": "111.222.333-44",
      "document": null,
      "cellphone": "(11) 98888-1234",
      "gender": "M",
      "civil_status": "CASADO(A)",
      "phone": null,
      "email": "joao.pereira@example.com",
      "occupation": "ENGENHEIRO",
      "street": null,
      "postalcode": null,
      "region": null,
      "city": "SAO PAULO",
      "state": "SP",
      "country": "BRASIL",
      "birthdate": "15/04/1985",
      "number_ctps": null,
      "number_pis": null,
      "number_cid": null,
      "notes": null,
      "origin": "ESCRITORIO",
      "created_at": "2026-01-15 10:30:00",
      "lawsuits": [
        {
          "lawsuit_id": 1234501,
          "process_number": null,
          "protocol_number": null
        }
      ]
    }
  ],
  "query": {
    "birthdays": true
  }
}
```

##### Exemplo: sem_aniversarios — Nenhum aniversario no mes atual

```json
{
  "offset": 0,
  "limit": 1000,
  "totalCount": 0,
  "data": [],
  "query": {
    "birthdays": true
  }
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha a URL de download de um documento
URL: /docs/documents/downloadDocument
Última atualização: 07/07/2026 · doc v1.24.0 — Novos endpoints de documentos: listar arquivos anexados (GET /documents, com filtros por nome/cliente/lançamento/tarefa) e gerar a URL temporária de download (GET /documents/{id}/download). (histórico completo: /docs/changelog)

Gera uma **URL temporária assinada** (Amazon S3) para baixar o arquivo. A URL expira em &#x2A;*300 segundos (5 minutos)**.

Use o `id` do documento — ou, de preferência, o caminho `links.download` retornado por `GET /documents` (assim seu código não quebra se a rota mudar).

⚠️ Um `id` inexistente retorna **erro 500**.

## GET /documents/{id}/download

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha a URL de download de um documento

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| id | integer | Sim | ID do documento (obtido em GET /documents). |

### Respostas

#### 200 — URL temporária gerada com sucesso

##### Exemplo

```json
{
  "data": {
    "id": 12345678,
    "name": "peticao_inicial.pdf",
    "temporary_url": "https://advbox.s3.sa-east-1.amazonaws.com/posts/123456789/peticao_inicial.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=300&X-Amz-Signature=...",
    "expires_in_seconds": 300
  }
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo: default

```json
{
  "error": "Unauthenticated."
}
```

#### 500 — Documento não encontrado — a API retorna 500 (não 404) para um `id` inexistente

##### Exemplo: default

```json
{
  "message": "Server Error"
}
```



# Obtenha uma lista de documentos
URL: /docs/documents/getDocuments
Última atualização: 07/07/2026 · doc v1.24.0 — Novos endpoints de documentos: listar arquivos anexados (GET /documents, com filtros por nome/cliente/lançamento/tarefa) e gerar a URL temporária de download (GET /documents/{id}/download). (histórico completo: /docs/changelog)

Retorna os documentos (arquivos anexados) da conta, filtrados por nome, cliente, lançamento financeiro ou tarefa.

**Filtros (pelo menos 1 é obrigatório):**

* `name` - Busca parcial pelo nome do arquivo (case-insensitive, mínimo 3 caracteres; inclui a extensão)
* `customer_id` - ID do cliente
* `transaction_id` - ID do lançamento financeiro (o anexo retorna com `attached_to.type` = `financial`)
* `post_id` - ID da tarefa

Múltiplos filtros são combinados com **AND**. Um filtro por id inexistente retorna `totalCount: 0` (não é erro).

Cada item traz `links.download`, usado no endpoint de download para gerar a URL temporária do arquivo.

## GET /documents

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha uma lista de documentos

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| name | string | Não | **[Optional]** Busca parcial pelo nome do arquivo. Case-insensitive, mínimo 3 caracteres, inclui a extensão. Pelo menos um filtro é obrigatório. |
| customer_id | integer | Não | **[Optional]** ID exato do cliente ao qual o arquivo está anexado. Pelo menos um filtro é obrigatório. |
| transaction_id | integer | Não | **[Optional]** ID exato do lançamento financeiro ao qual o arquivo está anexado. Pelo menos um filtro é obrigatório. |
| post_id | integer | Não | **[Optional]** ID exato da tarefa à qual o arquivo está anexado. Pelo menos um filtro é obrigatório. |
| limit | integer | Não | **[Optional]** Número máximo de itens por página (padrão: 1000). |
| offset | integer | Não | **[Optional]** Número de itens a pular (paginação). |

### Respostas

#### 200 — Lista de documentos retornada com sucesso

##### Exemplo

```json
{
  "offset": 0,
  "limit": 1000,
  "totalCount": 1,
  "data": [
    {
      "id": 12345678,
      "name": "peticao_inicial.pdf",
      "size": "115.3 KB",
      "links": {
        "download": "/api/v1/documents/12345678/download"
      },
      "attached_to": {
        "type": "task",
        "id": 123456789,
        "label": "COMENTÁRIO"
      },
      "uploaded_at": "2024-01-15 12:00:00"
    }
  ],
  "query": {
    "post_id": "123456789",
    "name": null
  }
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo: default

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Requisição inválida - nenhum filtro informado ou filtro inválido

##### Exemplo: sem_filtro — Nenhum filtro informado

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "name": [
      "At least one filter must be provided."
    ]
  }
}
```

##### Exemplo: name_curto — Filtro name com menos de 3 caracteres

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "name": [
      "The name filter must contain at least 3 characters."
    ]
  }
}
```



# Crie um novo processo
URL: /docs/lawsuits/createLawsuit
Última atualização: 02/04/2026 · doc v1.14.0 — Novos campos adicionados em POST /lawsuits e exemplos padronizados. (histórico completo: /docs/changelog)

Cria um novo processo judicial no sistema.

**Campos obrigatórios:**

* `users_id` - ID do usuário responsável (deve pertencer ao escritório)
* `customers_id` - Array de IDs de clientes (mínimo 1, devem pertencer à conta)
* `stages_id` - ID da fase processual (deve pertencer à conta)
* `type_lawsuits_id` - ID do tipo de processo (deve pertencer à conta)

**Validações importantes:**

* `process_number` deve ser um número CNJ válido e oficialmente distribuído. Aceita apenas números reais de processos judiciais.
* `date` deve ser no formato YYYY-MM-DD (valida calendário)
* `folder` aceita no máximo 30 caracteres
* Todos os IDs são validados se pertencem ao escritório autenticado
* `customers_id` deve ter pelo menos 1 elemento (array vazio não é aceito)

**Campos derivados automaticamente (não enviar):**

* `group_id` / `group` — derivados de `type_lawsuits_id`
* `steps_id` / `step` — derivados de `stages_id`

## POST /lawsuits

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Crie um novo processo

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

**Campos obrigatórios:** users_id, customers_id, stages_id, type_lawsuits_id

| Campo | Tipo | Descrição |
|-------|------|----------|
| users_id | string,integer | **[Required]** ID do usuário responsável pelo processo. Deve existir e pertencer ao escritório autenticado. Aceita string ou integer. |
| customers_id | array<integer> | **[Required]** Array de IDs de clientes associados ao processo. Deve conter pelo menos 1 cliente. Todos os IDs devem pertencer à conta autenticada. |
| stages_id | string,integer | **[Required]** ID da fase processual. Deve existir e pertencer à conta autenticada. Aceita string ou integer. |
| type_lawsuits_id | string,integer | **[Required]** ID do tipo de processo. Deve existir e pertencer à conta autenticada. Aceita string ou integer. |
| process_number | string | **[Optional]** Número do processo no formato CNJ (formato: NNNNNNN-DD.AAAA.J.TR.OOOO). Deve ser um número CNJ real e oficialmente distribuído. A API valida se o número existe nas bases do Poder Judiciário. Opcional. |
| protocol_number | string | **[Optional]** Número de protocolo do processo. Campo livre, sem validação de formato. |
| folder | string | **[Optional]** Nome da pasta para organização do processo. Máximo 30 caracteres. |
| date | string (date) | **[Optional]** Data do processo no formato YYYY-MM-DD. A data deve ser válida no calendário. |
| notes | string | **[Optional]** Observações detalhadas sobre o processo, incluindo histórico, notas importantes e contexto adicional para referência futura. |
| fees_expec | integer | **[Optional]** Valor esperado de honorários (em reais, inteiro). |
| fees_money | integer | **[Optional]** Valor de honorários em dinheiro (em reais, inteiro). |
| contingency | integer | **[Optional]** Valor de contingência do processo (em reais, inteiro). |
| status_closure | string (date) | **[Optional]** Data de fechamento do processo no formato YYYY-MM-DD. |
| exit_production | string (date) | **[Optional]** Data do trânsito em julgado no formato YYYY-MM-DD. |
| exit_execution | string (date) | **[Optional]** Data do arquivamento no formato YYYY-MM-DD. |

#### Exemplo: minimo — Criação mínima (campos obrigatórios)

```json
{
  "users_id": "123456",
  "customers_id": [
    1234567
  ],
  "stages_id": "2345678",
  "type_lawsuits_id": "1234567"
}
```

#### Exemplo: completo — Criação completa (todos os campos)

```json
{
  "users_id": "123456",
  "customers_id": [
    1234567
  ],
  "stages_id": "2345678",
  "type_lawsuits_id": "1234567",
  "protocol_number": "PROT-2026-001",
  "folder": "PASTA CLIENTE A",
  "date": "2026-04-02",
  "notes": "Processo iniciado para cliente referente a disputa contratual",
  "fees_expec": 10000,
  "fees_money": 5000,
  "contingency": 2500,
  "status_closure": "2026-04-02",
  "exit_production": "2026-03-01",
  "exit_execution": "2026-03-15"
}
```

### Respostas

#### 201 — Processo criado com sucesso

##### Exemplo

```json
{
  "success": true,
  "lawsuits_id": 12358596
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: campos_obrigatorios — Campos obrigatórios ausentes

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "customers_id": [
      "The customer is required."
    ],
    "users_id": [
      "The responsible user is required"
    ],
    "stages_id": [
      "The stage is required"
    ],
    "type_lawsuits_id": [
      "The type lawsuit is required"
    ]
  }
}
```

##### Exemplo: customers_id_invalido — Cliente não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "customers_id.0": [
      "One or more customers do not belong to your account"
    ]
  }
}
```

##### Exemplo: stages_id_invalido — Fase processual não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "stages_id": [
      "The stage do not belong to your account"
    ]
  }
}
```

##### Exemplo: type_lawsuits_id_invalido — Tipo de processo não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "type_lawsuits_id": [
      "The type lawsuit do not belong to your account"
    ]
  }
}
```

##### Exemplo: users_id_invalido — Usuário não pertence ao escritório

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "users_id": [
      "You must enter a user associated with your office"
    ]
  }
}
```

##### Exemplo: customers_id_vazio — Array customers_id enviado vazio

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "customers_id": [
      "The customer is required."
    ]
  }
}
```

##### Exemplo: folder_longo — Campo folder excede 30 caracteres

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "folder": [
      "The folder cannot exceed 30 characters"
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```

#### 500 — Erro interno do servidor

_Sem corpo de resposta._



# Crie uma movimentação manual para um processo
URL: /docs/lawsuits/createLawsuitMovement
Última atualização: 30/04/2026 · doc v1.19.0 — Exemplos de data ajustados em POST /lawsuits/movement. (histórico completo: /docs/changelog)

Cria uma nova movimentação manual (andamento) para um processo existente.

**Campos obrigatórios:**

* `lawsuit_id` - ID do processo (deve existir e pertencer ao escritório)
* `date` - Data da movimentação no formato **DD/MM/YYYY**
* `description` - Descrição da movimentação (mínimo 10 caracteres)

**Validações importantes:**

* `description`: mínimo de 10 caracteres
* `date`: formato **DD/MM/YYYY** obrigatório (diferente de outros endpoints)
* `lawsuit_id`: deve ser um ID válido de processo existente no escritório

**Comportamento:**

* Movimentações criadas por este endpoint têm `origin=MANUAL`
* Podem ser filtradas no endpoint GET /movements usando o parâmetro `?origin=MANUAL`

## POST /lawsuits/movement

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Crie uma movimentação manual para um processo

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

**Campos obrigatórios:** lawsuit_id, date, description

| Campo | Tipo | Descrição |
|-------|------|----------|
| lawsuit_id | integer | **[Required]** ID do processo |
| date | string | **[Required]** Data da movimentação no formato DD/MM/YYYY |
| description | string | **[Required]** Descrição da movimentação (mínimo 10 caracteres) |

#### Exemplo: exemplo — Criar movimentação

```json
{
  "lawsuit_id": 123456,
  "date": "02/04/2026",
  "description": "Audiência de conciliação agendada"
}
```

### Respostas

#### 201 — Movimentação criada com sucesso

##### Exemplo

```json
{
  "success": true,
  "lawsuits_id": 123
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: campos_obrigatorios — Campos obrigatórios ausentes

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "description": [
      "Informe os dados do andamento"
    ],
    "date": [
      "Informe a data do andamento"
    ],
    "lawsuit_id": [
      "Informe um processo válido"
    ]
  }
}
```

##### Exemplo: description_curta — Descrição com menos de 10 caracteres

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "description": [
      "O andamento deve ter no mínimo 10 caracteres"
    ]
  }
}
```

##### Exemplo: date_invalida — Formato de data inválido (esperado: DD/MM/YYYY)

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "date": [
      "Informe uma data válida"
    ]
  }
}
```

##### Exemplo: lawsuit_id_invalido — Processo não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "lawsuit_id": [
      "Informe um processo válido"
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha o histórico de tarefas de um processo
URL: /docs/lawsuits/getHistoryByLawsuitId
Última atualização: 02/01/2026 · doc v1.3.0 — Endpoints de processos (Lawsuits) adicionados à documentação. (histórico completo: /docs/changelog)

Retorna lista de tarefas (histórico) associadas a um processo específico.

**Filtros disponíveis:**

* `status` - Filtra tarefas por status (pending, completed ou all)

**Comportamento:**

* Sem filtro de status: retorna todas as tarefas (`status: "all"`)
* Com `status=pending`: retorna apenas tarefas pendentes
* Com `status=completed`: retorna apenas tarefas concluídas
* Array vazio quando não há tarefas no status especificado

**⚠️ Importante:**

* Parâmetros `limit` e `offset` **não funcionam** neste endpoint
* A API retorna todas as tarefas do processo de uma vez
* Retorna array vazio para lawsuit\_id inexistente ou sem permissão (não retorna erro 404)

## GET /history/{lawsuit_id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha o histórico de tarefas de um processo

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| lawsuit_id | integer | Sim | **[Required]** ID único do processo |

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| status | string | Não | **[Optional]** Filtrar tarefas por status (pending = pendentes, completed = concluídas) |

### Respostas

#### 200 — Lista de tarefas retornada com sucesso

##### Exemplo: all_tasks — Todas as tarefas (sem filtro)

```json
{
  "status": "all",
  "data": [
    {
      "process_number": "0001234-56.2024.8.26.0100",
      "protocol_number": "PROT-12345",
      "task": "AUDIÊNCIA",
      "reward": 1500,
      "start": "2026-02-15 10:00:00",
      "date_deadline": "2026-02-15 12:00:00",
      "comments": "Audiência de conciliação",
      "local": "Sala 301",
      "created_at": "2026-01-10 14:30:00",
      "author": "JOÃO SILVA",
      "responsible": "MARIA SANTOS",
      "customers": "PEDRO OLIVEIRA"
    }
  ]
}
```

##### Exemplo: pending_tasks — Apenas tarefas pendentes

```json
{
  "status": "pending",
  "data": [
    {
      "process_number": null,
      "protocol_number": "PROT-12345",
      "task": "PETIÇÃO",
      "reward": 0,
      "start": "2026-02-20 09:00:00",
      "date_deadline": "2026-02-25 18:00:00",
      "comments": "Elaborar petição de recurso",
      "local": null,
      "created_at": "2026-02-18 11:00:00",
      "author": "JOÃO SILVA",
      "responsible": "MARIA SANTOS",
      "customers": "PEDRO OLIVEIRA"
    }
  ],
  "query": "pending"
}
```

##### Exemplo: completed_empty — Nenhuma tarefa concluída

```json
{
  "status": "completed",
  "data": [],
  "query": "completed"
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha as últimas movimentações com filtros
URL: /docs/lawsuits/getLastMovements
Última atualização: 14/05/2026 · doc v1.20.0 — Documentação de GET /last_movements atualizada para refletir o comportamento agrupado das movimentações. (histórico completo: /docs/changelog)

Retorna o **último andamento** de cada processo do escritório, agrupado por processo.

**Comportamento:**

* Cada processo aparece **uma única vez** — sempre com seu andamento mais recente
* Se um processo tem múltiplos andamentos, apenas o mais recente é retornado
* Para listar todos os andamentos de um processo específico, use `GET /movements/{lawsuit_id}`

**Como funcionam os filtros:**

* Múltiplos filtros são combinados com **AND** (interseção)
* Todos os parâmetros são **opcionais**
* `lawsuit_id`: retorna o último andamento daquele processo específico (1 item)
* `process_number`, `protocol_number`: busca exata pelo número do processo
* `date_start` e `date_end`: filtram pela data do último andamento do processo

**Paginação:**

* Padrão: 100 itens por página (limit=100, offset=0)
* `totalCount` representa o número de **processos distintos** com andamentos

**Ordenação:**

* Processos ordenados pela data do último andamento (mais recentes primeiro)

## GET /last_movements

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha as últimas movimentações com filtros

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| lawsuit_id | integer | Não | **[Optional]** ID exato do processo. |
| process_number | string | Não | **[Optional]** Número exato do processo. |
| protocol_number | string | Não | **[Optional]** Número exato do protocolo. |
| date_start | string (date) | Não | **[Optional]** Data inicial para filtrar movimentações (formato: YYYY-MM-DD). |
| date_end | string (date) | Não | **[Optional]** Data final para filtrar movimentações (formato: YYYY-MM-DD). |

### Respostas

#### 200 — Últimas movimentações encontradas com sucesso

##### Exemplo: allMovements — Todas as movimentações (sem filtro)

```json
{
  "offset": 0,
  "limit": 100,
  "totalCount": 250,
  "data": [
    {
      "lawsuit_id": 12345,
      "date": "2025-02-15",
      "title": "Audiência de conciliação realizada",
      "header": "TJSP - Tribunal de Justiça de São Paulo",
      "process_number": "0001234-56.2024.8.26.0100",
      "protocol_number": null,
      "customers": "João Silva, Maria Santos"
    },
    {
      "lawsuit_id": 12346,
      "date": "2025-02-14",
      "title": "Sentença publicada",
      "header": "TJRJ - Tribunal de Justiça do Rio de Janeiro",
      "process_number": "0005678-90.2024.8.19.0001",
      "protocol_number": "PROT-2024-001",
      "customers": "Pedro Oliveira, Ana Costa"
    }
  ]
}
```

##### Exemplo: byLawsuitId — Filtrar por ID do processo

```json
{
  "offset": 0,
  "limit": 100,
  "totalCount": 8,
  "data": [
    {
      "lawsuit_id": 12345,
      "date": "2025-02-15",
      "title": "Audiência de conciliação realizada",
      "header": "TJSP - Tribunal de Justiça de São Paulo",
      "process_number": "0001234-56.2024.8.26.0100",
      "protocol_number": null,
      "customers": "João Silva, Maria Santos"
    }
  ]
}
```

##### Exemplo: byDateRange — Filtrar por intervalo de datas

```json
{
  "offset": 0,
  "limit": 100,
  "totalCount": 15,
  "data": [
    {
      "lawsuit_id": 12347,
      "date": "2025-01-25",
      "title": "Recurso interposto",
      "header": "TJMG - Tribunal de Justiça de Minas Gerais",
      "process_number": "0009876-54.2024.8.13.0024",
      "protocol_number": "PROT-2025-042",
      "customers": "Carlos Mendes, Empresa XYZ Ltda"
    }
  ]
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha um processo pelo ID
URL: /docs/lawsuits/getLawsuitById
Última atualização: 29/04/2026 · doc v1.18.0 — Descrições dos campos `status_closure`, `exit_production` e `exit_execution` revisadas para maior clareza. (histórico completo: /docs/changelog)

Retorna os dados completos de um processo específico baseado no seu ID único.

**Resposta inclui:**

* Dados básicos do processo (número CNJ, protocolo, pasta, data)
* Informações financeiras (honorários esperados, contingência)
* Tipo e grupo do processo
* Fase e etapa processual
* Usuário responsável
* Array de clientes associados
* Datas de criação e encerramentos

## GET /lawsuits/{id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha um processo pelo ID

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| id | integer | Sim | **[Required]** ID único do processo |

### Respostas

#### 200 — Processo encontrado com sucesso

##### Exemplo: encontrado — Processo encontrado

```json
{
  "id": 1234501,
  "process_number": "0001234-56.2026.5.15.0001",
  "protocol_number": "PROT-2026-001",
  "folder": "PASTA CLIENTE A",
  "process_date": "2026-01-15",
  "fees_expec": 15000,
  "fees_money": 8000,
  "contingency": 3000,
  "type_lawsuit_id": 1234567,
  "type": "ACAO TRABALHISTA",
  "group_id": 200001,
  "group": "TRABALHISTA",
  "created_at": "2026-01-15 10:30:00",
  "status_closure": null,
  "exit_production": null,
  "exit_execution": null,
  "responsible_id": 100001,
  "responsible": "MARIA SILVA",
  "stages_id": 300001,
  "stage": "FASE INSTRUTORIA",
  "steps_id": 3,
  "step": "JUDICIAL",
  "notes": "Processo referente a reclamacao trabalhista",
  "customers": [
    {
      "customer_id": 9000001,
      "name": "JOAO PEREIRA",
      "identification": "111.222.333-44",
      "origin": "ESCRITORIO"
    },
    {
      "customer_id": 9000002,
      "name": "EMPRESA XYZ LTDA",
      "identification": "12.345.678/0001-90",
      "origin": "PARTE CONTRARIA"
    }
  ]
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 404 — Registro não encontrado

##### Exemplo

```json
{
  "error": "Lawsuit not found"
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha uma lista de processos
URL: /docs/lawsuits/getLawsuits
Última atualização: 29/04/2026 · doc v1.18.0 — Descrições dos campos `status_closure`, `exit_production` e `exit_execution` revisadas para maior clareza. (histórico completo: /docs/changelog)

Retorna uma lista de processos com opções avançadas de filtro e paginação.

**Como funcionam os filtros:**

* Múltiplos filtros são combinados com **AND** (interseção)
* Filtros de texto são **case-insensitive**
* Alguns campos aceitam **busca parcial** (name, group, type, responsible, stage, step, notes)
* Outros requerem **valor exato** (customer\_id, process\_number, protocol\_number, folder, identification)
* Filtros de data funcionam como **range** (use \_start e \_end juntos)

A resposta inclui `totalCount` (total de registros), `data` (array de processos) e informações de paginação (`limit` e `offset`).

## GET /lawsuits

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha uma lista de processos

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| name | string | Não | **[Optional]** Busca parcial no nome dos contatos associados ao processo. |
| customer_id | integer | Não | **[Optional]** ID exato do contato associado ao processo. |
| identification | string | Não | **[Optional]** CPF ou CNPJ do contato associado ao processo. Aceita formatação com pontos e traços. |
| process_number | string | Não | **[Optional]** Número exato do processo. |
| protocol_number | string | Não | **[Optional]** Número exato do protocolo do processo. |
| folder | string | Não | **[Optional]** Nome exato da pasta do processo. |
| notes | string | Não | **[Optional]** Busca parcial nas anotações ou comentários do processo. |
| group | string | Não | **[Optional]** Busca parcial no grupo do processo. Case-insensitive. |
| type | string | Não | **[Optional]** Busca parcial no tipo do processo. |
| responsible | string | Não | **[Optional]** Busca parcial no nome do responsável. |
| stage | string | Não | **[Optional]** Busca parcial no nome da fase processual ou ID numérico. |
| step | string | Não | **[Optional]** Busca parcial no nome do passo. |
| process_date_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data do processo (formato: AAAA-MM-DD). |
| process_date_end | string (date) | Não | **[Optional]** Data final para filtrar por data do processo (formato: AAAA-MM-DD). |
| status_closure_start | string (date) | Não | **[Optional]** Data de início da filtragem dos processos por data de fechamento (formato: AAAA-MM-DD). |
| status_closure_end | string (date) | Não | **[Optional]** Data final para filtrar processos por data de fechamento (formato: AAAA-MM-DD). |
| exit_production_start | string (date) | Não | **[Optional]** Data inicial para filtrar processos por data de trânsito em julgado (formato: AAAA-MM-DD). |
| exit_production_end | string (date) | Não | **[Optional]** Data final para filtrar processos por data de trânsito em julgado (formato: AAAA-MM-DD). |
| exit_execution_start | string (date) | Não | **[Optional]** Data inicial para filtrar processos por data de arquivamento (formato: AAAA-MM-DD). |
| exit_execution_end | string (date) | Não | **[Optional]** Data final para filtrar processos por data de arquivamento (formato: AAAA-MM-DD). |
| created_start | string (date) | Não | **[Optional]** Data inicial para filtrar processos por data de criação (formato: AAAA-MM-DD). |
| created_end | string (date) | Não | **[Optional]** Data final para filtrar processos por data de criação (formato: AAAA-MM-DD). |
| limit | integer | Não | **[Optional]** Número de registros a retornar por página (padrão: 1000, recomendado: até 100). |
| offset | integer | Não | **[Optional]** Número de registros a pular para paginação (padrão: 0). |

### Respostas

#### 200 — Lista de processos retornada com sucesso

##### Exemplo: sem_filtro — Lista sem filtro (primeiros resultados)

```json
{
  "offset": 0,
  "limit": 10,
  "totalCount": 48,
  "data": [
    {
      "id": 1234501,
      "process_number": "0001234-56.2026.5.15.0001",
      "protocol_number": null,
      "folder": "PASTA CLIENTE A",
      "process_date": "2026-01-15",
      "fees_expec": 15000,
      "fees_money": null,
      "contingency": null,
      "type_lawsuit_id": 1234567,
      "type": "ACAO TRABALHISTA",
      "group_id": 200001,
      "group": "TRABALHISTA",
      "created_at": "2026-01-15 10:30:00",
      "status_closure": null,
      "exit_production": null,
      "exit_execution": null,
      "responsible_id": 100001,
      "responsible": "MARIA SILVA",
      "stages_id": 300001,
      "stage": "FASE INSTRUTORIA",
      "steps_id": 3,
      "step": "JUDICIAL",
      "notes": null,
      "customers": [
        {
          "customer_id": 9000001,
          "name": "JOAO PEREIRA",
          "identification": "111.222.333-44",
          "origin": "ESCRITORIO"
        }
      ]
    },
    {
      "id": 1234502,
      "process_number": null,
      "protocol_number": null,
      "folder": "PASTA CLIENTE B",
      "process_date": "2026-01-15",
      "fees_expec": null,
      "fees_money": null,
      "contingency": null,
      "type_lawsuit_id": 1234567,
      "type": "ACAO TRABALHISTA",
      "group_id": 200001,
      "group": "TRABALHISTA",
      "created_at": "2026-01-15 10:30:00",
      "status_closure": null,
      "exit_production": null,
      "exit_execution": null,
      "responsible_id": 100001,
      "responsible": "CARLOS SOUZA",
      "stages_id": 300001,
      "stage": "AGUARDANDO AUDIENCIA",
      "steps_id": 3,
      "step": "JUDICIAL",
      "notes": null,
      "customers": [
        {
          "customer_id": 9000002,
          "name": "ANA COSTA",
          "identification": null,
          "origin": "INDICACAO"
        }
      ]
    }
  ],
  "query": {}
}
```

##### Exemplo: com_filtro — Lista com filtro por responsavel

```json
{
  "offset": 0,
  "limit": 10,
  "totalCount": 3,
  "data": [
    {
      "id": 1234501,
      "process_number": "0001234-56.2026.5.15.0001",
      "protocol_number": null,
      "folder": "PASTA CLIENTE A",
      "process_date": "2026-01-15",
      "fees_expec": 15000,
      "fees_money": null,
      "contingency": null,
      "type_lawsuit_id": 1234567,
      "type": "ACAO TRABALHISTA",
      "group_id": 200001,
      "group": "TRABALHISTA",
      "created_at": "2026-01-15 10:30:00",
      "status_closure": null,
      "exit_production": null,
      "exit_execution": null,
      "responsible_id": 100001,
      "responsible": "MARIA SILVA",
      "stages_id": 300001,
      "stage": "FASE INSTRUTORIA",
      "steps_id": 3,
      "step": "JUDICIAL",
      "notes": null,
      "customers": [
        {
          "customer_id": 9000001,
          "name": "JOAO PEREIRA",
          "identification": "111.222.333-44",
          "origin": "ESCRITORIO"
        }
      ]
    }
  ],
  "query": {
    "responsible": "MARIA SILVA"
  }
}
```

##### Exemplo: vazio — Nenhum processo encontrado

```json
{
  "offset": 0,
  "limit": 10,
  "totalCount": 0,
  "data": [],
  "query": {
    "responsible": "NOME INEXISTENTE"
  }
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha as movimentações de um processo
URL: /docs/lawsuits/getMovementsByLawsuitId
Última atualização: 02/01/2026 · doc v1.3.0 — Endpoints de processos (Lawsuits) adicionados à documentação. (histórico completo: /docs/changelog)

Retorna lista de movimentações (andamentos processuais) associadas a um processo específico.

**Filtros disponíveis:**

* `origin` - Filtra por origem (TRIBUNAL ou MANUAL)

**Comportamento:**

* Sem filtro: retorna todas as movimentações
* Com `origin=TRIBUNAL`: apenas movimentações do tribunal
* Com `origin=MANUAL`: apenas movimentações criadas manualmente

**⚠️ Respostas especiais:**

* **204 No Content:** Retornado quando não há movimentações (ao invés de 404)
* ID inexistente ou inválido também retorna **204**
* Token inválido redireciona (302) para `/login`

## GET /movements/{lawsuit_id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha as movimentações de um processo

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| lawsuit_id | integer | Sim | **[Required]** ID único do processo |

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| origin | string | Não | **[Optional]** Filtrar por origem das movimentações (TRIBUNAL = do tribunal, MANUAL = criadas manualmente) |

### Respostas

#### 200 — Lista de movimentações retornada com sucesso

##### Exemplo: all_movements — Todas as movimentações (sem filtro)

```json
{
  "data": [
    {
      "lawsuit_id": 1234567,
      "date": "2025-01-17",
      "title": "PETIÇÃO INTERMEDIÁRIA",
      "header": "TJSP - Tribunal de Justiça",
      "process_number": "0001234-56.2024.8.26.0100",
      "protocol_number": null,
      "customers": "MARIA SANTOS, JOÃO SILVA"
    }
  ],
  "query": []
}
```

##### Exemplo: tribunal_only — Apenas do tribunal

```json
{
  "data": [
    {
      "lawsuit_id": 1234567,
      "date": "2025-01-17",
      "title": "CONCLUSOS PARA DESPACHO",
      "header": "TJSP - Tribunal de Justiça",
      "process_number": "0001234-56.2024.8.26.0100",
      "protocol_number": null,
      "customers": "MARIA SANTOS, JOÃO SILVA"
    }
  ],
  "query": {
    "origin": "TRIBUNAL"
  }
}
```

#### 204 — Sem movimentações (No Content) - retornado quando não há dados ou ID inexistente

_Sem corpo de resposta._

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Atualize um processo existente
URL: /docs/lawsuits/updateLawsuit
Última atualização: 13/04/2026 · doc v1.16.0 — PUT /lawsuits/{id} documentado com todos os campos disponíveis. (histórico completo: /docs/changelog)

Atualiza dados de um processo específico no sistema.

**⚠️ Importante:** Envie apenas os campos que deseja atualizar. Campos não incluídos no request permanecerão inalterados.

**Campos atualizáveis:**

* `users_id` - Responsável pelo processo (deve existir na conta)
* `stages_id` - Fase processual (deve existir na conta; atualiza `step` automaticamente)
* `type_lawsuits_id` - Tipo de processo (deve existir na conta; atualiza `group` automaticamente)
* `process_number` - Número CNJ (validado; envie string vazia para limpar)
* `protocol_number` - Número de protocolo
* `folder` - Nome da pasta (máximo 30 caracteres)
* `date` - Data do processo (formato YYYY-MM-DD)
* `notes` - Observações do processo
* `fees_expec` - Valor esperado de honorários (inteiro, em reais)
* `fees_money` - Valor de honorários em dinheiro (inteiro, em reais)
* `contingency` - Valor de contingência (inteiro, em reais)
* `status_closure` - Data de fechamento (YYYY-MM-DD; envie string vazia para limpar)
* `exit_production` - Data do trânsito em julgado (YYYY-MM-DD; envie string vazia para limpar)
* `exit_execution` - Data do arquivamento (YYYY-MM-DD; envie string vazia para limpar)

**Validações aplicadas:**

* `process_number`: Valida formato CNJ contra bases do Judiciário
* `folder`: Máximo 30 caracteres
* `date`, `status_closure`, `exit_production`, `exit_execution`: Formato YYYY-MM-DD obrigatório
* `stages_id` e `type_lawsuits_id`: Devem pertencer à sua conta

## PUT /lawsuits/{id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Atualize um processo existente

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| id | integer | Sim | **[Required]** ID único do processo a ser atualizado |

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

| Campo | Tipo | Descrição |
|-------|------|----------|
| users_id | string | **[Optional]** ID do usuário responsável pelo processo (deve existir na conta) |
| stages_id | string | **[Optional]** ID da fase processual (deve existir na conta; atualiza `step` automaticamente) |
| type_lawsuits_id | string | **[Optional]** ID do tipo de processo (deve existir na conta; atualiza `group` automaticamente) |
| process_number | string | **[Optional]** Número do processo CNJ (validado contra bases oficiais). Envie string vazia (`""`) para limpar. |
| protocol_number | string | **[Optional]** Número de protocolo do processo |
| folder | string | **[Optional]** Nome da pasta (máximo 30 caracteres) |
| date | string (date) | **[Optional]** Data do processo no formato YYYY-MM-DD |
| notes | string | **[Optional]** Observações detalhadas sobre o processo |
| fees_expec | integer | **[Optional]** Valor esperado de honorários (em reais, inteiro) |
| fees_money | integer | **[Optional]** Valor de honorários em dinheiro (em reais, inteiro) |
| contingency | integer | **[Optional]** Valor de contingência do processo (em reais, inteiro) |
| status_closure | string (date) | **[Optional]** Data de fechamento no formato YYYY-MM-DD. Envie string vazia (`""`) para limpar. |
| exit_production | string (date) | **[Optional]** Data do trânsito em julgado no formato YYYY-MM-DD. Envie string vazia (`""`) para limpar. |
| exit_execution | string (date) | **[Optional]** Data do arquivamento no formato YYYY-MM-DD. Envie string vazia (`""`) para limpar. |

#### Exemplo: minimo — Atualização mínima (um campo)

```json
{
  "folder": "PASTA CLIENTE A"
}
```

#### Exemplo: completo — Atualização completa (todos os campos)

```json
{
  "users_id": "100001",
  "stages_id": "300001",
  "type_lawsuits_id": "1234567",
  "process_number": "0001234-56.2026.5.15.0001",
  "protocol_number": "PROT-2026-001",
  "folder": "PASTA CLIENTE A",
  "date": "2026-04-02",
  "notes": "Processo atualizado com todos os campos",
  "fees_expec": 15000,
  "fees_money": 8000,
  "contingency": 3000,
  "status_closure": "2026-04-02",
  "exit_production": "2026-03-01",
  "exit_execution": "2026-03-15"
}
```

#### Exemplo: limpar_datas — Limpar campos de data

```json
{
  "status_closure": "",
  "exit_production": "",
  "exit_execution": ""
}
```

### Respostas

#### 200 — Processo atualizado com sucesso

##### Exemplo

```json
{
  "success": true,
  "lawsuits_id": "1234567"
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: id_nao_encontrado — ID não encontrado ou sem permissão

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "auth": [
      "You dont have permission to edit this lawsuit."
    ]
  }
}
```

##### Exemplo: stages_id_invalido — Fase processual não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "stages_id": [
      "The stage do not belong to your account"
    ]
  }
}
```

##### Exemplo: users_id_invalido — Usuário não pertence ao escritório

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "users_id": [
      "You must enter a user associated with your office"
    ]
  }
}
```

##### Exemplo: type_lawsuits_id_invalido — Tipo de processo não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "type_lawsuits_id": [
      "The type lawsuit do not belong to your account"
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha publicações de um processo
URL: /docs/publications/getPublicationsByLawsuitId
Última atualização: 02/01/2026 · doc v1.3.0 — Endpoints de processos (Lawsuits) adicionados à documentação. (histórico completo: /docs/changelog)

Retorna lista de publicações associadas a um processo específico.

Cada publicação inclui informações como título, conteúdo, data de publicação e fonte.

## GET /publications/{lawsuit_id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha publicações de um processo

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| lawsuit_id | integer | Sim | **[Required]** ID do processo para buscar publicações. |

### Respostas

#### 200 — Lista de publicações do processo encontrada com sucesso

##### Exemplo: with_publications — Processo com publicações

```json
{
  "data": [
    {
      "process_number": "1234567-89.2024.8.00.0000",
      "protocol_number": null,
      "start": "2025-01-15 00:00:00",
      "date_deadline": null,
      "local": null,
      "created_at": "2025-01-14 10:30:00",
      "author": "João Silva",
      "responsible": "Maria Santos",
      "customers": "Cliente A, Cliente B",
      "publication": "Intimação para apresentação de documentos",
      "date": "2025-01-15"
    }
  ]
}
```

##### Exemplo: empty — Processo sem publicações

```json
{
  "data": []
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 404 — Registro não encontrado

##### Exemplo

```json
{
  "error": "Not found"
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha configurações da conta
URL: /docs/settings/getSettings
Última atualização: 24/06/2026 · doc v1.23.0 — Corrigido o nome do campo de tipos de processo na resposta de GET /settings (`lawsuit_types`). Em POST /transactions, esclarecido que `type` e `competence` são derivados de `entry_type` e `date_due` — não precisam ser enviados. (histórico completo: /docs/changelog)

Retorna configurações e metadados da conta autenticada: usuários, origens de leads, tipos de tarefas, fases processuais, tipos de processos e dados financeiros.

**Este endpoint fornece os IDs de referência necessários para criar/atualizar registros em outros endpoints.**

Campos retornados: [#campos-retornados]

* **`users`** - Usuários do escritório (use `id` em: Customers, Lawsuits, Tasks, Transactions)
* **`origins`** - Origens de leads (use `id` como `customers_origins_id` em: Customers)
* **`tasks`** - Tipos de tarefas disponíveis (use `id` como `tasks_id` em: Tasks/Posts)
* **`stages`** - Fases processuais (use `id` como `stages_id` em: Lawsuits)
* **`lawsuit_types`** - Tipos de processos por área do direito (use `id` como `type_lawsuits_id` em: Lawsuits)
* **`financial`** - Dados financeiros:
  * **`banks`** - Contas bancárias (use `id` como `debit_account` em: Transactions)
  * **`categories`** - Categorias financeiras com tipo CRÉDITO/DÉBITO (use `id` como `categories_id` em: Transactions)
  * **`cost_centers`** - Centros de custo (use `id` como `cost_centers_id` em: Transactions)
  * **`departments`** - Departamentos (use `id` como `sectors_id` em: Transactions)

**Recomendação:** Execute este endpoint ao inicializar sua integração e armazene os IDs em cache para uso nas operações subsequentes.

⚠️ Os IDs retornados são específicos da sua conta.

## GET /settings

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha configurações da conta

### Respostas

#### 200 — Configurações da conta encontradas com sucesso

##### Exemplo: configuracoes — Configuracoes do escritorio

```json
{
  "users": [
    {
      "id": 100001,
      "name": "MARIA SILVA",
      "email": "maria.silva@example.com",
      "cellphone": "(11) 99999-1234"
    },
    {
      "id": 100002,
      "name": "CARLOS SOUZA",
      "email": "carlos.souza@example.com",
      "cellphone": "(11) 98888-5678"
    }
  ],
  "origins": [
    {
      "id": 422001,
      "origin": "ESCRITORIO"
    },
    {
      "id": 422002,
      "origin": "INDICACAO"
    },
    {
      "id": 422003,
      "origin": "INSTAGRAM"
    },
    {
      "id": 422004,
      "origin": "FACEBOOK"
    }
  ],
  "tasks": [
    {
      "id": 500001,
      "task": "AUDIENCIA",
      "reward": 150
    },
    {
      "id": 500002,
      "task": "PETICAO INICIAL",
      "reward": 100
    },
    {
      "id": 500003,
      "task": "RECURSO",
      "reward": 200
    }
  ],
  "stages": [
    {
      "id": 300001,
      "stage": "FASE INSTRUTORIA",
      "step": "JUDICIAL"
    },
    {
      "id": 300002,
      "stage": "AGUARDANDO AUDIENCIA",
      "step": "JUDICIAL"
    },
    {
      "id": 300003,
      "stage": "RECURSO PROTOCOLADO",
      "step": "RECURSAL"
    }
  ],
  "lawsuit_types": [
    {
      "id": 1234567,
      "type": "ACAO TRABALHISTA",
      "group": "TRABALHISTA"
    },
    {
      "id": 1234568,
      "type": "ACAO CIVIL PUBLICA",
      "group": "CIVEL"
    },
    {
      "id": 1234569,
      "type": "ACAO PENAL",
      "group": "CRIMINAL"
    }
  ],
  "financial": {
    "banks": [
      {
        "id": 135001,
        "name": "CONTA PRINCIPAL",
        "institution": "BANCO DO BRASIL"
      },
      {
        "id": 135002,
        "name": "CONTA POUPANCA",
        "institution": "CAIXA ECONOMICA"
      }
    ],
    "categories": [
      {
        "id": 1,
        "category": "HONORARIOS INICIAIS",
        "type": "income"
      },
      {
        "id": 2,
        "category": "HONORARIOS DE EXITO",
        "type": "income"
      },
      {
        "id": 101,
        "category": "CUSTAS PROCESSUAIS",
        "type": "expense"
      }
    ],
    "cost_centers": [
      {
        "id": 41001,
        "cost_center": "GERAL"
      },
      {
        "id": 41002,
        "cost_center": "CIVEL"
      },
      {
        "id": 41003,
        "cost_center": "TRABALHISTA"
      }
    ],
    "departments": [
      {
        "id": 10001,
        "department": "CONTENCIOSO"
      },
      {
        "id": 10002,
        "department": "CONSULTIVO"
      }
    ]
  }
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Criar nova tarefa
URL: /docs/tasks/createPost
Última atualização: 23/03/2026 · doc v1.13.0 — Documentação de transações e tarefas ampliada e validada. (histórico completo: /docs/changelog)

Cria uma nova tarefa no sistema associada a um processo e usuários responsáveis.

**Campos Obrigatórios:**

* `from`: ID do usuário criador (deve pertencer ao escritório)
* `guests`: Array com IDs dos responsáveis (mínimo 1, devem pertencer ao escritório)
* `tasks_id`: ID do tipo de tarefa
* `lawsuits_id`: ID do processo
* `start_date`: Data de início (aceita YYYY-MM-DD ou DD/MM/YYYY)

**Validações:**

* API valida se usuários pertencem ao escritório autenticado
* API detecta e impede tarefas duplicadas
* Array `guests` não pode ser vazio (mínimo 1 usuário)
* Guests podem incluir o próprio criador

**Horário de término:**

* `end_date` pode ser enviado sozinho
* `end_time` **requer `end_date` junto** — sem ele o horário de término é ignorado

**Retorno:**
Em caso de sucesso, retorna status 200 com ID da tarefa criada.

## POST /posts

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Criar nova tarefa

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

**Campos obrigatórios:** from, guests, tasks_id, lawsuits_id, start_date

| Campo | Tipo | Descrição |
|-------|------|----------|
| from | string | **[Required]** ID do usuário criador da tarefa. Deve pertencer ao escritório autenticado. |
| guests | array<integer> | **[Required]** Array com IDs dos usuários responsáveis pela tarefa. Mínimo 1 usuário. Todos devem pertencer ao escritório autenticado. |
| tasks_id | string | **[Required]** ID do tipo de tarefa. |
| lawsuits_id | string | **[Required]** ID do processo ao qual a tarefa está associada. |
| start_date | string | **[Required]** Data de início da tarefa. Aceita formatos YYYY-MM-DD ou DD/MM/YYYY. |
| start_time | string | **[Optional]** Hora de início da tarefa (formato HH:MM). |
| end_date | string | **[Optional]** Data de término da tarefa. Aceita formatos YYYY-MM-DD ou DD/MM/YYYY. |
| end_time | string | **[Optional]** Hora de término da tarefa (formato HH:MM). ⚠️ **Requer `end_date` junto** — sem ele o horário de término é ignorado. |
| date_deadline | string | **[Optional]** Data de prazo da tarefa. Aceita formatos YYYY-MM-DD ou DD/MM/YYYY. |
| local | string | **[Optional]** Local onde a tarefa será realizada. |
| comments | string | **[Optional]** Observações ou descrição detalhada da tarefa. |
| urgent | boolean | **[Optional]** Flag indicando se a tarefa é urgente. |
| important | boolean | **[Optional]** Flag indicando se a tarefa é importante. |
| display_schedule | boolean | **[Optional]** Flag indicando se a tarefa deve ser exibida na agenda. |

#### Exemplo: minimo — Criação mínima (campos obrigatórios)

```json
{
  "from": "12345",
  "guests": [
    12345,
    67890
  ],
  "tasks_id": "100",
  "lawsuits_id": "5000",
  "start_date": "2026-04-02"
}
```

#### Exemplo: completo — Criação completa (todos os campos)

```json
{
  "from": "12345",
  "guests": [
    12345,
    67890
  ],
  "tasks_id": "100",
  "lawsuits_id": "5000",
  "start_date": "2026-04-02",
  "start_time": "14:30",
  "end_date": "2026-04-02",
  "end_time": "16:00",
  "date_deadline": "2026-04-09",
  "local": "Sala de reuniões - 3º andar",
  "comments": "Reunião de acompanhamento do processo",
  "urgent": true,
  "important": true,
  "display_schedule": true
}
```

### Respostas

#### 200 — Tarefa criada com sucesso

##### Exemplo

```json
{
  "success": true,
  "posts_id": 180922743
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: campos_obrigatorios — Campos obrigatórios ausentes

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "lawsuits_id": [
      "The process is required"
    ],
    "start_date": [
      "The appointment date field is required"
    ],
    "from": [
      "The sender user is required"
    ],
    "tasks_id": [
      "The task field is required"
    ],
    "guests": [
      "Please provide the task assignees"
    ]
  }
}
```

##### Exemplo: lawsuits_id_invalido — Processo não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "lawsuits_id": [
      "The process is invalid"
    ]
  }
}
```

##### Exemplo: tasks_id_invalido — Tarefa não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "tasks_id": [
      "The task field is invalid"
    ]
  }
}
```

##### Exemplo: guests_invalido — Responsável não pertence ao escritório

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "guests": [
      "You must enter an assignees associated with your office"
    ]
  }
}
```

##### Exemplo: tarefa_duplicada — Tarefa duplicada (mesmo tipo + processo + data)

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "duplicate": [
      "Task with this data already exists."
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```

#### 500 — Erro interno — geralmente causado por tipo de dado incorreto (ex: guests enviado como inteiro em vez de array)

##### Exemplo

```json
{
  "message": "Server Error"
}
```



# Obtenha uma lista de tarefas com filtros opcionais
URL: /docs/tasks/getPosts
Última atualização: 23/03/2026 · doc v1.13.0 — Documentação de transações e tarefas ampliada e validada. (histórico completo: /docs/changelog)

Retorna lista de tarefas do escritório com múltiplos filtros opcionais.

**📋 Comportamento do filtro de status:**

* **Sem filtros:** retorna todas as tarefas (pendentes e concluídas)
* **Com `user_name` ou `user_id`:** retorna APENAS tarefas onde aquele usuário específico está pendente
* **Com `lawsuit_id`:** retorna APENAS tarefas pendentes do processo
* **Com `completed_start/completed_end`:** retorna APENAS tarefas concluídas no período

**Nota:** Tarefas podem ter múltiplos usuários com status diferentes. O filtro por usuário considera o status individual daquele usuário na tarefa.

**⚠️ IMPORTANTE - Filtros de Data:**

* **Cada par de datas deve ser usado completo** (start + end juntos)
* Usar apenas 1 parâmetro do par (ex: só `date_start` sem `date_end`) faz a API **IGNORAR** o filtro
* Pares disponíveis: `date_start/date_end`, `created_start/created_end`, `deadline_start/deadline_end`, `completed_start/completed_end`
* Você pode usar **um ou mais pares** ao mesmo tempo

**Como funcionam os filtros:**

* Múltiplos filtros são combinados com **AND** (interseção)
* Todos os parâmetros são **opcionais**
* `user_name`: busca **parcial** (LIKE)
* `user_id`, `id`, `task_id`, `lawsuit_id`: busca **exata**

**Paginação:**

* Default: limit=1000, offset=0
* Limit recomendado: entre 1 e 100

**Estrutura da resposta:**

* Cada tarefa inclui objeto `lawsuit` com dados do processo
* Cada tarefa inclui array `users` com responsáveis

## GET /posts

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha uma lista de tarefas com filtros opcionais

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| date_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data da tarefa (formato: YYYY-MM-DD). **Deve ser usado com date_end**. |
| date_end | string (date) | Não | **[Optional]** Data final para filtrar por data da tarefa (formato: YYYY-MM-DD). **Deve ser usado com date_start**. |
| created_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data de criação (formato: YYYY-MM-DD). **Deve ser usado com created_end**. |
| created_end | string (date) | Não | **[Optional]** Data final para filtrar por data de criação (formato: YYYY-MM-DD). **Deve ser usado com created_start**. |
| deadline_start | string (date) | Não | **[Optional]** Data inicial para filtrar por prazo (formato: YYYY-MM-DD). **Deve ser usado com deadline_end**. |
| deadline_end | string (date) | Não | **[Optional]** Data final para filtrar por prazo (formato: YYYY-MM-DD). **Deve ser usado com deadline_start**. |
| completed_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data de conclusão (formato: YYYY-MM-DD). **Deve ser usado com completed_end**. |
| completed_end | string (date) | Não | **[Optional]** Data final para filtrar por data de conclusão (formato: YYYY-MM-DD). **Deve ser usado com completed_start**. |
| user_id | string | Não | **[Optional]** ID exato do usuário responsável. |
| user_name | string | Não | **[Optional]** Nome do usuário responsável (busca parcial case-insensitive). |
| task_id | string | Não | **[Optional]** ID exato do tipo de tarefa. |
| id | integer | Não | **[Optional]** ID exato de uma tarefa específica. |
| lawsuit_id | string | Não | **[Optional]** ID exato do processo associado. |
| limit | integer | Não | **[Optional]** Número de itens por página (recomendado: 1-100). |
| offset | integer | Não | **[Optional]** Número de itens a pular antes de iniciar a resposta (paginação). |

### Respostas

#### 200 — Lista de tarefas retornada com sucesso

##### Exemplo: allTasks — Todas as tarefas (sem filtro)

```json
{
  "offset": 0,
  "limit": 100,
  "totalCount": 532,
  "data": [
    {
      "id": 123456789,
      "date": "2025-05-12 00:00:00",
      "date_deadline": null,
      "task": "AUDIÊNCIA PRELIMINAR",
      "reward": 0,
      "notes": "Comparecer à audiência preliminar do processo. Levar documentos de identificação do cliente e procuração.",
      "local": null,
      "lawsuits_id": 1234567,
      "created_at": "2025-05-12 15:47:45",
      "lawsuit": {
        "id": 1234567,
        "process_number": "0001234-56.2025.8.26.0100",
        "protocol_number": null,
        "customers": [
          {
            "customer_id": 1234567,
            "name": "João Silva",
            "identification": null,
            "customers_origins_id": null
          }
        ]
      },
      "users": [
        {
          "user_id": 163,
          "name": "Maria Oliveira",
          "completed": null,
          "important": 1,
          "urgent": 0
        }
      ]
    }
  ]
}
```

##### Exemplo: byDateRange — Filtrar por data de criação

```json
{
  "offset": 0,
  "limit": 100,
  "totalCount": 11,
  "data": [
    {
      "id": 234567890,
      "date": "2025-10-07 00:00:00",
      "date_deadline": null,
      "task": "CONTESTAÇÃO COMPLEXA",
      "reward": 150,
      "notes": "Preparar contestação detalhada",
      "local": null,
      "lawsuits_id": 23456789,
      "created_at": "2025-10-07 12:10:27",
      "lawsuit": {
        "id": 23456789,
        "process_number": "0009876-54.2025.8.13.0024",
        "protocol_number": "123456789",
        "customers": [
          {
            "customer_id": 23456789,
            "name": "Carlos Mendes",
            "identification": null,
            "customers_origins_id": 456789
          }
        ]
      },
      "users": [
        {
          "user_id": 123456,
          "name": "Pedro Santos",
          "completed": null,
          "important": 0,
          "urgent": 0
        }
      ]
    }
  ]
}
```

##### Exemplo: byUserAndCompleted — Filtrar por usuário e tarefas concluídas

```json
{
  "offset": 0,
  "limit": 100,
  "totalCount": 5,
  "data": [
    {
      "id": 345678901,
      "date": "2025-04-27 00:00:00",
      "date_deadline": null,
      "task": "SOLICITAR DOCUMENTOS",
      "reward": 10,
      "notes": null,
      "local": null,
      "lawsuits_id": 34567890,
      "created_at": "2025-04-22 09:36:31",
      "lawsuit": {
        "id": 34567890,
        "process_number": null,
        "protocol_number": null,
        "customers": [
          {
            "customer_id": 34567890,
            "name": "Ana Costa",
            "identification": null,
            "customers_origins_id": 567890
          }
        ]
      },
      "users": [
        {
          "user_id": 234567,
          "name": "Roberto Lima",
          "completed": "2025-12-18 17:27:50",
          "important": 0,
          "urgent": 0
        }
      ]
    }
  ]
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Crie uma nova transação financeira
URL: /docs/transactions/createTransaction
Última atualização: 24/06/2026 · doc v1.23.0 — Corrigido o nome do campo de tipos de processo na resposta de GET /settings (`lawsuit_types`). Em POST /transactions, esclarecido que `type` e `competence` são derivados de `entry_type` e `date_due` — não precisam ser enviados. (histórico completo: /docs/changelog)

Cria uma transação financeira (receita ou despesa) no sistema.

**Campos obrigatórios:**

* `users_id` - ID do usuário responsável (obtenha em GET `/api/v1/settings` → `users[]`)
* `entry_type` - Tipo da transação: `income` (receita) ou `expense` (despesa)
* `debit_account` - ID da conta bancária (obtenha em GET `/api/v1/settings` → `financial.banks[]`)
* `categories_id` - ID da categoria financeira (obtenha em GET `/api/v1/settings` → `financial.categories[]`)
* `cost_centers_id` - ID do centro de custo (obtenha em GET `/api/v1/settings` → `financial.cost_centers[]`)
* `amount` - Valor da transação em reais (use **vírgula** como separador decimal, ex: `"250,50"`)
* `date_due` - Data de vencimento (YYYY-MM-DD)

**Validações importantes:**

* `entry_type` DEVE corresponder ao tipo da categoria:
  * `entry_type="income"` aceita APENAS categorias com `type="CRÉDITO"`
  * `entry_type="expense"` aceita APENAS categorias com `type="DÉBITO"`
* Todos os IDs são validados se pertencem ao escritório autenticado
* `lawsuits_id` REQUER `customers_id` junto — sem ele retorna erro 422
* `date_payment` não pode ser futura (deve ser hoje ou passada)
* `amount` deve ser maior que zero — `amount: 0` causa erro 500 na API
* Execute GET `/api/v1/settings` primeiro para obter os IDs válidos

**Transformações automáticas:**

* Campo `description` é convertido para MAIÚSCULAS
* IDs são resolvidos para nomes no GET (users\_id→responsible, categories\_id→category)
* `entry_type` é retornado como `type` no GET
* `competence` é derivado automaticamente de `date_due` (mês/ano) — não precisa enviar

**Rate Limit:** 500 requisições por dia

## POST /transactions

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Crie uma nova transação financeira

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

**Campos obrigatórios:** users_id, entry_type, debit_account, categories_id, cost_centers_id, amount, date_due

| Campo | Tipo | Descrição |
|-------|------|----------|
| users_id | integer | **[Required]** ID do usuário responsável. Obtido via GET `/api/v1/settings` → `users[]` |
| entry_type | string | **[Required]** Tipo da transação: `income` (receita) ou `expense` (despesa). ⚠️ Deve corresponder ao tipo da categoria: income requer categorias tipo CRÉDITO, expense requer categorias tipo DÉBITO. |
| debit_account | integer | **[Required]** ID da conta de débito. Obtido via GET `/api/v1/settings` → `financial.banks[]` |
| categories_id | integer | **[Required]** ID da categoria. ⚠️ O tipo da categoria (CRÉDITO/DÉBITO) DEVE corresponder ao entry_type. Obtido via GET `/api/v1/settings` → `financial.categories[]` |
| cost_centers_id | integer | **[Required]** ID do centro de custo. Obtido via GET `/api/v1/settings` → `financial.cost_centers[]` |
| amount | — | **[Required]** Valor da transação em reais. Use **vírgula** como separador decimal (ex: `"250,50"`). ⚠️ O ponto é descartado (não funciona como decimal): `15.00` vira 1500. |
| date_due | string (date) | **[Required]** Data de vencimento no formato YYYY-MM-DD |
| customers_id | integer | **[Optional]** ID do cliente. Quando fornecido, popula os campos `name` e `identification` no GET |
| lawsuits_id | integer | **[Optional]** ID do processo. Popula o campo `lawsuit_id` no GET. ⚠️ **Requer `customers_id` junto** — enviar sem `customers_id` retorna erro 422 |
| sectors_id | integer | **[Optional]** ID do setor. Deve pertencer ao escritório autenticado, caso contrário retorna erro 422 |
| description | string | **[Optional]** Descrição da transação. Será convertida automaticamente para MAIÚSCULAS |
| date_payment | string (date) | **[Optional]** Data de pagamento no formato YYYY-MM-DD. ⚠️ Não pode ser futura (deve ser hoje ou passada) |

#### Exemplo: receita_simples — Receita (income) - Apenas campos obrigatórios

```json
{
  "users_id": 12345,
  "entry_type": "income",
  "debit_account": 1001,
  "categories_id": 100,
  "cost_centers_id": 500,
  "amount": "1.500,00",
  "date_due": "2026-03-15"
}
```

#### Exemplo: despesa_simples — Despesa (expense) - Apenas campos obrigatórios

```json
{
  "users_id": 12345,
  "entry_type": "expense",
  "debit_account": 1001,
  "categories_id": 200,
  "cost_centers_id": 500,
  "amount": "250,50",
  "date_due": "2026-03-10"
}
```

#### Exemplo: receita_completa — Receita (income) - Todos os campos

```json
{
  "users_id": 12345,
  "entry_type": "income",
  "debit_account": 1001,
  "categories_id": 100,
  "cost_centers_id": 500,
  "amount": "5.000,00",
  "date_due": "2026-03-20",
  "customers_id": 67890,
  "lawsuits_id": 54321,
  "description": "Honorários advocatícios - Processo ABC",
  "date_payment": "2026-02-10",
  "competence": "02/2026"
}
```

#### Exemplo: despesa_completa — Despesa (expense) - Todos os campos

```json
{
  "users_id": 12345,
  "entry_type": "expense",
  "debit_account": 1001,
  "categories_id": 200,
  "cost_centers_id": 500,
  "amount": "350,00",
  "date_due": "2026-03-05",
  "description": "Conta de água - Escritório",
  "date_payment": "2026-02-10",
  "competence": "02/2026"
}
```

### Respostas

#### 200 — Transação criada com sucesso

##### Exemplo

```json
{
  "success": true,
  "transactions_id": 12948208
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: campos_obrigatorios — Campos obrigatórios ausentes

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "entry_type": [
      "Select the transaction type: credit or debit"
    ],
    "users_id": [
      "The responsible user is required"
    ],
    "date_due": [
      "The date due field is required"
    ],
    "categories_id": [
      "The category field is required"
    ],
    "amount": [
      "The amount field is required"
    ],
    "debit_account": [
      "The bank account field is required"
    ],
    "cost_centers_id": [
      "The cost center field is required"
    ]
  }
}
```

##### Exemplo: categories_id_invalido — Categoria não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "categories_id": [
      "The category field is invalid"
    ]
  }
}
```

##### Exemplo: debit_account_invalido — Conta bancária não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "debit_account": [
      "The bank account is invalid"
    ]
  }
}
```

##### Exemplo: cost_centers_id_invalido — Centro de custo não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "cost_centers_id": [
      "validation.special_exists"
    ]
  }
}
```

##### Exemplo: users_id_invalido — Usuário não pertence ao escritório

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "users_id": [
      "You must enter a user associated with your office"
    ]
  }
}
```

##### Exemplo: date_due_invalida — Formato de data inválido (esperado: YYYY-MM-DD)

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "date_due": [
      "The date due is invalid"
    ],
    "competence": [
      "validation.date_format"
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha uma transação pelo ID
URL: /docs/transactions/getTransactionById
Última atualização: 06/03/2026 · doc v1.11.0 — Novo endpoint GET /transactions/{id}; atualização de transações disponível em /transactions/{id}. (histórico completo: /docs/changelog)

Retorna os dados completos de uma transação financeira específica baseado no seu ID único.

**Resposta inclui:**

* Dados financeiros (valor, tipo, categoria)
* Conta de débito e banco
* Centro de custo e departamento
* Datas de vencimento, pagamento e criação
* Vínculos com processo, cliente e departamento (quando houver)

## GET /transactions/{id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha uma transação pelo ID

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| id | integer | Sim | **[Required]** ID único da transação |

### Respostas

#### 200 — Transação encontrada com sucesso

##### Exemplo: encontrado — Transacao encontrada

```json
{
  "id": 5000001,
  "users_id": 100001,
  "debit_account": 135001,
  "bank": "CONTA PRINCIPAL",
  "categories_id": 1,
  "category": "HONORARIOS INICIAIS",
  "entry_type": "income",
  "cost_centers_id": 41001,
  "cost_center": "GERAL",
  "customers_id": 9000001,
  "lawsuits_id": 1234501,
  "departments_id": null,
  "department": null,
  "description": "HONORARIOS CONTRATUAIS",
  "amount": 5000,
  "date_due": "2026-04-30",
  "date_payment": null,
  "created_at": "2026-04-02 10:30:00"
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 404 — Registro não encontrado

##### Exemplo

```json
{
  "error": "Transaction not found"
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Obtenha uma lista de transações financeiras
URL: /docs/transactions/getTransactions
Última atualização: 23/03/2026 · doc v1.13.0 — Documentação de transações e tarefas ampliada e validada. (histórico completo: /docs/changelog)

Retorna lista de transações financeiras com diversos filtros opcionais incluindo informações de processos, clientes, datas e dados financeiros.

**Como funcionam os filtros:**

* Múltiplos filtros são combinados com **AND** (interseção)
* Filtros de texto como `responsible`, `customer_name`, `debit_bank`, `description`, `category` e `cost_center` são **busca parcial** (case-insensitive)
* Filtros como `lawsuit_id`, `process_number` são **busca exata**
* Filtros de data funcionam como **range** (use \_start e \_end juntos)
* `competence_start/end` usa formato **MM/YYYY** (ex: 03/2026), diferente dos demais filtros de data

A resposta inclui `totalCount`, `limit`, `offset` e array `data` com as transações.

## GET /transactions

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Obtenha uma lista de transações financeiras

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| lawsuit_id | integer | Não | **[Optional]** ID exato do processo associado à transação. |
| category | string | Não | **[Optional]** Busca parcial na categoria da transação. Case-insensitive. Exemplos: ALUGUEL, HONORÁRIOS, ENERGIA. |
| responsible | string | Não | **[Optional]** Busca parcial no nome do responsável. Case-insensitive. |
| customer_name | string | Não | **[Optional]** Busca parcial no nome do cliente. Case-insensitive. |
| debit_bank | string | Não | **[Optional]** Busca parcial no banco de débito. Case-insensitive. |
| cost_center | string | Não | **[Optional]** Busca parcial no centro de custo. Case-insensitive. |
| description | string | Não | **[Optional]** Busca parcial na descrição da transação. Case-insensitive. |
| process_number | string | Não | **[Optional]** Número exato do processo associado à transação (ex: 5003807-92.2020.8.24.0067). Busca exata - não aceita busca parcial. |
| protocol_number | string | Não | **[Optional]** Número do protocolo associado à transação. |
| customer_identification | string | Não | **[Optional]** CPF ou CNPJ do cliente. **IMPORTANTE:** Validação obrigatória - deve ser CPF/CNPJ válido, caso contrário retorna erro `Invalid identification.` |
| created_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data de criação (formato: YYYY-MM-DD). **Deve ser usado junto com `created_end`.** |
| created_end | string (date) | Não | **[Optional]** Data final para filtrar por data de criação (formato: YYYY-MM-DD). **Deve ser usado junto com `created_start`.** |
| date_due_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data de vencimento (formato: YYYY-MM-DD). **Deve ser usado junto com `date_due_end`.** |
| date_due_end | string (date) | Não | **[Optional]** Data final para filtrar por data de vencimento (formato: YYYY-MM-DD). **Deve ser usado junto com `date_due_start`.** |
| date_payment_start | string (date) | Não | **[Optional]** Data inicial para filtrar por data de pagamento (formato: YYYY-MM-DD). **Deve ser usado junto com `date_payment_end`.** |
| date_payment_end | string (date) | Não | **[Optional]** Data final para filtrar por data de pagamento (formato: YYYY-MM-DD). **Deve ser usado junto com `date_payment_start`.** |
| competence_start | string | Não | **[Optional]** Competência inicial para filtrar (formato: MM/YYYY, ex: 03/2026). **Deve ser usado junto com `competence_end`.** |
| competence_end | string | Não | **[Optional]** Competência final para filtrar (formato: MM/YYYY, ex: 03/2026). **Deve ser usado junto com `competence_start`.** |

### Respostas

#### 200 — Lista de transações financeiras retornada com sucesso

##### Exemplo: sem_filtro — Lista sem filtro (primeiros resultados)

```json
{
  "offset": 0,
  "limit": 1000,
  "totalCount": 42,
  "data": [
    {
      "id": 5000001,
      "entry_type": "income",
      "date_due": "2026-04-30",
      "date_payment": null,
      "competence": "04/2026",
      "amount": 5000,
      "description": "HONORARIOS CONTRATUAIS",
      "responsible": "MARIA SILVA",
      "category": "HONORARIOS INICIAIS",
      "lawsuit_id": 1234501,
      "process_number": "0001234-56.2026.5.15.0001",
      "protocol_number": null,
      "name": "JOAO PEREIRA",
      "identification": "111.222.333-44",
      "debit_bank": "CONTA PRINCIPAL",
      "credit_bank": null,
      "cost_center": "GERAL"
    },
    {
      "id": 5000002,
      "entry_type": "expense",
      "date_due": "2026-04-15",
      "date_payment": "2026-04-15",
      "competence": "04/2026",
      "amount": 350,
      "description": null,
      "responsible": "CARLOS SOUZA",
      "category": "CUSTAS PROCESSUAIS",
      "lawsuit_id": null,
      "process_number": null,
      "protocol_number": null,
      "name": null,
      "identification": null,
      "debit_bank": "CONTA PRINCIPAL",
      "credit_bank": null,
      "cost_center": "GERAL"
    }
  ]
}
```

##### Exemplo: com_filtro — Lista com filtro por categoria

```json
{
  "offset": 0,
  "limit": 1000,
  "totalCount": 12,
  "data": [
    {
      "id": 5000001,
      "entry_type": "income",
      "date_due": "2026-04-30",
      "date_payment": null,
      "competence": "04/2026",
      "amount": 5000,
      "description": "HONORARIOS CONTRATUAIS",
      "responsible": "MARIA SILVA",
      "category": "HONORARIOS INICIAIS",
      "lawsuit_id": 1234501,
      "process_number": "0001234-56.2026.5.15.0001",
      "protocol_number": null,
      "name": "JOAO PEREIRA",
      "identification": "111.222.333-44",
      "debit_bank": "CONTA PRINCIPAL",
      "credit_bank": null,
      "cost_center": "GERAL"
    }
  ]
}
```

##### Exemplo: vazio — Nenhuma transacao encontrada

```json
{
  "offset": 0,
  "limit": 1000,
  "totalCount": 0,
  "data": []
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```



# Atualize uma transação financeira existente
URL: /docs/transactions/updateTransaction
Última atualização: 16/06/2026 · doc v1.21.0 — Padronização do formato do campo `amount`: use vírgula como separador decimal (ex: `"250,50"`). (histórico completo: /docs/changelog)

Atualiza campos de uma transação financeira (receita ou despesa) existente no sistema.

**Campos alteráveis:**

* `entry_type` - Tipo da transação (income/expense)
* `categories_id` - Categoria financeira
* `amount` - Valor da transação (use **vírgula** como separador decimal, ex: `"250,50"`)
* `date_due` - Data de vencimento
* `date_payment` - Data de pagamento (marcar como paga/em aberto)
* `description` - Descrição
* `competence` - Competência (MM/YYYY)

**Validações importantes:**

* Para alterar `categories_id`, é **OBRIGATÓRIO** enviar `entry_type` junto (validação de tipo ativa)
* Validação de tipo continua: `entry_type="income"` aceita APENAS categorias `type="CRÉDITO"`
* Validação de tipo continua: `entry_type="expense"` aceita APENAS categorias `type="DÉBITO"`
* Pode alterar múltiplos campos simultaneamente
* Para marcar como **paga**: envie `"date_payment": "2026-02-10"`
* Para marcar como **em aberto**: envie `"date_payment": null`

**Resposta:**

* Sempre retorna `{"success":true,"lawsuits_id":"ID"}` (não `transactions_id`)

**Rate Limit:** 500 requisições por dia

## PUT /transactions/{id}

**Autenticação:** Bearer Token (header `Authorization: Bearer <token>`)

Atualize uma transação financeira existente

### Parâmetros de Path

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|----------|
| id | integer | Sim | ID da transação a ser atualizada |

### Corpo da Requisição (application/json)

*Corpo obrigatório.*

| Campo | Tipo | Descrição |
|-------|------|----------|
| entry_type | string | **[Optional]** Tipo da transação: `income` (receita) ou `expense` (despesa). ⚠️ **OBRIGATÓRIO ao alterar `categories_id`** (validação de tipo) |
| categories_id | integer | **[Optional]** ID da categoria financeira. ⚠️ **Deve enviar `entry_type` junto** (validação de tipo). Obtido via GET `/api/v1/settings` → `financial.categories[]` |
| amount | — | **[Optional]** Valor da transação em reais. Use **vírgula** como separador decimal (ex: `"250,50"`). ⚠️ O ponto é descartado (não funciona como decimal): `15.00` vira 1500. |
| date_due | string (date) | **[Optional]** Data de vencimento no formato YYYY-MM-DD |
| date_payment | — | **[Optional]** Data de pagamento no formato YYYY-MM-DD. Use `null` para marcar como em aberto, ou uma data para marcar como paga |
| description | string | **[Optional]** Descrição da transação. Será convertida automaticamente para MAIÚSCULAS |
| competence | string | **[Optional]** Competência no formato MM/YYYY (ex: 05/2026) |

#### Exemplo: corrigir_valor — Corrigir valor de uma transação

```json
{
  "amount": "2.500,00"
}
```

#### Exemplo: mudar_vencimento — Mudar data de vencimento

```json
{
  "date_due": "2026-06-30"
}
```

#### Exemplo: marcar_como_paga — Marcar transação como paga

```json
{
  "date_payment": "2026-02-11"
}
```

#### Exemplo: marcar_em_aberto — Marcar transação como em aberto

```json
{
  "date_payment": null
}
```

#### Exemplo: mudar_tipo — Alterar tipo da transação (despesa → receita)

```json
{
  "entry_type": "income",
  "categories_id": 105
}
```

#### Exemplo: multiplas_alteracoes — Atualizar múltiplos campos simultaneamente

```json
{
  "amount": "850,00",
  "date_due": "2026-07-20",
  "date_payment": "2026-02-11",
  "description": "Pagamento de fornecedor XYZ",
  "competence": "07/2026"
}
```

### Respostas

#### 200 — Transação atualizada com sucesso

##### Exemplo

```json
{
  "success": true,
  "lawsuits_id": "98765432"
}
```

#### 401 — Não autenticado — token inválido ou ausente

##### Exemplo

```json
{
  "error": "Unauthenticated."
}
```

#### 404 — Registro não encontrado

##### Exemplo

```json
{
  "error": "Transaction not found"
}
```

#### 422 — Dados inválidos — um ou mais campos falharam na validação

##### Exemplo: entry_type_obrigatorio — entry_type obrigatório ao atualizar

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "entry_type": [
      "Select the transaction type: credit or debit"
    ]
  }
}
```

##### Exemplo: date_due_invalida — Formato de data inválido

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "date_due": [
      "The date due is invalid"
    ]
  }
}
```

##### Exemplo: categories_id_invalido — Categoria inválida ou não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "categories_id": [
      "The category field is invalid"
    ]
  }
}
```

##### Exemplo: debit_account_invalido — Conta bancária não pertence à conta

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "debit_account": [
      "The bank account is invalid"
    ]
  }
}
```

##### Exemplo: competence_invalido — Formato de competência inválido (esperado: MM/YYYY)

```json
{
  "message": "The given data was invalid.",
  "errors": {
    "competence": [
      "validation.date_format"
    ]
  }
}
```

#### 429 — Limite de requisições atingido — aguarde antes de tentar novamente

##### Exemplo

```json
{
  "message": "Too Many Requests"
}
```

