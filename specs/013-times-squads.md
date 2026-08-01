# 013 — Times (squads)

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 012 · **Status:** ✅ concluída

---

## 1. Objetivo

Agrupar colaboradores em times para atribuir tarefa ao grupo inteiro de uma vez, em vez de
selecionar pessoa por pessoa.

## 2. Escopo

- Tabelas `squads` e `squad_members`
- CRUD com seleção múltipla de membros
- Aba `Configurações > Usuários > Times`

## 3. Fora de escopo

- Atribuição de tarefa a time → 032 (aqui só o cadastro)

## 4. Modelo de dados

```sql
CREATE TABLE squads (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE squad_members (
  squad_id UUID NOT NULL REFERENCES squads(id) ON DELETE CASCADE,
  user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  PRIMARY KEY (squad_id, user_id)
);
```
RLS nas duas. Migration `013_squads.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/squads?status=&q=&cursor=` | autenticado |
| POST | `/api/v1/squads` | ADMINISTRADOR |
| GET/PUT/DELETE | `/api/v1/squads/{id}` | ADMINISTRADOR |

`PUT` recebe `member_ids[]` completo e reconcilia (não é patch incremental).

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `ConfirmDialog`
**Cria:** `SquadForm` (nome + lista de checkboxes de colaboradores)
**Rota:** `/settings/users?tab=squads`

Colunas: Nome do time · Membros (contagem + avatares) · Cadastro

## 7. Regras de negócio

1. Nome único por tenant.
2. Time pode existir vazio, mas a UI avisa.
3. Remover membro **não** apaga o usuário nem as tarefas já atribuídas a ele.
4. Inativar usuário o remove das listas de atribuição, mas ele permanece no time.
5. Excluir time não afeta tarefas já criadas a partir dele.
6. `PUT` com `member_ids[]` reconcilia: adiciona os novos, remove os ausentes.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD completo | ~0,4 s |
| integração | nome duplicado → 409 | ~0,2 s |
| integração | reconciliação de membros no PUT | ~0,4 s |
| integração | excluir time não apaga usuários | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | `SquadForm` seleciona múltiplos | ~0,4 s |

**Total:** ~2,0 s

## 9. Descobertas

**`squad_members` usa PK surrogate, não a composta da seção 4.** A spec declara
`PRIMARY KEY (squad_id, user_id)`, mas toda outra tabela do projeto herda `Base`, que
define `id UUID` como PK única — `Base` não foi desenhado para acomodar PK composta.
Implementado com `id UUID` surrogate + `UNIQUE(squad_id, user_id)`: mesma garantia de
unicidade (um par squad+usuário não se repete), consistente com o resto do código em vez
de um caso especial isolado.

**Bug real: `session.refresh()` necessário depois de reconciliar membros.**
`SquadService.update()` seta `squad.name`/`squad.is_active` e depois chama
`reconcile_members`, que faz um `SELECT` — esse `SELECT` dispara autoflush do `UPDATE`
pendente do squad. Como `updated_at` é `onupdate=func.now()` (o valor real só existe
depois que o Postgres computa), o SQLAlchemy marca o atributo como expirado após esse
autoflush. Sem um `await self.session.refresh(squad)` explícito antes de devolver a
resposta, o primeiro acesso síncrono a `squad.updated_at` (dentro de `_to_response`, na
serialização) tentava recarregar via I/O fora de um contexto async válido e quebrava com
`MissingGreenlet`. Achado pelos dois testes que fazem PUT (`test_crud_completo`,
`test_listagem_filtra_por_status`) — nenhum teste de account/users (011/012) tinha essa
combinação exata (setattr + query subsequente antes de responder), então o mesmo bug
estrutural não apareceu lá (mas pode existir latente se algum fluxo futuro repetir o
padrão "muda campo + consulta relacionada antes de responder").

**Sem N+1 na listagem: uma query só para os membros de todas as squads da página.**
`get_members_for_squads(squad_ids)` busca `squad_members JOIN users` filtrado por
`squad_id IN (...)` de uma vez, agrupando em Python — evita uma query por squad ao montar
"Membros (contagem + avatares)" na listagem.

**Rota é `?tab=` na mesma tela de Usuários, não uma rota própria — igual ADVBOX.**
`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` linha 56 confirma: "Abas Colaboradores e Times" na
mesma tela `users`. `UsersSettingsPage` (nova) lê `?tab=` da URL e alterna entre
`<UsersListPage>` (012, inalterado) e `<SquadsListPage>` (nova) — nenhuma rota
`/settings/squads` separada.

**`SquadForm` recebe `form` em vez de ter seu próprio `useForm`.** Diferente de
`AccountForm`/`UserForm` (formulários de página inteira, com `useForm` próprio),
`SquadForm` só existe dentro de um `FormModal` (não há rota de detalhe de time) — para
reutilizar de verdade o `FormModal` da spec 007 (que já gerencia `useForm`/erro de
servidor/dirty guard internamente), `SquadForm` recebe o `form: UseFormReturn<...>` via
prop e só renderiza os campos, igual o padrão já usado por `InviteUserModal` (012).

**Checkbox de membro usa o registro nativo do react-hook-form para grupos.** Vários
`<input type="checkbox" value={id}>` registrados no MESMO nome de campo (`member_ids`)
via `register("member_ids")` — RHF coleta os valores marcados num array automaticamente,
sem precisar de `useFieldArray` nem de `Controller` manual.

**Nenhuma jornada e2e nova; máximo de 25 continua 2/25.** O plano de testes da spec não
pede e2e — CRUD e reconciliação já cobertos por integração, seleção múltipla por teste de
frontend.

## 10. Definição de pronto

- [x] Migration `013_squads.py` aplicada — `squads` (nome único por tenant) e
      `squad_members` (RLS, índices de FK) com RLS ligado nas duas
- [x] CRUD completo com RBAC (autenticado lista, ADMINISTRADOR cria/edita/exclui)
- [x] Nome único por tenant (409 na criação e na renomeação); time pode existir vazio
- [x] `PUT` com `member_ids[]` reconcilia (adiciona novos, remove ausentes) sem apagar
      usuário nem afetar tarefas
- [x] Excluir time não afeta usuários nem tarefas já criadas a partir dele
- [x] `SquadForm` criado (dentro de `FormModal`); `DataTable`/`ConfirmDialog` reutilizados;
      abas Colaboradores/Times na mesma tela `/settings/users?tab=squads`
- [x] Todos os testes do plano (seção 8) escritos, mais testes adicionais de cobertura de
      erro (renomear para nome existente, 404 em PUT/DELETE, busca textual)
- [x] `make lint` verde (ruff, black, mypy --strict, eslint, tsc, prettier)
- [x] `make test` verde, wall-clock ~40s (< 120s)
- [x] `test-timing.json` atualizado
- [x] `ROADMAP.md` → ✅
- [x] Commit `feat(013): times (squads)`
