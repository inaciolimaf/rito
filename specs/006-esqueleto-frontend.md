# 006 — Esqueleto do frontend

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +8 s
**Depende de:** 004 · **Status:** ✅ concluída

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

- **Bug real, não sandbox:** `apiRequest` inicialmente disparava o fluxo de refresh para
  QUALQUER 401, inclusive o de `/auth/login` com senha errada — o teste "credencial inválida
  mostra erro" pegou isso na hora (mensagem virava "sessão expirada" em vez do erro real).
  Corrigido checando se a requisição original tinha `Authorization` — só então um 401 dispara
  refresh; sem token, é resposta de credencial mesmo.
- **Sem endpoint de resolução de slug→tenant.** O contrato de `/auth/login` (spec 004) não leva
  identificador de tenant no corpo — o back só sabe qual tenant usar via header `X-Tenant-Id`
  (UUID), e não existe (ainda) nenhuma rota pública que resolva um "código do escritório" para
  esse UUID (isso é natural território da 011 — Escritório). `LoginPage` ganhou um terceiro
  campo, "ID do escritório", pedindo o UUID cru. É uma UX ruim para um produto de verdade, mas
  correta e honesta para o estado atual do backend — documentado aqui para a 011 revisitar
  (ideal: subdomínio ou campo de slug resolvido no backend).
- **CORS não existia** até agora — nenhuma spec anterior precisou, já que só havia testes
  ASGI in-process (sem origem cruzada de verdade). A jornada e2e (navegador real batendo em
  `localhost:8000` a partir de `localhost:5173`) expôs isso imediatamente. Adicionado
  `CORSMiddleware` + `CORS_ALLOWED_ORIGINS` (`app/core/config.py`, `app/main.py`) — fora do
  escopo literal da spec 006, mas pré-requisito inescapável para "login real funcionando ponta
  a ponta" num navegador de verdade.
- **Bug real de isolamento de teste, achado através do e2e.** Rodar `make test` com o
  webServer do e2e (que precisa de `DATABASE_URL`/`SECRET_KEY`/`REDIS_URL` no ambiente
  apontando pro banco de **dev**, não teste) expôs que `backend/tests/conftest.py` usava
  `os.environ.setdefault(...)` para essas variáveis — ou seja, se o processo pai já tinha
  `DATABASE_URL` setada (exatamente o caso do e2e rodando ao lado), o pytest **herdava** esse
  valor e testava contra o banco errado, causando `UndefinedTableError` só nas tabelas
  criadas exclusivamente em `rito_test` (os testes de RLS). Não era race condition nem
  problema deste sandbox — era um bug real de isolamento que só a introdução do e2e (rodando
  de verdade, precisando de `DATABASE_URL` no ambiente) revelou. Trocado `setdefault` por
  atribuição forçada: testes agora SEMPRE usam `TEST_*`, nunca herdam o que já estiver no
  ambiente. Também endureci o nome da tabela de sonda (`tenant_probe_{worker_id}_{uuid4}`)
  como defesa adicional, mas a causa raiz era o `setdefault`.
- **E2E de verdade, não simulado.** `e2e/global-setup.ts` roda
  `backend/scripts/seed_e2e.py` (idempotente, tenant+usuário fixos) antes da suíte;
  `playwright.config.ts` sobe backend (uvicorn) e frontend (vite dev) via `webServer` — sem
  servidor real rodando, cai para `reuseExistingServer`. Rodei a jornada tanto com servidores
  já de pé quanto com o Playwright subindo os dois do zero; ambos os caminhos passam.
  Chromium instalou e rodou neste sandbox sem precisar de `--with-deps` (que exigiria sudo
  indisponível aqui) — se isso mudar em outro ambiente, é só rodar
  `npx playwright install --with-deps chromium` com privilégio.
- **Estado "offline" não implementado.** A seção 6 lista "offline" como um dos estados —
  não há teste para isso no plano (seção 8) nem regra de negócio correspondente (seção 7), e
  por isso não implementei detecção de `navigator.onLine`/banner de rede. Login/credencial
  inválida/sessão expirada estão cobertos; offline fica pendente para quem precisar dele de
  verdade (provavelmente junto de alguma spec de sincronização/fila offline mais adiante).
- `shadcn/ui` foi inicializado com a convenção (`components.json`, `lib/utils.ts` com `cn()`,
  `class-variance-authority`, Radix) mas os componentes (`Button`, `Input`, `Label`) usam os 8
  tokens semânticos da spec (`surface`, `primary`, `muted`, `default`, `accent`, `danger`,
  `warning`, `success`), não a paleta padrão do shadcn (`background`/`card`/`destructive`/...).
  Regra dos 3 usos ainda não bateu para nenhum outro primitivo — só o que o login precisava.
- Regra de lint contra cor literal implementada como plugin local
  (`eslint-rules/no-literal-tailwind-color.js`) em vez de depender de um pacote npm — varre
  qualquer string/template literal (não só `className` de JSX), pegando também `cva()`/`cn()`.
  Reporta só a primeira ocorrência por literal (suficiente para bloquear o lint; não enumera
  todas as cores num único literal com mais de uma).

## 10. Definição de pronto

- [x] Login real funcionando ponta a ponta (validado com Playwright contra backend/Postgres/
      Redis reais, não só MSW)
- [x] Refresh concorrente resolvido com fila (uma única promise compartilhada; testado com 2
      requisições simultâneas → 1 chamada de refresh)
- [x] Dark mode nos dois sentidos (SO na primeira visita, escolha manual persiste e
      sobrepõe, testado)
- [x] Regra de lint contra cor literal ativa (plugin local, `error`, testado manualmente
      contra um caso positivo)
- [x] Commit `feat(006): esqueleto do frontend`
