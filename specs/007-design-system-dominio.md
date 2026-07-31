# 007 — Design system de domínio

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +12 s
**Depende de:** 006 · **Status:** ⬜ pendente

---

## 1. Objetivo

A spec de maior alavancagem do projeto. São ~40 telas de listagem com filtro, tabela, modal de
formulário e export. Se cada uma for escrita à mão, o projeto não termina. Aqui construímos os
primitivos que fazem a 40ª tela custar quase nada.

## 2. Escopo

Sete componentes em `components/domain/`, todos dirigidos por schema:

| Componente | Responsabilidade |
|---|---|
| `DataTable<T>` | colunas tipadas, ordenação server-side, **paginação keyset**, seleção múltipla, ações de linha e em massa, export xlsx/pdf, estados de loading/vazio/erro, responsivo |
| `FilterBar` | filtros declarativos (texto, select, multiselect, data, intervalo, booleano), sincronizados com a query string, "limpar filtros", contador de ativos |
| `FormModal<T>` | formulário a partir de schema Zod, React Hook Form, layout em grid, validação, erro de servidor por campo, dirty guard |
| `EntityPicker` | busca assíncrona debounced de cliente / processo / usuário, seleção simples ou múltipla, criação inline opcional |
| `StatCard` | valor, rótulo, variação vs período anterior, tendência, link de detalhe, skeleton |
| `EmptyState` | ícone, título, descrição, ação primária |
| `ConfirmDialog` | confirmação destrutiva, com digitação de confirmação opcional |

Mais: `useDataTable`, `useFilters` (URL como fonte de verdade) e uma página `/kitchen-sink`
em dev exercitando todos.

## 3. Fora de escopo

- `KanbanBoard` → 051 (só existe um consumidor até lá; regra dos 3 usos)
- `AIActionPreview` → 084

## 4. Modelo de dados

Nenhum. Endpoints falsos servem a página de demonstração.

## 5. Contratos de API

Define o **contrato de listagem** que todas as specs seguintes seguem:

```
GET /api/v1/<recurso>?cursor=&limit=&sort=&order=&<filtros>
200 { "items": [...], "next_cursor": "...|null", "total": 123 }
```

Keyset, não offset: `cursor` codifica `(sort_value, id)` em base64.

## 6. Front-end

Cada componente entrega: implementação, tipos exportados, testes e entrada no kitchen sink.
Acessibilidade não é opcional — navegação por teclado, `aria-*` e foco visível em todos.

## 7. Regras de negócio

1. `DataTable` **nunca** faz fetch sozinho. Recebe dados e callbacks. Quem busca é a feature.
2. Filtros vivem na URL — recarregar a página preserva o estado; o link é compartilhável.
3. `FormModal` bloqueia fechamento com alterações não salvas (dirty guard).
4. Erro de validação do servidor (422) mapeia para o campo correspondente.
5. Paginação é **sempre keyset**. Offset é proibido — quebra em volume.
6. Export respeita os filtros ativos, não a página visível.
7. Todo componente tem estado vazio e de erro explícitos. "Nada acontece" não é estado.
8. Tudo navegável por teclado.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| frontend | `DataTable` renderiza, ordena, seleciona | `DataTable.test.tsx` | ~0,8 s |
| frontend | `DataTable` pagina por cursor | idem | ~0,4 s |
| frontend | `DataTable` mostra vazio e erro | idem | ~0,3 s |
| frontend | `FilterBar` reflete na URL e volta | `FilterBar.test.tsx` | ~0,5 s |
| frontend | `FilterBar` limpa e conta ativos | idem | ~0,3 s |
| frontend | `FormModal` valida por Zod | `FormModal.test.tsx` | ~0,5 s |
| frontend | `FormModal` mapeia erro 422 no campo | idem | ~0,4 s |
| frontend | `FormModal` dirty guard | idem | ~0,3 s |
| frontend | `EntityPicker` debounce e seleção | `EntityPicker.test.tsx` | ~0,5 s |
| frontend | `StatCard` variação e skeleton | `StatCard.test.tsx` | ~0,2 s |
| frontend | `ConfirmDialog` exige confirmação | `ConfirmDialog.test.tsx` | ~0,2 s |
| frontend | teclado atravessa `DataTable` e `FormModal` | `a11y.test.tsx` | ~0,6 s |

**Total estimado:** ~5,0 s
Sem e2e — componente puro se testa com Vitest, mais barato e mais estável.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] Sete componentes com testes
- [ ] Kitchen sink exercitando todos
- [ ] Contrato de listagem keyset documentado no `CLAUDE.md`
- [ ] Navegação por teclado verificada
- [ ] Commit `feat(007): design system de domínio`
