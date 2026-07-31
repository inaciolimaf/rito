# 022 — Processos: modelo e CRUD

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 021, 015 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(022): processos — modelo e CRUD`
