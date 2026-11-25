# Auditoria de acessibilidade (WCAG 2.2 AA) do frontend

Referência: `references/accessibility.md` e a parte de acessibilidade de `references/guarantees.md`
do padrão de frontend. Formato: regra | status | ação | dívida.

Status: **ok** (atende), **corrigido** (estava falho e foi corrigido neste ciclo), **parcial**
(atende em parte, o resto está na dívida), **dívida** (não atende, não corrigido).

## Regras

| Regra | Status | Ação | Dívida |
|---|---|---|---|
| Foco visível (2.4.7, 2.4.13) | ok | Todo controle usa `focus-visible:ring-2 ring-accent` (anel de 2 px, sólido). Confirmado em `Button`, `Input`, `Checkbox`, `Sidebar`, `Header`, `DataTable`. | Contraste do anel depende do token de acento; ver a linha de contraste. |
| Acessível por teclado (2.1.1) | corrigido | `KanbanBoard`: cards só se moviam por arrastar. Cada card ganhou um `select` "Mover para…" (uso de 2.5.7 Movimentos de arrasto). `EntityPicker`: Escape fecha a lista mesmo sem resultados. | Drawer mobile do `AppLayout` não é um diálogo modal: o foco não fica preso dentro dele (ver "Dialogs"). |
| Rótulo em campos (3.3.2, 1.3.1) | parcial | `FilterBar`, `EntityPicker`, `ConfirmDialog`, `FormModal` usam `Label htmlFor`/`aria-label`. | Erro de campo não recebe `aria-invalid` nem `aria-describedby` nos formulários de feature: o erro é exibido, mas não é anunciado ao campo. Corrigir num `FormField` compartilhado. |
| Nome acessível em botão de ícone (4.1.2) | corrigido | Sidebar recolhida perdia o nome dos links (o texto saía do DOM): agora o rótulo vai em `sr-only`. Já tinham nome: `Header` (menu, usuário), `ThemeToggle`, `NotificationBell`, `QuickAddMenu`, remoções de `EntityPicker`, seleção de linhas do `DataTable`. | Editar/Excluir de `CrudListPage` são textos genéricos sem o nome da linha (ex.: "Editar" em todas as linhas). Exige passar um rótulo por linha. |
| Diálogos: foco preso e devolvido (2.4.3, 2.1.2) | ok | `ui/dialog` é Radix: prende o foco, fecha com Escape e devolve o foco ao disparador. Testado em `FormModal` e `ConfirmDialog` pelo axe. | Drawer mobile (`AppLayout`) é overlay próprio, sem foco preso e sem `role="dialog"`. Trocar por um diálogo Radix de tela cheia. |
| Landmarks e link de pular (2.4.1, 1.3.1) | corrigido | `AppLayout` ganhou link "Pular para o conteúdo" (primeiro item focável) apontando para `main#conteudo`. Já havia `header`, `nav` ("Navegação principal"), `nav` de breadcrumb e `main`. | — |
| Título e foco por rota (2.4.2, 2.4.3) | corrigido | `useRouteFocus` (novo, em `components/shell/`): `document.title` vira "Tela · Rito" e o foco vai para o `main` ao trocar de rota. Testado em `AppLayout.test.tsx`. | — |
| Ordem de títulos (1.3.1, 2.4.6) | parcial | Cada tela tem um `h1`. Dentro do `KanbanBoard`, o título de coluna é `h3` sem `h2` antes. | Tabela de títulos das telas não foi auditada uma a uma (são 40+). Revisar quando houver teste de títulos por rota. |
| Regiões ativas para status assíncrono (4.1.3) | parcial | Já existem `role="status"` em resultados de salvar/extrair/análise e `role="alert"` para erro (FormModal, DataTable, banner de integração). `DataTable` agora marca `aria-busy` durante o carregamento. | Não há sistema de toast: ações que só mostram sucesso por toast não seriam anunciadas. Quando houver toast, ele precisa de `role="status"`. |
| Ordenação anunciada | corrigido | Cabeçalho ordenável do `DataTable` tem `aria-sort` (ascending/descending). | — |
| Tabela com nome | dívida | `DataTable` não tem `caption` nem `aria-label`. | Adicionar prop opcional `caption` (sr-only) e passá-la das telas. |
| Alvo de toque (2.5.8) | ok | Botões `sm` têm h-8 (32 px, acima de 24 px). Links de texto em linha ficam isentos. Botões principais são `h-10`. | Meta de 44 px para ações principais de toque não foi aplicada (aceita pelo padrão como "adotada", não exigida). |
| Contraste de texto (1.4.3) | parcial | Teste novo `src/index.contrast.test.ts` lê os blocos `:root` e `.dark` de `index.css` e checa 14 pares de texto em cada tema. 10 pares estão abaixo de 4,5:1 e entram como exceção com motivo. | Corrigir os tokens (ver tabela abaixo). Não editado aqui porque os tokens são do slice de identidade. |
| Idioma da página (3.1.1) | ok | `index.html` com `lang="pt-BR"`. | — |
| Sem movimento forçado (2.3.3) | ok | Motion é responsabilidade do slice de motion; `DataTable` usa `animate-pulse` só no carregamento. | Conferir `prefers-reduced-motion` no `animate-pulse` quando o slice de motion fechar. |
| Zoom e reflow (1.4.10) | parcial | Layout de 390 px funciona por classes responsivas. Sem teste automatizado de overflow horizontal nesta suíte (é guarantee de e2e, fora do escopo deste ciclo). | Playwright `scrollWidth > innerWidth` em 390 px (guarantee de e2e). |
| Axe sobre componentes de domínio | ok | `src/components/domain/a11y.axe.test.tsx` (jest-axe): DataTable, FormModal, ConfirmDialog, FilterBar, EntityPicker, KanbanBoard, TabBar, StatCard, StagnantBadge, EmptyState. Desliga `color-contrast` (jsdom não calcula cor; ver linha de contraste) e `region` (regra de página). | Axe sobre todas as rotas em ambos os temas é guarantee de e2e (Playwright), não rodado aqui. |

## Contraste dos tokens (medido com o algoritmo WCAG sobre `index.css`)

Abaixo de 4,5:1 para texto normal. Estão listados em `KNOWN_EXCEPTIONS` do teste de contraste;
quando o token for corrigido, o teste falha e manda tirar a entrada.

| Tema | Par (texto sobre fundo) | Razão | Onde aparece |
|---|---|---|---|
| claro | `text-muted` sobre `surface-muted` | 4,31:1 | cabeçalho da tabela |
| claro | `danger` sobre `surface` | 3,78:1 | mensagens de erro, "Excluir" |
| claro | `danger` sobre `surface-muted` | 3,46:1 | erro sobre fundo cinza |
| claro | `success` sobre `surface` | 2,30:1 | texto de sucesso |
| claro | `warning` sobre `surface` | 2,14:1 | texto de aviso |
| claro | `danger-foreground` sobre `danger` | 3,61:1 | botão destrutivo |
| claro | `success-foreground` sobre `success` | 2,19:1 | botão de sucesso |
| escuro | `danger` sobre `surface` | 3,61:1 | erro em texto |
| escuro | `danger` sobre `surface-muted` | 2,99:1 | erro sobre fundo cinza |
| escuro | `accent` sobre `surface-muted` | 4,09:1 | link sobre fundo cinza |

Ação recomendada: escurecer `--danger`, `--success` e `--warning` (texto) no claro e clarear
`--danger` no escuro, ou usar tokens `*-text` separados dos de preenchimento. Dono: slice de tokens.

## Dívida consolidada

1. Erro de campo sem `aria-invalid`/`aria-describedby` (precisa de `FormField` compartilhado).
2. Drawer mobile sem foco preso nem `role="dialog"`.
3. Editar/Excluir de `CrudListPage` sem o nome da linha.
4. `DataTable` sem `caption`.
5. Toast ausente; quando existir, precisa de região `role="status"`.
6. Dez pares de token abaixo de 4,5:1 (tabela acima).
7. Axe de rota inteira em ambos os temas e teste de overflow em 390 px ficam para o e2e.
8. Leitor de tela e navegação só por teclado no fluxo principal: revisão manual, não automatizada.
9. Radix injeta guardas de foco `aria-hidden` com `tabindex=0`; o axe as acusa. O teste as remove antes da varredura. Falso positivo, não corrigido na origem.
