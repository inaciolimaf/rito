# Isolamento entre tenants — inventário de políticas

> Entregável da spec 080 (refatoração de Gestão e BI). Registra **cada** política de
> Row Level Security do banco, cada exceção ao isolamento padrão e o teste que cobre
> cada uma. O inventário é executável: `tests/integration/test_isolation_matrix.py` lê
> o catálogo do Postgres e falha se aparecer política, exceção ou tabela sem RLS que
> não esteja aqui.

## 1. O padrão

`app/core/rls.py::enable_rls_statements(tabela)` é o único jeito de ligar RLS no
projeto. Ele emite sempre as mesmas quatro coisas:

```sql
ALTER TABLE "t" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "t" FORCE ROW LEVEL SECURITY;      -- sem isto o DONO da tabela lê tudo
CREATE POLICY tenant_isolation ON "t"
  USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE INDEX ix_t_tenant ON "t" (tenant_id);
```

Estado atual: **56 políticas em 54 tabelas**, das quais **50 são exatamente esta**.
As outras 6 estão na seção 3, uma a uma.

Duas garantias sustentam o resto:

- **A aplicação roda como `rito_app`**, criada `NOSUPERUSER NOBYPASSRLS` na migration
  003. Superusuário ignora RLS mesmo com `FORCE` — por isso a URL de superusuário
  (`MIGRATIONS_DATABASE_URL`) só existe para `alembic upgrade` e para o `REFRESH
  MATERIALIZED VIEW CONCURRENTLY` dos workers, nunca no caminho de uma request.
  Coberto por `test_role_da_aplicacao_nao_ignora_rls` e
  `test_nenhum_modulo_da_app_troca_de_role_ou_usa_conexao_de_migration`.
- **Nenhum service filtra tenant no `WHERE`.** `set_tenant_context()` seta
  `app.tenant_id` no início da transação e quem isola é sempre a política.

## 2. Views materializadas: a barreira

Postgres não aplica RLS em view materializada. Por isso toda matview de agregação
(039, 059, 071, 073, 074, 075, 076, 077) é lida através de uma **view barreira**
`<nome>_visible`, que embute `WHERE tenant_id = current_setting('app.tenant_id',
true)::uuid` e é a única com `GRANT SELECT` para `rito_app`. A matview crua não é
acessível pela role da aplicação — só pelo superusuário que faz o refresh.

## 3. As seis exceções

Cada uma está em `DOCUMENTED_EXCEPTIONS` no teste de auditoria; mexer numa das duas
pontas sem a outra quebra a suíte.

### 3.1 `external_requests` — política `tenant_isolation`

```sql
USING ((tenant_id IS NULL) OR (tenant_id = current_setting('app.tenant_id', true)::uuid))
```

Auditoria de chamada HTTP externa (spec 050). Uma sync agendada (DJEN, DataJud) não
roda em nome de um escritório: a linha nasce com `tenant_id NULL` e é telemetria do
sistema, visível a todos. Nenhum dado de escritório trafega nessas linhas — o corpo
gravado é o da chamada ao tribunal.

### 3.2 `integration_alerts` — política `tenant_isolation`

```sql
USING ((tenant_id IS NULL) OR (tenant_id = current_setting('app.tenant_id', true)::uuid))
```

Mesma natureza (spec 049): "o DJEN está fora do ar" é um alerta do sistema, não de um
escritório. Alertas com `tenant_id` preenchido (um termo monitorado falhando, por
exemplo) seguem a regra normal.

### 3.3 e 3.4 `partnerships` — políticas `partnerships_read` e `partnerships_write`

```sql
partnerships_read  (SELECT) USING (requester_tenant_id = current OR partner_tenant_id = current)
partnerships_write (ALL)    USING/CHECK (requester_tenant_id = current)
```

A parceria (spec 079) pertence aos **dois** escritórios — é a primeira linha do banco
sem dono único, e por isso a única tabela de domínio sem `tenant_id`. Leitura para as
duas pontas; escrita só para quem convidou. Aceitar e encerrar mexem na linha do outro
lado e passam pelas funções `partnership_accept`/`partnership_end`, não por uma
política de UPDATE — uma política de UPDATE para o lado convidado deixaria ele mudar o
próprio escopo de acesso.

### 3.5 e 3.6 `shared_lawsuits` — políticas `shared_lawsuits_read` e `shared_lawsuits_write`

```sql
shared_lawsuits_read  (SELECT) USING (owner_tenant_id = current OR partner_tenant_id = current)
shared_lawsuits_write (ALL)    USING/CHECK (owner_tenant_id = current)
```

O compartilhamento de um processo é visível aos dois lados (o parceiro precisa saber o
escopo que recebeu), mas só o dono cria, altera e revoga.

## 4. A fronteira do tenant: as funções `SECURITY DEFINER`

O acesso do parceiro ao processo compartilhado **não** afrouxa nenhuma política acima.
Ele passa por 11 funções `SECURITY DEFINER` criadas na migration 079 (mais
`lookup_ical_feed`, da spec 037, que resolve o token público do feed iCal). Todas são
`SET search_path = public`, pertencem ao superusuário da migration e repetem o mesmo
guarda:

```sql
EXISTS (SELECT 1 FROM shared_lawsuits s JOIN partnerships p ON p.id = s.partnership_id
        WHERE s.lawsuit_id = <alvo>
          AND s.partner_tenant_id = current_setting('app.tenant_id', true)::uuid
          AND s.revoked_at IS NULL AND p.status = 'ATIVA')
```

| Função | O que atravessa |
|---|---|
| `partner_share_for` | o escopo do compartilhamento (é o guarda que as outras consultam) |
| `partner_shared_lawsuits` | os processos compartilhados com o tenant da sessão |
| `partner_shared_parties` | as partes de um processo compartilhado |
| `partner_shared_timeline` | as movimentações de um processo compartilhado |
| `partner_shared_tasks` | as tarefas de um processo compartilhado |
| `partner_shared_task_types` | o catálogo de tipos de tarefa do dono, para a demanda |
| `partner_create_task` | **a única escrita cross-tenant do sistema** |
| `partnership_accept` | aceite do convite (linha do outro lado) |
| `partnership_end` | encerramento + revogação dos dois lados |
| `partnership_email_has_account` | booleano: o e-mail convidado já tem conta |
| `partner_pending_demands` | as contagens dos cards, das duas pontas |
| `lookup_ical_feed` | `(tenant_id, user_id)` a partir do token do feed (spec 037) |

Consequência desenhada: o parceiro recebe **404** em `/api/v1/lawsuits/{id}` mesmo do
processo compartilhado. Ele só chega ao processo pelas rotas
`/api/v1/partnerships/shared-with-me/...`. Nenhuma listagem, relatório tabular,
dashboard ou view de BI dele enxerga a linha do dono, porque nenhuma delas passa por
essas funções.

Regra 9 da 079 é aplicada dentro do banco: `partner_shared_lawsuits` devolve
`CASE WHEN can_view_financial THEN case_value END`. Sem permissão o valor não sai do
Postgres.

## 5. O que a exceção de parceria **não** alcança

Verificado por teste (`test_partnerships.py`, `test_partner_isolation.py`):

| Superfície | Resultado para o parceiro |
|---|---|
| `GET /lawsuits`, `GET /lawsuits/{id}` | lista vazia / 404 |
| `GET /customers` | só os contatos do próprio escritório |
| `GET /transactions`, `/lawsuits/{id}/financial-summary` | nada do dono |
| `GET /templates` | só os modelos do próprio escritório |
| `GET /reports/tabular/*`, `/lawsuits/stats` | zero linhas do dono |
| `GET /bi/*` (7 matviews) | zero linhas do dono |
| `GET /documents` | nada do dono |

## 6. Modelos públicos (spec 068) não são uma exceção

`public_templates` é catálogo **global e imutável**, sem `tenant_id` e sem RLS — mesma
natureza de `courts`, `steps` e `occupations`. Copiar um modelo público clona o
conteúdo para um `templates` do tenant. Não há interação possível com a exceção de
parceria: são tabelas diferentes, e `templates` segue com a política padrão.

## 7. Testes que sustentam este documento

| Teste | O que garante |
|---|---|
| `test_isolation_matrix.py::test_toda_tabela_com_tenant_id_tem_rls_ligado_e_forcado` | tabela nova não nasce sem RLS |
| `…::test_toda_tabela_com_rls_tem_politica` | RLS ligado sem política (esconde tudo) |
| `…::test_toda_excecao_de_politica_esta_documentada` | exceção nova quebra a suíte até ser justificada aqui |
| `…::test_role_da_aplicacao_nao_ignora_rls` | `rito_app` continua `NOBYPASSRLS`/`NOSUPERUSER` |
| `…::test_nenhum_modulo_da_app_troca_de_role_ou_usa_conexao_de_migration` | nenhuma request escapa pela conexão de superusuário |
| `…::test_matriz_leitura_escrita_por_tenant` | B não lê, não atualiza, não apaga e não insere como A |
| `test_partner_isolation.py` | a exceção de parceria não vazou para financeiro, modelos, documentos nem BI |
| `test_partnerships.py` (5 testes de vazamento) | o parceiro vê o processo compartilhado e nada mais |
| `test_rls.py` | a política padrão, ponta a ponta, na tabela-sonda |
