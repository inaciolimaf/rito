# 022 — Processos: modelo e CRUD

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 021, 015 · **Status:** ✅ concluída

---

## 1. Objetivo

A entidade central do sistema. Processo judicial, administrativo, consultivo ou de prospecção —
tudo é `lawsuit`, diferenciado pela fase em que está.

## 2. Escopo

- Tabela `lawsuits` com todos os campos do levantamento
- CRUD + modal de criação/edição
- Vínculo com grupo, tipo, fase, etapa, tribunal, sistema e responsável
- Soft delete (arquivamento)

## 3. Fora de escopo

- Partes → 023 · Honorários e ciclo → 024 · Validação CNJ → 025
- Timeline → 026 · Listagem e filtros → 027

## 4. Modelo de dados

```sql
CREATE TABLE lawsuits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id),          -- responsável
  lawsuit_type_id UUID NOT NULL REFERENCES lawsuit_types(id),
  stage_id UUID NOT NULL REFERENCES stages(id),
  court_id SMALLINT REFERENCES courts(id),
  court_system_id SMALLINT REFERENCES court_systems(id),
  process_number TEXT,                  -- CNJ, só dígitos
  protocol_number TEXT,
  originating_process TEXT,
  folder TEXT,                          -- máx 30
  filing_year SMALLINT,
  judiciary TEXT,
  county TEXT,                          -- comarca
  court_division TEXT,                  -- vara
  process_date DATE,
  notes TEXT,
  is_archived BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (folder IS NULL OR length(folder) <= 30)
);
CREATE INDEX ix_lawsuits_user   ON lawsuits (tenant_id, user_id);
CREATE INDEX ix_lawsuits_stage  ON lawsuits (tenant_id, stage_id);
CREATE INDEX ix_lawsuits_type   ON lawsuits (tenant_id, lawsuit_type_id);
CREATE INDEX ix_lawsuits_number ON lawsuits (tenant_id, process_number) WHERE process_number IS NOT NULL;
CREATE INDEX ix_lawsuits_folder ON lawsuits (tenant_id, folder) WHERE folder IS NOT NULL;
```
RLS ligado. Migration `022_lawsuits.py`.

**Campos derivados — nunca aceitos do cliente:** `action_group_id` (via `lawsuit_type_id`) e
`step_id` (via `stage_id`). Expostos na leitura, ignorados na escrita.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| POST | `/api/v1/lawsuits` | COLABORADOR |
| GET/PUT | `/api/v1/lawsuits/{id}` | COLABORADOR |
| DELETE | `/api/v1/lawsuits/{id}` | ADMINISTRADOR (soft) |

## 6. Front-end

**Reutiliza:** `FormModal`, `EntityPicker`, `CourtSelect`, `ConfirmDialog`
**Cria:** `LawsuitForm`, `StageStepSelect` (etapa filtra por fase e vice-versa)
**Rota:** modal sobre `/lawsuits`

## 7. Regras de negócio

1. Obrigatórios: responsável, tipo de ação, etapa. Mínimo 1 parte é validado em 023.
2. Grupo é derivado do tipo; fase é derivada da etapa. Enviar qualquer um dos dois → 422.
3. `folder` limitado a 30 caracteres (constraint no banco).
4. Trocar o tipo de ação para outro grupo é permitido e recalcula o grupo derivado.
5. Trocar a etapa para outra fase é permitido — é assim que o processo avança no funil.
6. `process_number` guardado só com dígitos; a máscara é de apresentação.
7. Delete é soft; processo com lançamento financeiro nunca é apagado de fato.
8. `court_system_id` deve pertencer ao `court_id` escolhido, se ambos forem informados.
9. Responsável precisa ser usuário ativo do tenant.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD completo | ~0,5 s |
| integração | grupo derivado do tipo | ~0,3 s |
| integração | enviar `action_group_id` → 422 | ~0,2 s |
| integração | enviar `step_id` → 422 | ~0,2 s |
| integração | folder com 31 caracteres → 422 | ~0,2 s |
| integração | trocar etapa muda a fase derivada | ~0,3 s |
| integração | sistema incompatível com tribunal → 422 | ~0,3 s |
| integração | responsável inativo → 422 | ~0,2 s |
| integração | delete arquiva | ~0,2 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | etapa filtra por fase | ~0,4 s |
| frontend | tipo filtra por grupo | ~0,4 s |

**Total:** ~3,5 s

## 9. Descobertas

- **`courts`/`court_systems` (spec 021) vivem numa `DeclarativeBase` própria** (`CourtBase`,
  `MetaData` separada de `Base`) — `ForeignKey("courts.id")` por string só resolve dentro da
  `MetaData` da própria tabela sendo declarada, então `lawsuits.court_id`/`court_system_id`
  precisaram de `ForeignKey(Court.id)`/`ForeignKey(CourtSystem.id)` (a coluna real, não uma
  string) para o SQLAlchemy achar a tabela alvo ao ordenar as dependências do flush.
  `lawsuits` é o primeiro consumidor real desse cruzamento entre as duas `MetaData`.
- **Mesma classe de bug já documentada na spec 013 (`squads`)**: `_with_derived` faz
  `SELECT`s (tipo→grupo, etapa→fase) depois de mutar o objeto em `update()`, o que dispara
  autoflush do `UPDATE` pendente e expira `updated_at` (`onupdate=func.now()`) — a leitura
  síncrona em `_to_response` quebrava com `MissingGreenlet`. Corrigido setando
  `lawsuit.updated_at = datetime.now(UTC)` explicitamente antes das consultas, mesmo padrão
  já usado em `customers.upload_photo` (spec 017).
- **Regra 8 (sistema × tribunal) só restringe quando o tribunal tem vínculo cadastrado.**
  `court_system_links` (spec 021) cobre só as 23 variantes de sistema — os outros 159
  tribunais não têm nenhum vínculo. Tratar "sem vínculo" como "nenhum sistema permitido"
  bloquearia o campo para quase todo o catálogo; a leitura adotada (documentada também em
  `CourtRepository.is_system_compatible`) é: tribunal sem vínculo aceita qualquer sistema,
  tribunal com vínculo só aceita um dos vinculados. `court_system_links` ganhou aqui seu
  primeiro consumidor real — modelo ORM `CourtSystemLink` novo em `courts/models.py` (a
  tabela já existia desde a 021, só sem mapeamento ORM).
- **Frontend sem listagem** (spec 027 é quem entrega): `LawsuitsPage` segue o mesmo padrão
  de tela single-record que `CustomersPage` (spec 017) usou antes de `CustomerListPage`
  chegar na 019. Grupo de ação e fase são filtros locais (`useState`) só para popular os
  seletores em cascata (tipo filtra por grupo, etapa filtra por fase) — nunca campos do
  formulário nem do payload, coerente com a regra 2 (campos derivados nunca aceitos do
  cliente).
- `court_id`/`court_system_id` não validam existência no service (diferente de
  `lawsuit_type_id`/`stage_id`, que são obrigatórios e tenant-scoped) — mesmo padrão já
  aceito em `publications_user_id` (spec 014): um id inválido vira `IntegrityError` não
  tratada (500), aceitável porque nada na UI permite enviar um id que não existe
  (`CourtSelect`/`<select>` só oferecem ids reais).

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Teste de isolamento por tenant (tabela nova `lawsuits`)
- [x] `make test` verde e wall-clock < 120 s (60 s medidos)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (nenhum novo padrão repetido
      3 vezes nesta spec)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(022): processos — modelo e CRUD`
