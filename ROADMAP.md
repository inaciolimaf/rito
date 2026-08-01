# Rito — Roadmap de Specs

**100 specs · 90 de feature · 10 de refatoração** (a cada 10ª, terminando em refatoração).

Legenda de status: `⬜ pendente` · `🔄 em andamento` · `✅ concluída`

Orçamento (`t`) é o **acréscimo máximo ao wall-clock** de `make test` que a spec pode causar.
A soma de todos os acréscimos não pode levar o total acima de **120 s**.

---

## Fase 0 — Fundação (001–010)

### ✅ 001 — Monorepo, tooling e ambiente
Estrutura `backend/`, `frontend/`, `e2e/`; Docker Compose com Postgres 16 + Redis 7; Makefile com todos os alvos; `.env.example`; pre-commit (ruff, black, eslint, prettier).
**Aceite:** `make up && make dev` sobe tudo do zero em máquina limpa. **t:** 0 s. **Deps:** —

### ✅ 002 — Esqueleto do backend
FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic Settings, healthcheck, error handler RFC 7807, logging estruturado.
**Aceite:** `GET /health` retorna 200; migration inicial aplica. **t:** 3 s. **Deps:** 001

### ✅ 003 — Multi-tenancy com RLS
Tabela `tenants`; `tenant_id` + política RLS; `set_tenant_context()` na sessão; middleware que resolve tenant; `BaseRepository`.
**Aceite:** tenant A não lê linha de tenant B nem com query crua. **t:** 5 s. **Deps:** 002

### ✅ 004 — Autenticação
`users`, hash Argon2, login, JWT access + refresh, rotação, logout, recuperação de senha, política de senha (8+, número, minúscula, maiúscula, especial).
**Aceite:** ciclo completo de login/refresh/logout; senha fraca rejeitada. **t:** 6 s. **Deps:** 003

### ✅ 005 — RBAC e acesso financeiro
Perfis Gestor/Administrador/Colaborador; dimensão independente de acesso financeiro (Sem acesso / Somente visualizador / Acesso completo); dependency `require_role` / `require_financial`.
**Aceite:** Colaborador recebe 403 em rota de Gestor; financeiro respeitado nos 3 níveis. **t:** 4 s. **Deps:** 004

### ✅ 006 — Esqueleto do frontend
Vite + React + TS strict + Tailwind + shadcn/ui; design tokens; **dark mode**; TanStack Query; React Router; client de API com refresh automático; tela de login.
**Aceite:** login funcional; alternância de tema persiste. **t:** 8 s. **Deps:** 004

### ✅ 007 — Design system de domínio
`DataTable` (ordenação, paginação keyset, seleção, ações de linha, export xlsx/pdf), `FilterBar` declarativo, `FormModal` por schema Zod, `EntityPicker`, `StatCard`, `EmptyState`, `ConfirmDialog`.
**Aceite:** cada componente com stories e testes; usados por uma tela de demonstração. **t:** 12 s. **Deps:** 006

### ✅ 008 — App shell
Sidebar com os 15 itens, header, busca global (Tudo/Pessoas/Processos), dropdown "Adicionar", breadcrumbs, layout responsivo, rotas protegidas.
**Aceite:** navegação completa entre módulos com placeholders. **t:** 5 s. **Deps:** 007

### ⬜ 009 — Pipeline de testes e gate de 120 s
`pytest -n auto` + template DB + rollback por teste; Vitest threads; Playwright sharded; `make test` roda as 3 concorrentes; script que **falha se wall-clock > 120 s**; GitHub Actions.
**Aceite:** CI verde e reporta wall-clock. **t:** 0 s (é a própria infra). **Deps:** 002, 006

### ⬜ 010 — 🔧 REFATORAÇÃO — Fundação
Pente fino em 001–009: cobertura, SOLID, duplicação, tipos frouxos, tempo de suíte.
**Aceite:** sem mudança de comportamento; testes antigos passam sem edição. **t:** −

---

## Fase 1 — Cadastros base (011–020)

### ⬜ 011 — Escritório (account)
Dados do escritório: razão social, fantasia, CNPJ, endereço, e-mails principal e financeiro, site, logotipo, **timezone** (8 opções BR/PT).
**Aceite:** CRUD + upload de logo. **t:** 3 s. **Deps:** 005

### ⬜ 012 — Usuários
CRUD, convite por e-mail, 66 cargos, OAB/UF, jornada (`work_start`/`interval`/`end`), salário, admissão/demissão, meta de pontos, ativo/inativo.
**Aceite:** convite gera cadastro pendente; jornada valida. **t:** 6 s. **Deps:** 011

### ⬜ 013 — Times (squads)
CRUD de times com membros; atribuição de tarefa a time inteiro (preparo).
**Aceite:** time com N membros; remoção não apaga usuário. **t:** 3 s. **Deps:** 012

### ⬜ 014 — Grupos e tipos de ação
`groups` (6 padrão) com responsável por intimações; `type_lawsuits` vinculados a grupo; transferência em lote.
**Aceite:** tipo herda grupo; transferência remaneja processos. **t:** 4 s. **Deps:** 011

### ⬜ 015 — Fases e etapas
`steps` (9 fixas, seed imutável); `stages` (59 padrão) com fase, `enable_stagnant_days`, `stagnant_days`, workflow sugerido; transferência em lote.
**Aceite:** etapa sempre pertence a uma fase; estagnação configurável. **t:** 4 s. **Deps:** 014

### ⬜ 016 — Origem de pessoas
CRUD das origens (8 padrão) + transferência em lote.
**Aceite:** origem em uso não é apagada sem transferência. **t:** 2 s. **Deps:** 011

### ⬜ 017 — Contatos: modelo e CRUD
PF/PJ no mesmo modelo com discriminador; todos os campos do levantamento; bloco de representante legal.
**Aceite:** PF e PJ com validações distintas; representante opcional. **t:** 6 s. **Deps:** 016

### ⬜ 018 — Contatos: validação e endereço
Validação real de CPF/CNPJ com bloqueio de duplicidade; CEP `99999-999`; consulta ViaCEP; telefone com DDD e sem DDI; estados e cidades.
**Aceite:** CPF inválido rejeitado; duplicidade bloqueada; ViaCEP mockado. **t:** 4 s. **Deps:** 017

### ⬜ 019 — Contatos: listagem e dashboard
`DataTable` com filtros (tipo, estado, cidade, origem, período, arquivados); dashboard Top Origens, Faixa etária, Top Profissões; aniversariantes; export.
**Aceite:** filtros combinam com AND; export gera xlsx. **t:** 6 s. **Deps:** 018, 007

### ⬜ 020 — 🔧 REFATORAÇÃO — Cadastros
**t:** −

---

## Fase 2 — Processos (021–030)

### ⬜ 021 — Tribunais e sistemas
Seed dos **182 tribunais** e **13 sistemas processuais**; relação tribunal↔sistema.
**Aceite:** seed idempotente; busca por sigla. **t:** 2 s. **Deps:** 011

### ⬜ 022 — Processos: modelo e CRUD
Todos os campos do levantamento; `folder` (30 chars); protocolo; processo originário; anotações.
**Aceite:** CRUD completo; campos derivados (`group`, `step`) nunca aceitos do cliente. **t:** 6 s. **Deps:** 021, 015

### ⬜ 023 — Processos: partes
N:N com contatos e **polo** (ativo / passivo / parte contrária); mínimo 1 parte.
**Aceite:** processo sem parte é rejeitado; mesma pessoa em polos distintos. **t:** 4 s. **Deps:** 022, 017

### ⬜ 024 — Processos: honorários e ciclo
`fees_expec`, `fees_money`, `fees_percentage`, contingenciamento (3 níveis); datas `status_closure`, `exit_production`, `exit_execution`.
**Aceite:** valores monetários corretos; datas de ciclo coerentes entre si. **t:** 3 s. **Deps:** 022

### ⬜ 025 — Validação de número CNJ
Parser do formato `NNNNNNN-DD.AAAA.J.TR.OOOO`; dígito verificador (módulo 97 base 10); extração de ano, segmento, tribunal e origem.
**Aceite:** DV inválido rejeitado; segmentos extraídos corretamente. **t:** 2 s. **Deps:** 022

### ⬜ 026 — Processos: timeline unificada
Agrega tarefas, movimentações (auto e manual), publicações e lançamentos financeiros, com toggle por tipo; ordenação cronológica; paginação.
**Aceite:** toggles filtram; ordenação estável. **t:** 6 s. **Deps:** 024

### ⬜ 027 — Processos: listagem e filtros
12 visões rápidas (ativos, movimentados 7/30 dias, parados +30/+45/+90, fechamentos do mês…); filtros avançados; export.
**Aceite:** cada visão bate com o SQL esperado em fixture. **t:** 7 s. **Deps:** 026

### ⬜ 028 — Processos: dashboard
Cards de ativos, fechamentos com variação, arquivados no mês; gráfico volume por fase; meta de fechamentos.
**Aceite:** números conferem com seed determinístico. **t:** 4 s. **Deps:** 027

### ⬜ 029 — Pastas e organização
Campo `folder` com autocomplete, agrupamento por pasta, busca.
**Aceite:** agrupamento e busca funcionam. **t:** 3 s. **Deps:** 027

### ⬜ 030 — 🔧 REFATORAÇÃO — Processos
**t:** −

---

## Fase 3 — Tarefas e Taskscore (031–040)

### ⬜ 031 — Catálogo de tarefas e Taskscore
152 tarefas padrão; complexidade (5 níveis) × tempo médio (5 faixas) → **calculadora de pontuação** com sugestão editável; vínculo com fase; só Gestor edita.
**Aceite:** matriz de pontuação determinística e testada célula a célula. **t:** 4 s. **Deps:** 015

### ⬜ 032 — Tarefas: modelo e CRUD
`posts` como entidade central; múltiplos responsáveis; vínculo a processo; data, hora, prazo fatal, local, descrição.
**Aceite:** tarefa exige processo e ≥1 responsável; duplicata detectada. **t:** 6 s. **Deps:** 031, 022

### ⬜ 033 — Tarefas: flags e conclusão
Importante, urgente, futura, privada, retroativa (com `date_completed`); conclusão por responsável; pontuação creditada na conclusão.
**Aceite:** retroativa credita na data informada; privada invisível a terceiros. **t:** 4 s. **Deps:** 032

### ⬜ 034 — Tarefas: recorrência
8 periodicidades + `repeat_on_week` (dia exato / 1ª / 2ª / 3ª / última semana); geração da próxima ocorrência.
**Aceite:** série mensal "última semana" resolve corretamente em meses de 4 e 5 semanas. **t:** 4 s. **Deps:** 033

### ⬜ 035 — Tarefas: comentários e anexos
Thread de comentários, `@menções` com notificação, anexos múltiplos.
**Aceite:** menção notifica; anexo respeita quota. **t:** 5 s. **Deps:** 032

### ⬜ 036 — Caixa de entrada
6 seções configuráveis (Prazo fatal, Intimações, Não lidas, Urgentes, Importantes, Demais); ordem por usuário; ações em massa; marcação de leitura.
**Aceite:** reordenação persiste; ação em massa transacional. **t:** 6 s. **Deps:** 033, 007

### ⬜ 037 — Agenda
Visões mês/semana/dia/agenda; filtro por usuário e por data de compromisso vs prazo fatal; **feed iCal por usuário** (só tarefas com "Mostrar na agenda").
**Aceite:** iCal válido consumível pelo Google Agenda; sincronização unidirecional. **t:** 7 s. **Deps:** 033

### ⬜ 038 — Workflow
Modelo de sequência (tarefa + responsável opcional + prazo em dias úteis); editor; disparo ao mudar de etapa; cálculo de dias úteis com feriados nacionais.
**Aceite:** workflow de 5 etapas gera 5 tarefas com datas corretas. **t:** 5 s. **Deps:** 034, 015

### ⬜ 039 — Metas, ranking e Taskscore dashboard
Meta mensal por grupo de ação e por usuário; ranking com "classificar por" (pontuação, volume, atrasadas, envolvimento); período mensal ou ELTV; gráfico mês atual × anterior × meta.
**Aceite:** ranking determinístico com seed. **t:** 5 s. **Deps:** 036

### ⬜ 040 — 🔧 REFATORAÇÃO — Tarefas
**t:** −

---

## Fase 4 — Integração CNJ (041–050)

### ⬜ 041 — Cliente HTTP resiliente
Camada comum: retry com backoff exponencial, rate limit por host, circuit breaker, timeout, cache condicional, **gravação de fixtures** para teste.
**Aceite:** 429 aciona backoff; circuito abre após N falhas. **t:** 4 s. **Deps:** 002

### ⬜ 042 — DJEN: client e modelo
Client de `comunicaapi.pje.jus.br/api/v1/comunicacao` (**sem autenticação**, exige user-agent de browser); modelo com todos os campos, incluindo `destinatarios[]` e `destinatarioadvogados[]`; payload bruto em JSONB.
**Aceite:** parse fiel contra fixture real gravada. **t:** 4 s. **Deps:** 041

### ⬜ 043 — Termos monitorados
CRUD de termos (OAB/UF, CPF, CNPJ); vínculo a usuário; status de monitoramento; custo por termo.
**Aceite:** termo duplicado bloqueado; status transita corretamente. **t:** 4 s. **Deps:** 042

### ⬜ 044 — DJEN: sincronização
Worker Celery beat diário + sync manual; **deduplicação por `hash`**; tratamento de `status`/`motivo_cancelamento` (publicação anulada); janela de datas; paginação.
**Aceite:** reprocessar o mesmo payload não duplica; cancelamento marca a comunicação. **t:** 6 s. **Deps:** 043

### ⬜ 045 — Intimação → tarefa
Roteamento: responsável do **grupo de ação** do processo → senão **responsável geral**; casamento por `numero_processo` e por `destinatarioadvogados[].advogado_id`; cria tarefa do tipo "Intimações Judiciais"; `data_disponibilizacao` como base de prazo.
**Aceite:** os 3 caminhos de roteamento testados. **t:** 5 s. **Deps:** 044, 032

### ⬜ 046 — DataJud: client
Client de `api-publica.datajud.cnj.jus.br` com **APIKey pública em configuração** (nunca hardcode); alias por tribunal; query Elasticsearch; alerta em 401 (chave rotacionada).
**Aceite:** parse contra fixture; 401 gera alerta. **t:** 3 s. **Deps:** 041

### ⬜ 047 — DataJud: andamentos
Sync de capa e `movimentos[]` com códigos da tabela CNJ; só processos cadastrados; `dataHoraUltimaAtualizacao` para incremental.
**Aceite:** movimento novo aparece na timeline; reprocesso não duplica. **t:** 5 s. **Deps:** 046, 026

### ⬜ 048 — Módulo Intimações
Tela de listagem com filtros (período, usuário, cliente, tribunal, número); leitura; vínculo manual a processo.
**Aceite:** filtros combinam; vínculo manual cria relação. **t:** 5 s. **Deps:** 045, 007

### ⬜ 049 — Observabilidade da sincronização
Painel de status por termo; histórico de execuções; **falha vira tarefa** para o responsável; métricas de captura.
**Aceite:** falha simulada gera tarefa de alerta. **t:** 4 s. **Deps:** 048

### ⬜ 050 — 🔧 REFATORAÇÃO — Integrações CNJ
**t:** −

---

## Fase 5 — CRM e Financeiro I (051–060)

### ⬜ 051 — CRM: board Kanban
`KanbanBoard` reutilizável; colunas por fase; drag & drop; mudança de fase persiste; virtualização para volume.
**Aceite:** arrastar card muda a fase no banco. **t:** 7 s. **Deps:** 027, 007

### ⬜ 052 — CRM: estagnação e métricas
Marcação de estagnado por `stagnant_days` da etapa; filtro estagnados/em andamento; cards de topo (processos, recebidos no mês, valor, estagnado).
**Aceite:** estagnação calculada a partir da última tarefa. **t:** 4 s. **Deps:** 051

### ⬜ 053 — CRM: workflow ao mover
Sugestão de workflow ao mover para etapa configurada; confirmação; criação das tarefas.
**Aceite:** mover para etapa com workflow sugere e cria após confirmar. **t:** 4 s. **Deps:** 052, 038

### ⬜ 054 — Financeiro: plano de contas
10 grupos DRE; 61 categorias padrão (14 receita, 47 despesa); centros de custo; CRUD.
**Aceite:** categoria sempre tem grupo e tipo; seed idempotente. **t:** 3 s. **Deps:** 011

### ⬜ 055 — Financeiro: contas e cartões
5 tipos; ~95 instituições; agência, número, `cycle_day`, `due_day`, saldo inicial, conta padrão.
**Aceite:** cartão exige ciclo e vencimento; só uma conta padrão. **t:** 4 s. **Deps:** 054

### ⬜ 056 — Financeiro: lançamentos
Receita / despesa / **transferência**; **validação `entry_type` × tipo da categoria**; vínculo cliente e processo (processo exige cliente); descrição em maiúsculas; competência derivada do vencimento.
**Aceite:** receita com categoria de despesa é rejeitada; transferência move saldo entre contas. **t:** 6 s. **Deps:** 055

### ⬜ 057 — Financeiro: recorrência e parcelamento
Recorrente com ciclo; parcelado até 100x com geração das parcelas; edição da série.
**Aceite:** 12x gera 12 lançamentos com vencimentos mensais corretos. **t:** 5 s. **Deps:** 056

### ⬜ 058 — Financeiro: registro interno e anexos
Flag "apenas registro interno" (não afeta saldo); anexos por lançamento.
**Aceite:** registro interno não entra no saldo. **t:** 3 s. **Deps:** 056

### ⬜ 059 — Financeiro: dashboard e fluxo de caixa
Saldo com variação, receita/despesa prevista vs realizada, atrasados; 4 regimes de visualização (pagamento, vencimento, competência, **fluxo de caixa**); saldo por conta.
**Aceite:** cada regime muda a agregação corretamente. **t:** 6 s. **Deps:** 058

### ⬜ 060 — 🔧 REFATORAÇÃO — CRM e Financeiro I
**t:** −

---

## Fase 6 — Financeiro II, Documentos e Modelos (061–070)

### ⬜ 061 — Financeiro: inadimplência
Identificação de atrasados, régua de cobrança, notificações por e-mail/SMS/WhatsApp (adapters mockáveis).
**Aceite:** atrasado detectado no vencimento+1; régua dispara nos marcos. **t:** 5 s. **Deps:** 059

### ⬜ 062 — Financeiro: relatórios DRE e DFC
Agrupamento por grupo DRE; DRE e DFC por período; export.
**Aceite:** DRE fecha com o razão em seed determinístico. **t:** 5 s. **Deps:** 061

### ⬜ 063 — Documentos e nuvem
Storage S3-compatible atrás de interface `FileStorage` (MinIO em dev); upload múltiplo, pastas, URL assinada temporária, quota por plano.
**Aceite:** URL expira; quota excedida bloqueia upload. **t:** 6 s. **Deps:** 002

### ⬜ 064 — Modelos: biblioteca
CRUD de modelos; tipos contrato/petição/recurso/documento; busca; lixeira.
**Aceite:** filtro por tipo; restauração da lixeira. **t:** 4 s. **Deps:** 063

### ⬜ 065 — Modelos: editor
TipTap com cabeçalho, rodapé, marca d'água, tabelas, imagens, listas, formatação completa; autosave.
**Aceite:** documento salva e reabre idêntico. **t:** 8 s. **Deps:** 064

### ⬜ 066 — Modelos: engine de variáveis
Variáveis de cliente, processo, escritório e usuário; **valores por extenso** (datas e dinheiro); resolução com dados reais; variável ausente sinalizada.
**Aceite:** todas as variáveis do levantamento resolvem; extenso correto. **t:** 5 s. **Deps:** 065

### ⬜ 067 — Modelos: geração e envio
Render para PDF; download; envio por e-mail; salvar na nuvem do processo.
**Aceite:** PDF gerado com cabeçalho/rodapé. **t:** 6 s. **Deps:** 066

### ⬜ 068 — Biblioteca pública de modelos
Modelos do sistema visíveis a todos os tenants; copiar para o escritório.
**Aceite:** cópia vira modelo editável do tenant. **t:** 3 s. **Deps:** 064

### ⬜ 069 — Notificações
Config por evento (novo cliente, novo processo, parceiros, intimações) com responsável ou "não notificar"; canais e-mail/SMS/WhatsApp; preferências por usuário.
**Aceite:** evento roteia para o configurado. **t:** 4 s. **Deps:** 035

### ⬜ 070 — 🔧 REFATORAÇÃO — Documentos e Modelos
**t:** −

---

## Fase 7 — Gestão, BI e Parceiros (071–080)

### ⬜ 071 — Relatórios: Agilidade e Produtividade
Gráfico concluídas em dia / em atraso / pendentes; tarefas com mais atraso; colaboradores com mais atraso; agilidade geral; produtividade semanal.
**Aceite:** números batem com seed. **t:** 5 s. **Deps:** 039

### ⬜ 072 — Relatórios tabulares
7 relatórios (produtividade, tarefas atrasadas, registros de acesso, novos clientes, novos processos, ganhos, perdidos) com filtros e export.
**Aceite:** cada relatório com teste de agregação. **t:** 6 s. **Deps:** 071

### ⬜ 073 — Registro de acessos e livro de ponto
Log de acesso (data, IP, primeiro/último login) com toggle; livro de ponto a partir da jornada.
**Aceite:** acesso registrado só com toggle ligado. **t:** 4 s. **Deps:** 012

### ⬜ 074 — BI: Estoque e Prospecção
Oportunidades do mês, ativos, arquivados, parados +120 dias, fechamentos com evolução de 6 meses, funil e taxa de conversão por grupo.
**Aceite:** indicadores conferem com seed. **t:** 5 s. **Deps:** 072

### ⬜ 075 — BI: Safra e Qualidade
Taxa de sucesso por grupo de ação; safra por ano de fechamento; ciclo de vida; comparação histórica; considera só concluídos.
**Aceite:** processos em tramitação excluídos do cálculo. **t:** 5 s. **Deps:** 074

### ⬜ 076 — BI: Tempo e Honorários
Média por processo, média mensal, **tempo perdido**; ciclos prospecção/produção/execução/rotação; tempo médio por fase e grupo.
**Aceite:** ciclos calculados a partir da timeline. **t:** 5 s. **Deps:** 075

### ⬜ 077 — BI: Custos
CAC, custo médio em produção, execução, rotação completa e **custo por ponto**; considera processos em andamento.
**Aceite:** custo por ponto = despesa ÷ pontos do período. **t:** 5 s. **Deps:** 076

### ⬜ 078 — BI: camada de agregação
Materialized views + refresh a cada 8 h; relatórios tabulares em tempo real; invalidação sob demanda.
**Aceite:** view refresca; tabela não usa cache. **t:** 4 s. **Deps:** 077

### ⬜ 079 — Parceiros
Convite por e-mail, rede, compartilhamento de processos, demandas pendentes de cada lado, filtros.
**Aceite:** processo compartilhado visível aos dois tenants com escopo restrito. **t:** 6 s. **Deps:** 027

### ⬜ 080 — 🔧 REFATORAÇÃO — Gestão e BI
**t:** −

---

## Fase 8 — Inteligência Artificial (081–090)

### ⬜ 081 — Camada LLM (OpenRouter)
Client genérico OpenRouter atrás da interface `LLMProvider`; **modelo selecionável por feature** em `ai_feature_config` com UI; streaming SSE; contagem de tokens e custo em `ai_usage`; fallback de modelo; fixtures gravadas.
**Aceite:** trocar modelo pela UI muda a chamada; nenhuma chamada real em teste. **t:** 5 s. **Deps:** 041

### ⬜ 082 — Runtime LangGraph
Grafos de agente; checkpointer em Postgres; interrupção para **human-in-the-loop**; retomada; timeout; observabilidade de passos.
**Aceite:** grafo interrompe, persiste e retoma após confirmação. **t:** 6 s. **Deps:** 081

### ⬜ 083 — Ferramentas de leitura
Tool registry tipado: consultar processos, clientes, tarefas, agenda, financeiro, métricas, intimações. **Sem RAG** — contexto por tool calling. Toda tool respeita RLS e RBAC do usuário.
**Aceite:** tool não retorna dado de outro tenant nem além do RBAC. **t:** 6 s. **Deps:** 082

### ⬜ 084 — Ferramentas de escrita
Criar cliente/processo/tarefa, mudar etapa, criar lançamento. Fluxo obrigatório: propor → `AIActionPreview` → confirmar → executar → `ai_audit_log`.
**Aceite:** nenhuma escrita ocorre sem confirmação; auditoria registra antes/depois. **t:** 6 s. **Deps:** 083

### ⬜ 085 — Copiloto global
Chat lateral em todo o sistema, ciente da tela atual; streaming; histórico por usuário; sugestões contextuais; seleção de modelo.
**Aceite:** pergunta sobre dados reais responde via tools. **t:** 8 s. **Deps:** 084

### ⬜ 086 — IA em intimações
Resumo, classificação do tipo de ato, **cálculo de prazo** (dias úteis, feriados, base `data_disponibilizacao`), tarefa sugerida com responsável e data; leitura automática opcional.
**Aceite:** prazo calculado confere em casos de fixture; sugestão sempre revisável. **t:** 6 s. **Deps:** 085, 045

### ⬜ 087 — Agentes de petição
19 agentes por área do direito; coletam contexto por tool calling; geram peça no editor; usam modelos do escritório como base.
**Aceite:** agente produz peça com dados reais do processo. **t:** 7 s. **Deps:** 086, 066

### ⬜ 088 — IA no editor
Continuar escrevendo, reescrever trecho, ajustar tom, revisar peça com checklist, sugerir fundamentação.
**Aceite:** ações aplicam no documento com desfazer. **t:** 6 s. **Deps:** 087

### ⬜ 089 — IA analítica
Text-to-SQL **guardrailed** (allowlist de tabelas/colunas, somente leitura, limite de linhas) para métricas; next-best-action por processo; detecção de risco (prazo, estagnação, inadimplência).
**Aceite:** SQL fora da allowlist é bloqueado; injeção não escapa. **t:** 6 s. **Deps:** 085, 078

### ⬜ 090 — 🔧 REFATORAÇÃO — IA
**t:** −

---

## Fase 9 — Automação, API e produção (091–100)

### ⬜ 091 — Extração de documentos
Upload → OCR → LLM → campos estruturados → **preview** → cadastro de cliente ou processo.
**Aceite:** PDF de fixture gera cadastro correto após confirmação. **t:** 6 s. **Deps:** 084, 063

### ⬜ 092 — Automação: gatilhos e ações
Motor gatilho → ação → tempo. Gatilhos: tarefa concluída, mudança de etapa. Ações: criar tarefa, definir responsável, calcular prazo, aguardar condição.
**Aceite:** fluxo de 3 passos executa na ordem com os prazos certos. **t:** 6 s. **Deps:** 038

### ⬜ 093 — Automação: webhooks outbound
HTTP Request com payload padronizado (os dois formatos do levantamento); assinatura HMAC; retry; log de entrega.
**Aceite:** payload bate com o contrato; retry em 5xx. **t:** 5 s. **Deps:** 092

### ⬜ 094 — Automação com decisão por LLM
Nó de decisão via LangGraph dentro do fluxo; ramificação condicional por análise do LLM.
**Aceite:** decisão ramifica corretamente com fixture. **t:** 5 s. **Deps:** 093, 082

### ⬜ 095 — API pública v1
Bearer token por tenant; rate limit (30 GET/min, 500 POST/dia); endpoints de customers, lawsuits, posts, publications, transactions, documents, settings; OpenAPI.
**Aceite:** rate limit retorna 429; contrato validado contra schema. **t:** 7 s. **Deps:** 059, 048

### ⬜ 096 — Busca global
Busca unificada (Tudo / Pessoas / Processos) com ranking, `pg_trgm`, atalho `/`.
**Aceite:** busca por nome parcial e por CNJ. **t:** 4 s. **Deps:** 027

### ⬜ 097 — Observabilidade
Logs estruturados com `tenant_id` e `request_id`, tracing OpenTelemetry, métricas Prometheus, healthchecks profundos.
**Aceite:** trace atravessa request → celery task. **t:** 3 s. **Deps:** 002

### ⬜ 098 — Performance
Auditoria de índices, eliminação de N+1, paginação keyset em todas as listas, budget de queries por endpoint em teste.
**Aceite:** nenhum endpoint acima do budget de queries. **t:** 4 s. **Deps:** 096

### ⬜ 099 — Deploy
Dockerfile multi-stage de produção, migrations no boot, seed opcional, variáveis documentadas, runbook.
**Aceite:** imagem sobe e serve com Postgres externo. **t:** 2 s. **Deps:** 098

### ⬜ 100 — 🔧 REFATORAÇÃO FINAL
Pente fino geral: SOLID, duplicação, cobertura, tipos, orçamento de teste, dívidas anotadas.
**Aceite:** suíte < 120 s; zero `# type: ignore` sem justificativa. **t:** −

---

## Orçamento acumulado

| Fase | Acréscimo |
|---|---|
| 0 — Fundação | 33 s |
| 1 — Cadastros | 28 s |
| 2 — Processos | 31 s |
| 3 — Tarefas | 36 s |
| 4 — CNJ | 35 s |
| 5 — CRM/Fin I | 39 s |
| 6 — Docs/Modelos | 41 s |
| 7 — Gestão/BI | 39 s |
| 8 — IA | 50 s |
| 9 — Produção | 42 s |

A soma bruta (374 s) **excede o teto** — e é isso que torna as specs de refatoração obrigatórias:
cada uma tem como critério de saída **devolver o wall-clock para baixo de 90 s**, via paralelismo,
substituição de e2e por integração, fixtures mais enxutas e template database.
O gate real é sempre o wall-clock de `make test`, nunca a soma teórica.
