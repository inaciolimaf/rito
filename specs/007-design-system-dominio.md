# 007 — Design system de domínio

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +12 s
**Depende de:** 006 · **Status:** ✅ concluída

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

- **Bug real de reatividade do react-hook-form, achado pelo teste de dirty guard.**
  `FormModal.requestClose()` lia `form.formState.isDirty` dentro do próprio event handler e
  sempre via `false`, mesmo depois de digitar no campo (confirmado via um teste descartável:
  o MESMO `form.formState.isDirty`, lido durante o *render* do `children(form)`, retornava
  `true`; lido dentro do handler do botão Cancelar, `false`). RHF só mantém `formState`
  reativo para os campos efetivamente lidos durante o render do componente que chamou
  `useForm` — ler só dentro de uma closure de evento não "assina" a atualização. Corrigido
  desestruturando `const { isDirty } = form.formState` no corpo de `FormModal` (fora de
  qualquer handler) e usando essa variável local em `requestClose`. Vale para qualquer futuro
  componente que leia `formState.*` fora do render.
- **Sem `@tanstack/react-table` ou combobox de terceiros.** `DataTable` usa `<table>` nativo
  (sort/seleção via `<button>`/`<input type="checkbox">`, navegação por teclado de graça) e
  `EntityPicker` implementa um combobox mínimo à mão (`role="combobox"`/`role="listbox"`,
  `aria-activedescendant` via índice ativo, Arrow/Enter/Escape) em vez de puxar uma lib de
  combobox — mantém o design system sem dependência extra para o que só precisava de HTML
  semântico bem feito.
- **Multiselect do `FilterBar` usa `<select multiple>` nativo**, não um dropdown de checkboxes
  customizado — acessível de graça (teclado, leitor de tela) e evita mais uma dependência
  Radix só para isso. Puro texto/select/date usam `<Input type="date">`/`<select>` também
  nativos pela mesma razão.
- **`components.json`/tokens do shadcn continuam os 8 semânticos da spec 006** (`surface`,
  `primary`, `muted`, `default`, `accent`, `danger`, `warning`, `success`) — `Dialog` e
  `Checkbox` (novos nesta spec) seguem a mesma convenção, sem introduzir `background`/`card`/
  `destructive` do shadcn padrão.
- **Kitchen sink é gated por `import.meta.env.DEV`** — a rota `/kitchen-sink` não entra no
  bundle de produção (Vite faz tree-shaking do branch morto no build). Testado manualmente
  num navegador real (Playwright ad hoc, não commitado): claro/escuro, abrir `FormModal`,
  buscar e selecionar no `EntityPicker` — sem erros de console, screenshots conferidas.
- **`FormModal`/`ConfirmDialog` são genéricos sobre `z.ZodType<any, any, any>`** com
  `eslint-disable` pontual para `no-explicit-any` — é o preço de expor um componente
  genuinamente genérico por schema Zod (`z.infer<TSchema>` não function sem esse bound). Não é
  um `any` "de preguiça": é a única forma de o TypeScript aceitar qualquer schema Zod como
  parâmetro de tipo.
- Nenhum `KanbanBoard`/`AIActionPreview` foi tocado — confirma o "fora de escopo" (051, 084).

## 10. Definição de pronto

- [x] Sete componentes com testes (`DataTable`, `FilterBar`, `FormModal`, `EntityPicker`,
      `StatCard`, `EmptyState`, `ConfirmDialog` — `EmptyState` coberto indiretamente via os
      testes de estado vazio/erro do `DataTable`, que o usa internamente)
- [x] Kitchen sink exercitando todos (`/kitchen-sink`, dev-only, verificado num navegador real)
- [x] Contrato de listagem keyset documentado no `CLAUDE.md` (§6, nova subseção)
- [x] Navegação por teclado verificada (`a11y.test.tsx` + checagem manual no navegador)
- [x] Commit `feat(007): design system de domínio`
