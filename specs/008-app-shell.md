# 008 — App shell

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 007 · **Status:** ✅ concluída

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

- **Dois bugs reais e sérios no fluxo de autenticação, só descobertos porque esta spec
  finalmente exercitou reload de página + navegação real contra o backend de verdade** (as
  specs 006/007 só tinham 1 jornada e2e simples e testes de componente com MSW, que mascaravam
  os dois problemas abaixo):
  1. **`/auth/refresh` e `/auth/logout` sempre precisaram de `X-Tenant-Id`** (spec 004: todo
     endpoint pré-autenticação resolve o tenant pelo header, nunca pelo corpo) — mas
     `lib/api.ts`/`AuthProvider` nunca mandavam esse header nessas duas chamadas. Login
     funcionava (manda o header), mas QUALQUER reload de página (silent re-auth via refresh
     token) e todo logout falhavam com `400 Cabeçalho X-Tenant-Id é obrigatório` — silenciosos
     porque `logout()` engole erros (`.catch(() => undefined)`) e o teste e2e da 006 nunca
     dava reload de página. Corrigido persistindo `tenantId` em `localStorage` ao lado do
     refresh token (`setSession`/`getStoredTenantId`) e mandando o header nas duas chamadas.
     Os mocks MSW foram endurecidos para exigir o header também (antes não validavam nada),
     senão o mesmo bug voltaria a passar batido em teste de componente.
  2. **Minha própria correção da spec 006** (não disparar refresh num 401 de `/auth/login`
     sem token) usava a condição errada — checava "a requisição mandou Bearer token?" em vez
     de "qual endpoint é esse?". Isso quebrava o caso NORMAL de reautenticação silenciosa: a
     primeira chamada de `/auth/me` depois de um reload não tem access token (ele só vive em
     memória) por design — é exatamente quando o refresh deveria disparar. Troquei para uma
     lista de paths pré-autenticação (`/auth/login`, `/auth/refresh`, `/auth/forgot-password`,
     `/auth/reset-password`) que nunca tentam refresh; todo o resto tenta, com ou sem token.
  - Achados com um script Playwright ad hoc (login → navegação client-side → reload de página
    numa rota qualquer) enquanto investigava por que a jornada 2/25 falhava — não helper de
    debug commitado, só usado para isolar a causa raiz antes de escrever o fix de verdade.
- **Mapeamento ADVBOX → rotas do Rito** pesquisado em
  `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md`: os 15 itens do menu lateral do ADVBOX são 13
  navegáveis + 2 que abrem modal (Suporte, Indicar a ADVBOX/Rito — sem rota própria). Mantive
  os 13 caminhos já definidos na seção 6 desta spec; os 2 modais viram um `Dialog` genérico
  ("Em breve.") a partir do clique no item, sem nenhuma feature nova.
- **Gate por capability aplicado só a 3 dos 15 itens**: Financeiro (`financial.read`),
  Configurações e Conta e assinatura (`settings.manage`) — os únicos que já existem na matriz
  da spec 005. Os outros 12 ficam visíveis para qualquer usuário autenticado; a spec não pediu
  (nem a 005 fornece) uma capability por módulo, e inventar uma seria escopo da spec de cada
  módulo real.
- **Sem rota protegida por capability** — só o ITEM do menu é ocultado (regra 1, literal:
  "ocultado, não desabilitado"). Acessar `/transactions` direto por URL sem `financial.read`
  ainda renderiza o placeholder; controle de acesso ao CONTEÚDO real é escopo de cada módulo
  (fases 1–9), não desta spec.
- Nenhum dropdown/combobox de terceiros novo — `QuickAddMenu`/`NotificationBell`/`UserMenu`
  reusam o mesmo padrão de "lista posicionada + fechar ao clicar fora" que `EntityPicker` já
  tinha (spec 007), evitando mais uma dependência Radix para um menu simples.
- `UserMenu` não está na lista de "Componentes criados" da spec (só tem os 7 nomeados) —
  ficou como subcomponente não-exportado dentro de `Header.tsx` para não inventar um 8º nome;
  o requisito "menu do usuário" do escopo do Header está atendido mesmo assim.

## 10. Definição de pronto

- [x] 15 itens navegáveis na sidebar (13 rotas reais + 2 modais, mapeados do ADVBOX)
- [x] Ocultação por capability (Financeiro/Configurações/Conta e assinatura; testado que
      some, não que desabilita)
- [x] Responsivo verificado (drawer mobile testado em Vitest + conferido visualmente em
      viewport 390×844 num navegador real)
- [x] Commit `feat(008): app shell`
