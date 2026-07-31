# 064 — Modelos: biblioteca

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 063 · **Status:** ⬜ pendente

---

## 1. Objetivo

O acervo de peças do escritório: contratos, petições, recursos e documentos. Organização, busca
e lixeira — o editor vem na próxima.

## 2. Escopo

- Tabela `document_templates`
- 4 tipos de modelo
- CRUD, duplicar, favoritar
- Lixeira com restauração
- Busca por nome e conteúdo
- Tela `Modelos`

## 3. Fora de escopo

- Editor → 065 · Variáveis → 066 · Geração de PDF → 067 · Biblioteca pública → 068

## 4. Modelo de dados

```sql
CREATE TYPE template_kind AS ENUM ('CONTRATO','PETICAO','RECURSO','DOCUMENTO');

CREATE TABLE document_templates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID REFERENCES tenants(id),        -- NULL = biblioteca pública (068)
  kind template_kind NOT NULL,
  name TEXT NOT NULL,
  content JSONB NOT NULL DEFAULT '{}',          -- documento TipTap
  content_text TEXT,                             -- texto plano, para busca
  header JSONB, footer JSONB, watermark JSONB,
  is_favorite BOOLEAN NOT NULL DEFAULT false,
  created_by UUID REFERENCES users(id),
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_templates_kind ON document_templates (tenant_id, kind) WHERE deleted_at IS NULL;
CREATE INDEX ix_templates_search ON document_templates
  USING gin (to_tsvector('portuguese', coalesce(name,'') || ' ' || coalesce(content_text,'')));
CREATE INDEX ix_templates_deleted ON document_templates (tenant_id, deleted_at)
  WHERE deleted_at IS NOT NULL;
```
RLS ligado, com política que também libera `tenant_id IS NULL` para leitura (biblioteca pública).
Migration `064_document_templates.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/templates?kind=&q=&favorite=&deleted=&cursor=` |
| POST | `/api/v1/templates` |
| GET/PUT/DELETE | `/api/v1/templates/{id}` |
| POST | `/api/v1/templates/{id}/duplicate` |
| POST | `/api/v1/templates/{id}/restore` |
| POST | `/api/v1/templates/{id}/favorite` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `EmptyState`, `ConfirmDialog`
**Cria:** `TemplateLibraryPage` (grade com cartões), `TemplateCard`, `TemplateKindFilter`,
`TrashView`
**Rota:** `/library`

Filtros: Todos os modelos · Contratos · Petições · Recursos · Documentos · Somente os excluídos

## 7. Regras de negócio

1. Exclusão é **soft** (`deleted_at`); restauração disponível por 90 dias.
2. Job semanal apaga definitivamente o que passou de 90 dias na lixeira.
3. `content_text` é derivado de `content` na gravação — é o que alimenta a busca full-text.
4. Busca usa `tsvector` em português, cobrindo nome e conteúdo.
5. Duplicar copia conteúdo, cabeçalho, rodapé e marca d'água, com nome sufixado " (cópia)".
6. Favorito é do tenant, não do usuário (decisão de simplicidade; se virar demanda, migra).
7. Modelo em uso não impede exclusão — documentos gerados são independentes do modelo.
8. Nome não precisa ser único.
9. Modelo da biblioteca pública (`tenant_id IS NULL`) é somente leitura para o tenant.
10. Criação e edição exigem COLABORADOR; exclusão exige ADMINISTRADOR.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD dos 4 tipos | ~0,4 s |
| integração | exclusão soft e restauração | ~0,3 s |
| integração | job apaga após 90 dias | ~0,3 s |
| integração | busca full-text por nome e conteúdo | ~0,4 s |
| integração | busca ignora acento | ~0,2 s |
| integração | duplicar copia tudo com sufixo | ~0,3 s |
| integração | modelo público é somente leitura | ~0,3 s |
| integração | Colaborador não exclui → 403 | ~0,2 s |
| integração | RLS + acesso à biblioteca pública | ~0,4 s |
| frontend | filtro por tipo | ~0,3 s |
| frontend | lixeira e restauração | ~0,4 s |

**Total:** ~3,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Política de RLS com exceção pública testada · Commit `feat(064): modelos — biblioteca`
