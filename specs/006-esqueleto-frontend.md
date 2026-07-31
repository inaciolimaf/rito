# 006 — Esqueleto do frontend

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +8 s
**Depende de:** 004 · **Status:** ⬜ pendente

---

## 1. Objetivo

Aplicação React que autentica de verdade contra o backend, mantém a sessão viva com refresh
automático e já nasce com tema claro/escuro e os tokens do design system.

## 2. Escopo

- Vite + React 18 + TypeScript strict
- Tailwind com design tokens (cores semânticas, espaçamento, raio, tipografia)
- shadcn/ui inicializado (`components/ui/` — não editar à mão)
- **Dark mode** com `class` strategy, alternância e persistência em `localStorage` + preferência do SO
- TanStack Query com `QueryClient` configurado (retry, staleTime, error boundary)
- React Router com rotas públicas e protegidas
- Client de API (`lib/api.ts`): baseURL, injeção de bearer, **refresh automático em 401 com fila de requisições pendentes**, tradução de problem+json para erro tipado
- `AuthProvider` com contexto de usuário e `capabilities`
- Tela de login funcional
- Setup do Vitest + Testing Library + MSW

## 3. Fora de escopo

- Componentes de domínio (`DataTable` etc.) → 007
- Shell com sidebar → 008

## 4. Modelo de dados

Nenhum.

## 5. Contratos de API

Consome `/auth/login`, `/auth/refresh`, `/auth/me` da spec 004.

## 6. Front-end

**Componentes criados:** `AuthProvider`, `ProtectedRoute`, `ThemeProvider`, `ThemeToggle`, `LoginPage`
**Rotas:** `/login` (pública), `/` (protegida, placeholder)
**Estados:** loading, credencial inválida, sessão expirada, offline

Tokens semânticos — nunca cor crua no componente:
`bg-surface`, `bg-surface-muted`, `text-primary`, `text-muted`, `border-default`,
`accent`, `danger`, `warning`, `success`. Todos definidos para os dois temas.

## 7. Regras de negócio

1. 401 dispara refresh **uma vez**; requisições concorrentes esperam na fila e são reexecutadas.
2. Refresh falhou → limpa sessão e redireciona para `/login` preservando o destino.
3. Rota protegida sem sessão → `/login?next=<rota>`.
4. Tema segue o SO na primeira visita; escolha manual passa a mandar.
5. Token em memória + refresh em `localStorage`. Nenhum dado sensível além disso.
6. Erro `problem+json` vira `ApiError` tipado com `status`, `title`, `detail`, `errors`.
7. Nenhum componente usa cor literal (`bg-blue-500`); só token semântico. **Lint bloqueia.**

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| frontend | login com sucesso redireciona | `LoginPage.test.tsx` | ~0,4 s |
| frontend | credencial inválida mostra erro | idem | ~0,3 s |
| frontend | 401 dispara refresh e reexecuta | `lib/api.test.ts` | ~0,5 s |
| frontend | refresh falho limpa sessão | idem | ~0,3 s |
| frontend | requisições concorrentes fazem 1 refresh só | idem | ~0,4 s |
| frontend | rota protegida redireciona com `next` | `ProtectedRoute.test.tsx` | ~0,3 s |
| frontend | tema alterna e persiste | `ThemeToggle.test.tsx` | ~0,3 s |
| frontend | problem+json vira `ApiError` | `lib/errors.test.ts` | ~0,2 s |
| e2e | **jornada 1/25:** login → home → logout | `e2e/auth.spec.ts` | ~3 s |

**Total estimado:** ~5,7 s
Backend mockado com MSW nos testes de frontend. E2E roda contra o backend real.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] Login real funcionando ponta a ponta
- [ ] Refresh concorrente resolvido com fila
- [ ] Dark mode nos dois sentidos
- [ ] Regra de lint contra cor literal ativa
- [ ] Commit `feat(006): esqueleto do frontend`
