# 008 — App shell

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 007 · **Status:** ⬜ pendente

---

## 1. Objetivo

A casca navegável do sistema: sidebar com os 15 destinos, header com busca global e menu de
criação rápida. As telas ainda são placeholders, mas a topologia fica congelada — cada spec
seguinte só preenche o seu espaço.

## 2. Escopo

- `AppLayout`: sidebar colapsável + header + área de conteúdo
- Sidebar com os 15 itens, ícone, estado ativo, colapso persistido
- Header: busca global, notificações, dropdown "Adicionar", menu do usuário
- Busca global com facetas **Tudo / Pessoas / Processos**, atalho `/`, navegação por teclado (UI apenas; backend em 096)
- Dropdown "Adicionar": Nova tarefa · Novo contato · Novo processo · Nova receita/despesa
- Breadcrumbs
- Rotas de todos os módulos com placeholder
- Ocultação de item por `capabilities`
- Responsivo: sidebar vira drawer no mobile

## 3. Fora de escopo

- Conteúdo de qualquer módulo → specs das fases 1–9
- Backend da busca → 096
- Notificações reais → 069

## 4. Modelo de dados

Nenhum.

## 5. Contratos de API

Nenhum novo. Consome `capabilities` de `/auth/me`.

## 6. Front-end

**Rotas:** `/home`, `/schedules`, `/posts`, `/crm`, `/customers`, `/lawsuits`,
`/publications`, `/partners`, `/library`, `/transactions`, `/reports`, `/settings`,
`/subscription`

**Componentes criados:** `AppLayout`, `Sidebar`, `Header`, `GlobalSearch`, `QuickAddMenu`,
`Breadcrumbs`, `NotificationBell`

Reutiliza `EmptyState` para os placeholders.

## 7. Regras de negócio

1. Item de menu sem capability é **ocultado**, não desabilitado.
2. Estado de colapso da sidebar persiste por usuário.
3. `/` foca a busca de qualquer lugar, exceto dentro de campo de texto.
4. Busca navega por setas e abre com Enter.
5. Rota desconhecida → 404 dentro do layout, com link de volta.
6. No mobile (<768px) a sidebar vira drawer e fecha ao navegar.
7. Item ativo é derivado da rota, nunca de estado local.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| frontend | sidebar renderiza 15 itens e marca o ativo | `Sidebar.test.tsx` | ~0,4 s |
| frontend | item sem capability é ocultado | idem | ~0,3 s |
| frontend | colapso persiste | idem | ~0,2 s |
| frontend | `/` foca a busca, mas não dentro de input | `GlobalSearch.test.tsx` | ~0,4 s |
| frontend | busca navega por teclado | idem | ~0,3 s |
| frontend | dropdown Adicionar tem as 4 ações | `QuickAddMenu.test.tsx` | ~0,2 s |
| frontend | rota desconhecida → 404 no layout | `AppLayout.test.tsx` | ~0,2 s |
| frontend | drawer no mobile fecha ao navegar | idem | ~0,3 s |
| e2e | **jornada 2/25:** navegar por todos os módulos | `e2e/navigation.spec.ts` | ~4 s |

**Total estimado:** ~6,3 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] 15 rotas navegáveis
- [ ] Ocultação por capability
- [ ] Responsivo verificado
- [ ] Commit `feat(008): app shell`
