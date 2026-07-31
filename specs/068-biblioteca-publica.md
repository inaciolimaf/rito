# 068 — Biblioteca pública de modelos

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 064 · **Status:** ⬜ pendente

---

## 1. Objetivo

Escritório novo começa com o editor vazio e não escreve nada. A biblioteca pública entrega
modelos prontos que ele copia e adapta.

## 2. Escopo

- Modelos de sistema (`tenant_id IS NULL`)
- Aba "Biblioteca Pública"
- Visualizar antes de copiar
- Copiar para o escritório
- Busca e filtro por tipo
- Seed inicial de modelos

## 3. Fora de escopo

- Marketplace ou compartilhamento entre tenants (fora do escopo)

## 4. Modelo de dados

Nenhuma tabela nova — usa `document_templates` com `tenant_id IS NULL`. Colunas de apoio:

```sql
ALTER TABLE document_templates
  ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN public_description TEXT,
  ADD COLUMN copied_from_id UUID REFERENCES document_templates(id),
  ADD COLUMN copy_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX ix_templates_public ON document_templates (kind)
  WHERE is_public AND deleted_at IS NULL;
```
Migration `068_public_library.py` + seed de modelos.

**Política de RLS** revisada: `SELECT` permite `tenant_id = current_tenant OR is_public`;
`INSERT`, `UPDATE` e `DELETE` só `tenant_id = current_tenant`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/templates/public?kind=&q=&cursor=` |
| GET | `/api/v1/templates/public/{id}` — visualização |
| POST | `/api/v1/templates/public/{id}/copy` → cria no tenant |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `EmptyState`, `ConfirmDialog`
**Cria:** `PublicLibraryTab`, `PublicTemplateCard` (com badge NOVO e contador de cópias),
`TemplatePreviewDialog`
**Rota:** `/library?tab=public`

## 7. Regras de negócio

1. Modelo público é **somente leitura**: tentar editar ou excluir → 403.
2. Copiar cria registro novo no tenant, com `copied_from_id` preenchido e `is_public = false`.
3. A cópia é independente: alterar o público depois não afeta quem já copiou.
4. `copy_count` incrementa a cada cópia — alimenta a ordenação por popularidade.
5. Visualização mostra o conteúdo renderizado com as variáveis como chips, sem resolver dados.
6. Busca full-text no acervo público, igual à do privado.
7. Ordenação padrão: mais copiados primeiro.
8. Badge NOVO em modelos publicados nos últimos 30 dias.
9. Seed inicial: pelo menos um modelo de cada tipo (contrato de honorários, petição inicial genérica, recurso de apelação, procuração).
10. Só administrador da plataforma cria modelo público — não há UI para isso, só migration.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | listar públicos sem estar em nenhum tenant específico | ~0,3 s |
| integração | editar público → 403 | ~0,2 s |
| integração | excluir público → 403 | ~0,2 s |
| integração | copiar cria no tenant com `copied_from_id` | ~0,4 s |
| integração | alterar o público não afeta a cópia | ~0,4 s |
| integração | `copy_count` incrementa | ~0,2 s |
| integração | **RLS: público visível a todos, privado só ao dono** | ~0,5 s |
| integração | busca no acervo público | ~0,3 s |
| frontend | preview sem resolver variáveis | ~0,4 s |
| frontend | badge NOVO em recentes | ~0,2 s |

**Total:** ~3,1 s

> A política de RLS com exceção é o ponto delicado: um erro aqui vaza modelo entre tenants.
> O teste marcado é o mais importante da spec.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · RLS com exceção pública testada nos dois sentidos · Commit `feat(068): biblioteca pública de modelos`
