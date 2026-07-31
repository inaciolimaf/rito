# 029 — Pastas e organização

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 027 · **Status:** ⬜ pendente

---

## 1. Objetivo

Escritórios organizam processos por pasta física ou por caso. O campo `folder` é texto livre —
esta spec dá a ele autocomplete, agrupamento e navegação.

## 2. Escopo

- Autocomplete de pasta a partir das já usadas no tenant
- Visão agrupada por pasta
- Renomear pasta em lote
- Contador de processos por pasta

## 3. Fora de escopo

- Pastas de documento na nuvem → 063 (conceito diferente)

## 4. Modelo de dados

Nenhuma tabela nova — pasta é atributo, não entidade. Índice para o autocomplete:

```sql
CREATE INDEX ix_lawsuits_folder_trgm ON lawsuits USING gin (folder gin_trgm_ops)
  WHERE folder IS NOT NULL;
```
Migration `029_folder_index.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/lawsuits/folders?q=&limit=20` → `[{name, count}]` |
| POST | `/api/v1/lawsuits/folders/rename` → `{from, to}` |
| GET | `/api/v1/lawsuits?group_by=folder` |

## 6. Front-end

**Reutiliza:** `DataTable`, `EntityPicker`, `ConfirmDialog`
**Cria:** `FolderAutocomplete` (aceita valor novo), `FolderGroupView`
**Rota:** `/lawsuits?group_by=folder`

## 7. Regras de negócio

1. Autocomplete sugere pastas existentes, mas aceita valor novo — não é lista fechada.
2. Comparação de nome é case-insensitive e sem acento; o armazenamento preserva o digitado.
3. Renomear em lote atualiza todos os processos com a pasta antiga, em transação única.
4. Renomear para uma pasta existente **funde** as duas, com confirmação explícita.
5. Pasta continua limitada a 30 caracteres.
6. Visão agrupada ordena por contagem decrescente; processos sem pasta caem em "Sem pasta".
7. Autocomplete devolve no máximo 20 sugestões, ordenadas por frequência de uso.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | autocomplete ordena por frequência | ~0,3 s |
| integração | autocomplete ignora acento | ~0,2 s |
| integração | renomear em lote é transacional | ~0,4 s |
| integração | renomear para existente funde | ~0,3 s |
| integração | agrupamento inclui "Sem pasta" | ~0,3 s |
| integração | RLS: pastas não vazam entre tenants | ~0,3 s |
| frontend | autocomplete aceita valor novo | ~0,4 s |

**Total:** ~2,2 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(029): pastas e organização`
