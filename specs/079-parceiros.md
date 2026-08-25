# 079 — Parceiros

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 027 · **Status:** ✅ concluída

---

## 1. Objetivo

Escritórios que trabalham juntos em processos — correspondente em outro estado, parceria de
captação, banca especializada. A funcionalidade mais delicada do produto do ponto de vista de
isolamento: é o **único caso em que dado atravessa a fronteira do tenant**.

## 2. Escopo

- Convite por e-mail e aceite
- Rede de parceiros
- Compartilhamento de processo com escopo restrito
- Demandas pendentes de cada lado
- Filtros e relatório da parceria

## 3. Fora de escopo

- Repasse financeiro automático entre escritórios (fora do escopo)
- Chat entre parceiros (usa comentário da tarefa compartilhada)

## 4. Modelo de dados

```sql
CREATE TYPE partnership_status AS ENUM ('PENDENTE','ATIVA','RECUSADA','ENCERRADA');

CREATE TABLE partnerships (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  requester_tenant_id UUID NOT NULL REFERENCES tenants(id),
  partner_tenant_id UUID REFERENCES tenants(id),     -- nulo até o aceite
  invited_email CITEXT NOT NULL,
  status partnership_status NOT NULL DEFAULT 'PENDENTE',
  token_hash TEXT UNIQUE,
  invited_by UUID NOT NULL REFERENCES users(id),
  accepted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (requester_tenant_id, invited_email)
);

CREATE TABLE shared_lawsuits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  partnership_id UUID NOT NULL REFERENCES partnerships(id) ON DELETE CASCADE,
  owner_tenant_id UUID NOT NULL REFERENCES tenants(id),
  partner_tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  can_view_financial BOOLEAN NOT NULL DEFAULT false,
  can_create_tasks BOOLEAN NOT NULL DEFAULT true,
  shared_by UUID NOT NULL REFERENCES users(id),
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (lawsuit_id, partner_tenant_id)
);
CREATE INDEX ix_shared_partner ON shared_lawsuits (partner_tenant_id) WHERE revoked_at IS NULL;
```
Migration `079_partnerships.py`.

**Política de RLS estendida** em `lawsuits`, `posts` e `lawsuit_parties`:
`SELECT` permite `tenant_id = current_tenant` **ou** existe `shared_lawsuits` ativo para o
processo com `partner_tenant_id = current_tenant`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/partnerships?status=` | ADMINISTRADOR |
| POST | `/api/v1/partnerships/invite` → `{email}` | GESTOR |
| POST | `/api/v1/partnerships/accept` → `{token}` | GESTOR |
| POST | `/api/v1/partnerships/{id}/end` | GESTOR |
| POST | `/api/v1/lawsuits/{id}/share` → `{partnership_id, can_view_financial, can_create_tasks}` | ADMINISTRADOR |
| DELETE | `/api/v1/lawsuits/{id}/share/{share_id}` | ADMINISTRADOR |
| GET | `/api/v1/partnerships/shared-with-me?report=&status=&steps[]=` | autenticado |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `StatCard`, `EntityPicker`, `ConfirmDialog`
**Cria:** `PartnersPage`, `InvitePartnerDialog`, `ShareLawsuitDialog` (com escopo explícito),
`SharedBadge`, `PartnerNetworkList`
**Rota:** `/partners`

Cards: Processos compartilhados ativos · Demanda pendente pelo escritório · Demanda pendente pelo parceiro

## 7. Regras de negócio

1. Parceria é **bilateral e simétrica** — aceita uma vez, vale para os dois lados.
2. Convite para e-mail sem conta no Rito envia convite de cadastro; a parceria fica `PENDENTE`.
3. Compartilhar é **por processo**, nunca a carteira inteira. Não existe "compartilhar tudo".
4. O parceiro enxerga: dados do processo, partes, timeline e tarefas. **Não** enxerga: outros processos, contatos não relacionados, financeiro (salvo `can_view_financial`), configurações, relatórios e BI.
5. `can_create_tasks` permite ao parceiro criar tarefa no processo compartilhado; sem isso, é só leitura.
6. Revogar o compartilhamento corta o acesso imediatamente; o que o parceiro criou permanece.
7. Encerrar a parceria revoga **todos** os compartilhamentos, dos dois lados.
8. Tarefa criada por parceiro é marcada com a origem e aparece nas duas caixas de entrada.
9. Parceiro **nunca** vê valor financeiro sem `can_view_financial`, mesmo com `financial_access = FULL` no tenant dele.
10. "Demanda pendente pelo parceiro" = tarefas atribuídas ao parceiro, não concluídas.
11. Toda ação de compartilhamento é auditada.
12. Processo compartilhado exibe badge permanente, para ninguém esquecer que há terceiro olhando.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | convite → aceite → parceria ativa | ~0,5 s |
| integração | convite para e-mail sem conta fica pendente | ~0,3 s |
| integração | compartilhar dá acesso ao processo | ~0,4 s |
| integração | **parceiro NÃO vê outros processos do dono** | ~0,5 s |
| integração | **parceiro NÃO vê contatos não relacionados** | ~0,4 s |
| integração | **parceiro NÃO vê financeiro sem permissão** | ~0,4 s |
| integração | parceiro com `can_view_financial` vê | ~0,3 s |
| integração | parceiro sem `can_create_tasks` não cria → 403 | ~0,3 s |
| integração | revogar corta o acesso na hora | ~0,4 s |
| integração | revogar preserva o que o parceiro criou | ~0,3 s |
| integração | encerrar parceria revoga tudo dos dois lados | ~0,4 s |
| integração | tarefa de parceiro aparece nas duas inboxes | ~0,4 s |
| integração | **parceiro não acessa BI nem relatórios do dono** | ~0,4 s |
| frontend | diálogo mostra o escopo do compartilhamento | ~0,4 s |

**Total:** ~5,4 s

> Os cinco testes marcados são de **vazamento entre tenants**. São os mais importantes do
> projeto inteiro — um furo aqui expõe carteira de cliente a concorrente.

## 9. Descobertas

- **Nenhuma política de RLS existente foi afrouxada.** A spec §4 previa estender o
  `SELECT` de `lawsuits`/`posts`/`lawsuit_parties` com um `OR EXISTS (shared_lawsuits…)`.
  Escrito assim, o processo do parceiro passaria a entrar em TODA query dele — listagem,
  `/lawsuits/stats`, relatórios tabulares e as matviews de BI —, o que viola a regra 4
  ("não enxerga relatórios e BI") num lugar longe daqui, onde ninguém procuraria. O
  acesso cross-tenant ficou concentrado em 11 funções `SECURITY DEFINER` na migration
  079 (mesmo padrão de `lookup_ical_feed`, spec 037), todas com o mesmo guarda: existe
  `shared_lawsuits` não revogado, de parceria `ATIVA`, para
  `current_setting('app.tenant_id')`. Consequência boa: o parceiro pede o processo
  compartilhado pela rota `/partnerships/shared-with-me/...` e recebe 404 na rota normal
  `/lawsuits/{id}` — os testes de vazamento afirmam as duas coisas.
- **`partnerships` e `shared_lawsuits` são as únicas tabelas sem `tenant_id`** — a linha
  pertence aos dois lados. Política escrita à mão: leitura para as duas pontas, escrita
  só para o lado dono. Aceitar e encerrar tocam a linha do outro lado e por isso passam
  por função, não por política de UPDATE: uma política de UPDATE para o parceiro deixaria
  ele mudar `can_view_financial` do próprio compartilhamento.
- **Regra 9 é aplicada dentro do banco, não no serializer.** `partner_shared_lawsuits()`
  devolve `CASE WHEN can_view_financial THEN case_value END` — sem permissão o valor nem
  sai do Postgres, então não há caminho de resposta que possa vazá-lo por engano.
- **A "caixa de entrada do parceiro" é a lista do processo compartilhado**, não o
  `/inbox`. A tarefa criada pelo parceiro nasce no tenant do DONO (é ele quem executa),
  marcada com `posts.partner_tenant_id`, e cai no `/inbox` do responsável pelo processo
  — essa metade da regra 8 está literal. A outra metade não: para a mesma linha aparecer
  no `/inbox` do parceiro seria preciso que ele enxergasse `posts`, `post_users` E
  `task_types` do dono por RLS, exatamente o afrouxamento recusado acima. O parceiro vê a
  demanda em `GET /partnerships/shared-with-me/{id}` (com `from_partner: true`) e no card
  "Demanda pendente pelo parceiro". Se a paridade literal for necessária, a saída é uma
  view de inbox unificada — fica anotado para a refatoração 080.
- **Sem envio de e-mail**, igual ao convite de usuário (spec 012): o token volta na
  resposta de `POST /partnerships/invite` e `account_exists` distingue os dois convites
  da regra 2 (parceria x cadastro). Infra de e-mail transacional continua pendente no
  projeto inteiro.
- **`GET /partnerships/{id}` não existe** — a spec §5 não pede e a tela lê tudo da
  listagem. `GET /lawsuits/{id}/shares` foi acrescentada (não estava na tabela §5) porque
  o badge permanente da regra 12 precisa saber com quem o processo está compartilhado;
  ela é COLABORADOR, já que o badge aparece para todo mundo.
- **Rota de filtro `steps[]`** é aplicada em Python sobre o retorno da função (a lista de
  compartilhados é pequena por definição — regra 3 proíbe compartilhar a carteira). O
  `report=true` devolve a contagem por fase e o total de tarefas em aberto no mesmo
  endpoint.
- **Custo medido:** os 13 testes de integração rodam em ~9 s isolados num worker
  (~5 s dentro do `-n 2` da suíte, que os distribui) e o teste de frontend em ~0,35 s;
  `make test` segue dentro do orçamento.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (regra 8 com o desvio documentado acima)
- [x] Teste de isolamento por tenant — os 5 testes de vazamento
- [x] `make test` verde e dentro do orçamento
- [x] `make lint` verde
- [x] Sem `Any`/`as any`/`# type: ignore` sem justificativa
- [x] Componentes reutilizados: `DataTable`, `StatCard`, `EmptyState`, `ConfirmDialog`
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(079): parceiros`
