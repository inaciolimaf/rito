# Auditoria do padrão de front: identidade, tokens e CSS

Auditoria do `frontend/` contra as referências `identity`, `tokens-and-css`, `motion` e `process` do
padrão `frontend-standard`. Identidade do produto em `docs/frontend-identity.md`.

Legenda de status: **ok** (atende), **parcial** (atende em parte, com a ação registrada),
**falta** (não atende), **n/a** (não se aplica agora).

## Stack e versão

| Regra | Status | Ação | Débito |
|---|---|---|---|
| Tailwind v4 (`@theme inline`, `@custom-variant`) | falta | nenhuma: o projeto usa Tailwind **3.4.17** (`frontend/package.json`) | migração para v4 é débito grande, fora deste escopo |
| `darkMode: "class"` segue o app, não o sistema | ok | nenhuma: `ThemeProvider` põe `.dark` em `<html>` | o equivalente v4 (`@custom-variant`) entra com a migração |

## Identidade

| Regra | Status | Ação | Débito |
|---|---|---|---|
| Spec de identidade com conceito, esqueleto, significados, proibições | falta | criado `docs/frontend-identity.md` preenchido a partir do template, marcando o que é proposta | conceito e tipografias dependem de decisão da pessoa dona no app rodando |
| O conceito muda o layout das telas | falta | nenhuma: sem conceito aprovado, não há o que mudar | piloto na tela de Processos |
| Uma raiz única por tela, com teste | falta | nenhuma: a casca `AppLayout` é a de painel administrativo genérico | depende do conceito |
| Uma ação principal sólida por tela | parcial | nenhuma: `Button` `default` é sólido em `accent`; não há teste de orçamento | verificar no piloto |
| Cor nunca carrega sentido sozinha | parcial | nenhuma: `FieldConfidenceBadge` usa texto; não auditado a fundo | auditoria tela a tela, junto com acessibilidade |
| Aviso no item a que se refere | n/a | nenhuma | depende das telas do piloto |

## Cor e tokens

| Regra | Status | Ação | Débito |
|---|---|---|---|
| Cor só por token, com valor em cada tema | ok | nenhuma: `index.css` define todos os tokens em `:root` e `.dark` | |
| Lint bloqueia cor literal do Tailwind | ok | nenhuma: `rito/no-literal-tailwind-color` | |
| Lint bloqueia hexadecimal ou `hsl()` fora de tokens | falta | nenhuma no lint (fora da minha fatia) | regra de lint; é da frente de lint |
| Cores de gráfico fora de componente, em tokens | parcial, corrigido | `CycleBarChart`, `CostPerStageChart` e `DonutChart` passaram a usar `--chart-*`; teste atualizado | os valores de `--chart-*` são iguais nas duas temas (ver contraste abaixo) |
| Cor de texto do editor de modelos (escolha do usuário) | n/a | mantida fora dos tokens: é conteúdo do documento | exceção declarada, sem lint |
| Iframe de documento com cores próprias (`SandboxedHtml`) | n/a | mantido: CSS de conteúdo renderizado, isolado do app | exceção declarada |
| Texto sobre `bg-primary` com `on-*` | falta, corrigido | `text-on-primary` era usado em 8 lugares e **não estava definido** no Tailwind, então o texto herdava a cor escura (ilegível no claro). Definido `on-primary` em `tailwind.config.ts` | |
| Véu de diálogo e gaveta sem cor de texto | parcial, corrigido | `AppLayout` (gaveta mobile) usa `bg-overlay/50`, token novo, preto nos dois temas. `components/ui/dialog.tsx` ainda usa `bg-primary/50` | `ui/dialog.tsx` é shadcn, não se edita à mão; o véu fica claro no tema escuro até regenerar ou sobrescrever |
| Tons de fundo com cor de texto (`bg-muted/20`) | parcial | nenhuma: 4 ocorrências intencionais de tinta esmaecida | aceitas; se crescer, virar token |
| Contraste de pares de texto nos dois temas, em teste | ok, corrigido | tokens ajustados só em luminosidade (matiz e saturação mantidos): `muted`, `danger`, `success`, `warning` e `warning-foreground` no claro; `accent` e `danger` no escuro; `danger-foreground` no escuro passou a texto escuro. Teste `src/index.contrast.test.ts` com lista de exceções vazia | `warning` no claro ficou em 33% de luminosidade, o mínimo que passa com texto preto sobre ele; a cor é um ocre escuro |
| Cada tema desenhado à parte, sem inversão | parcial | nenhuma: os valores do escuro foram escolhidos à mão, mas o tema é só "superfície escura" | desenho do escuro entra com a identidade |
| `text-white` sobre cor | ok | nenhuma: zero ocorrências | |
| Tokens de tipografia; sem `text-[NNpx]` | ok, corrigido | 12 ocorrências de `text-[10px]`/`text-[11px]` viraram `text-micro`/`text-caption` (tokens em `tailwind.config.ts`), tamanho idêntico | |
| Escala de cerca de cinco tamanhos | falta | nenhuma: a escala padrão tem nove, e o corpo é `text-sm` (548 usos) | reduzir a escala é decisão de identidade |
| Números comparados com `tabular-nums` | falta | nenhuma: zero ocorrências | aplicar em Financeiro e Relatórios no piloto |
| Hierarquia de Inter ou fontes proibidas | ok | nenhuma: sem fonte customizada, sem Inter | a escolha de fonte é da pessoa dona |
| Backgrounds do shell por token | ok | nenhuma | |

## CSS (armadilhas)

| Regra | Status | Ação | Débito |
|---|---|---|---|
| `100dvh`, nunca `100vh` | ok, corrigido | `h-screen` → `h-dvh` em `AppLayout`; `min-h-screen` → `min-h-dvh` em `LoginPage`, `AcceptInvitePage` e `ErrorBoundary` | |
| Trilhas de grid com `minmax(0, 1fr)` | ok, corrigido | `PipelinePanel` tinha `lg:grid-cols-[1fr_auto]`; virou `minmax(0,1fr)` | |
| Override fora de `@layer components` | n/a | nenhum override de CSS sem camada encontrado | |
| Folha de CSS por área (`src/styles/<area>.css`) | falta | nenhuma: `index.css` único, com tokens e base | se o CSS crescer, separar |
| Container queries para partes em colunas variáveis | falta | nenhuma: não há caso que hoje precise | |
| `overflow-x: clip` em camada deslizante | n/a | nenhuma camada deslizante | |
| `vector-effect` em traço animado | n/a | nenhum traço animado | |

## Movimento

| Regra | Status | Ação | Débito |
|---|---|---|---|
| Durações e curvas como tokens, espelhadas em TS | falta | nenhuma: a app usa as durações padrão do Tailwind e nenhum `--motion-*` | criar tokens quando houver motion próprio |
| Só `transform`, `opacity` e traço animam; teste faz parse de `@keyframes` | parcial | nenhuma: `transition-colors` e `transition-[width]` animam cor e largura; zero `@keyframes` próprios | a regra de propriedade é cumprida na prática, sem teste |
| `prefers-reduced-motion` dá troca imediata | ok, adicionado | bloco em `index.css`: zera transições e para `animate-pulse`. Teste garante que o bloco existe (`src/lib/tokens.test.ts`) | o giro do `Loader2` continua, de propósito (carregamento em curso) |
| Motion de timers JavaScript com reduced-motion | falta | nenhuma: não auditado | a verificar no piloto |
| Loops só em carregamento | ok | nenhuma: `animate-spin` e `animate-pulse` são só de carregamento | |
| Som e vibração desligados por padrão | n/a | não existem | |

## Garantias adicionadas

| Regra | Garantia |
|---|---|
| Toda classe de cor semântica usada existe na configuração do Tailwind | `src/lib/tokens.test.ts` (varre `src/`, falha em classe indefinida) |
| Pares de texto ≥ 4,5:1 nos dois temas | `src/index.contrast.test.ts` (lista de exceções vazia) |
| Bloco de movimento reduzido presente | `src/lib/tokens.test.ts` |

## Verificação

- `npx tsc -b --noEmit`: limpo.
- `npx eslint .`: 0 erros; 18 avisos já existentes (react-refresh), nenhum nos arquivos tocados.
- `npx prettier --check .`: limpo.
- `npx vitest run` nas suítes relacionadas (`lib`, `features/reports`, `components`, `features/financial`,
  `automations`, `extractions`, `squads`, `invites`, `auth`): 46 arquivos, 139 testes verdes.
- Build do Tailwind (`tailwindcss -i src/index.css`): gera `h-dvh`, `text-caption`, `text-micro`
  e o bloco `prefers-reduced-motion`.
- Não foi feita revisão visual no app rodando: a mudança é de tokens e de classes, sem nova composição.
  As alterações de cor do tema claro devem ser idênticas; o tema escuro do véu e de `text-on-primary`
  muda de propósito (era bug).

## Débitos, em ordem de custo

1. Migrar para Tailwind v4 (`@theme inline`, `@custom-variant`), hoje 3.4.17.
2. Conceito e identidade: decisão da pessoa dona, piloto na tela de Processos.
3. Lint para hexadecimal e `hsl()` fora de tokens, e para `text-[NNpx]` (frente de lint).
4. `components/ui/dialog.tsx` com véu `bg-primary/50` (shadcn; regenerar ou sobrescrever por token).
5. Contraste dos `--chart-*` no escuro (o `--chart-execution` #1e3a8a é pouco visível sobre a superfície
   escura). Os pares de texto já passam em 4,5:1 nos dois temas.
6. Reduzir a escala de tamanhos; `tabular-nums` nas tabelas de valores.
7. `ThemeProvider` não acompanha mudanças do sistema depois de carregar quando não há escolha salva.
8. Motion de timers JavaScript sem auditoria de reduced-motion.
