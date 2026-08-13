# 064 — Modelos: biblioteca

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 063 · **Status:** ✅ concluída

---

## 1. Objetivo

Antes de ter editor (spec 065) ou variável (spec 066), o escritório precisa de onde
guardar e organizar os modelos de documento: cadastro, os 4 tipos do levantamento,
busca e uma lixeira reversível.

## 2. Escopo

- CRUD de modelos (nome, tipo, conteúdo em texto simples — o editor rico é a spec 065,
  o campo já existe para não exigir migration nova quando ele chegar).
- 4 tipos: Contrato, Petição, Recurso, Documento.
- Busca por nome.
- Filtro por tipo (Todos/Contrato/Petição/Recurso/Documento) e visão "Somente os
  excluídos".
- Exclusão vai para a lixeira (reversível); restauração devolve à listagem normal.
- Fazer cópia de um modelo existente (ação do levantamento ADVBOX §4.9).

## 3. Fora de escopo

- Editor rico (TipTap, cabeçalho/rodapé/marca d'água) — spec 065.
- Variáveis de preenchimento automático — spec 066.
- Geração de PDF/envio — spec 067.
- Biblioteca pública (aba separada, modelos de terceiros) — spec 068.
- Exclusão definitiva da lixeira (purge) — não há requisito do levantamento para isso;
  a lixeira é só reversível.

## 4. Modelo de dados

```sql
CREATE TABLE templates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  type TEXT NOT NULL,              -- 'CONTRATO' | 'PETICAO' | 'RECURSO' | 'DOCUMENTO'
  content TEXT NOT NULL DEFAULT '',
  created_by UUID NOT NULL REFERENCES users(id),
  deleted_at TIMESTAMPTZ,           -- NULL = ativo; preenchido = na lixeira (regra 3)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_templates_tenant_type ON templates (tenant_id, type) WHERE deleted_at IS NULL;
```
RLS. Migration `064_templates.py`.

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/templates?view=&q=&cursor=&limit=` | query | `200 {items[], next_cursor, total}` | autenticado |
| POST | `/api/v1/templates` | `{name,type,content?}` | `201 template` | autenticado |
| GET | `/api/v1/templates/{id}` | — | `200 template` | autenticado |
| PUT | `/api/v1/templates/{id}` | `{name,type,content}` | `200 template` | autenticado |
| DELETE | `/api/v1/templates/{id}` | — | `204` (lixeira) | autenticado |
| POST | `/api/v1/templates/{id}/restore` | — | `200 template` | autenticado |
| POST | `/api/v1/templates/{id}/duplicate` | — | `201 template` | autenticado |

`view` ∈ `all` (default) · `CONTRATO` · `PETICAO` · `RECURSO` · `DOCUMENTO` · `trash`.
Erros: `404` (modelo inexistente/de outro tenant).

## 6. Front-end

**Componentes reutilizados:** `DataTable`, `FilterBar`, `FormModal`, `ConfirmDialog`,
`useCrudResource`, `useFilters`
**Componentes criados:** nenhum — a tela é o 4º uso do mesmo esqueleto de
`CustomerOriginsListPage`/`FinancialCategoriesListPage`/`CostCentersListPage` (regra
dos 3 usos já satisfeita antes desta spec, nada novo para extrair).
**Rota:** `/library` (item "Modelos" do menu, spec 008)
**Estados:** loading, vazio, erro, lixeira vazia

## 7. Regras de negócio

1. `type` é um dos 4 valores fixos do levantamento — outro valor é `422`.
2. Nome é obrigatório; duplicidade de nome é permitida (o levantamento não veta).
3. Excluir marca `deleted_at = now()` — nunca apaga a linha (regra: reversível).
4. Modelo na lixeira não aparece nas visões normais (`all`/por tipo); só na visão
   `trash`.
5. Restaurar limpa `deleted_at` — volta a aparecer nas visões normais, some da lixeira.
6. Fazer cópia cria um novo modelo com `name` sufixado `" (cópia)"`, mesmo `type` e
   `content`, nunca na lixeira mesmo que o original esteja.
7. Busca por nome é case-insensitive, contains, dentro da visão ativa (não cruza
   lixeira com listagem normal).
8. Restaurar ou copiar um modelo de outro tenant (ou inexistente) é `404` — RLS já
   impede o acesso à linha; a rota só formata o erro.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | CRUD completo (criar, ler, atualizar) | `tests/integration/test_templates.py` | ~0,3 s |
| integração | tipo inválido → 422 | idem | ~0,2 s |
| integração | excluir move pra lixeira; some da listagem normal | idem | ~0,3 s |
| integração | lixeira lista só os excluídos | idem | ~0,3 s |
| integração | restaurar devolve à listagem normal | idem | ~0,3 s |
| integração | duplicar copia nome/tipo/conteúdo com sufixo | idem | ~0,3 s |
| integração | duplicar um modelo da lixeira gera cópia ativa | idem | ~0,2 s |
| integração | busca por nome é case-insensitive | idem | ~0,2 s |
| integração | filtro por tipo combina com AND com a busca | idem | ~0,2 s |
| RLS | tenant A não vê/restaura/duplica modelo de tenant B | idem | ~0,3 s |
| frontend | filtra por tipo, exclui e restaura da lixeira | `src/features/templates/*.test.tsx` | ~0,3 s |

**Total estimado:** ~3,1 s
**Fixtures externas:** nenhuma.

## 9. Descobertas

- Nenhuma dependência técnica real de 063 apareceu — a biblioteca não usa
  `FileStorage`/quota (o `content` é texto simples guardado direto na coluna). A
  dependência declarada no ROADMAP é de ordem de fase; o editor (spec 065) e a geração
  de PDF (spec 067) é que devem usar a nuvem de documentos.
- `paginate_keyset`/`encode_cursor`/`decode_cursor` (spec 030) cobriram a listagem sem
  nenhum código novo de paginação — mesmo padrão de contatos (019).

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Teste de isolamento por tenant
- [x] `make test` verde e wall-clock < 300 s (259 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(064): modelos — biblioteca`
