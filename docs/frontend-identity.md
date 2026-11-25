# Identidade visual do Rito

Preenchido a partir de `templates/identity-spec.md` do padrão `frontend-standard`. Descreve o que existe
hoje no `frontend/` e onde a identidade ainda não foi decidida. O que está marcado **proposta** não foi
aprovado pela pessoa dona do produto e não está implementado.

Auditoria contra o padrão: `docs/frontend-standard-audit-identity.md`.

## 1. O conceito

**Estado atual: sem conceito.** A interface é o padrão do shadcn/ui com a paleta padrão (azul como
acento, cinza-azulado como neutro). Nenhuma tela tem um objeto do mundo real que organize o layout.
Isso é o que o padrão chama de "tema, não conceito", e a identidade do produto fica por fazer.

Quem usa: advogados e equipes administrativas de escritórios brasileiros. Usam o sistema o dia inteiro,
em monitores e às vezes no celular, com muitos dados por tela (processos, prazos, financeiro, CRM).
O produto precisa parecer sério, denso e confiável. Não pode parecer um painel genérico de SaaS.

**Proposta, não aprovada:** o processo judicial como concept. A tela de um processo vira a pasta do caso:
cabeçalho com número e partes, prazos e movimentações como folhas da pasta. Teste do padrão: isso muda o
layout de pelo menos três telas (Processos, Processo individual, Meu Painel), não só as cores. Antes de
qualquer mudança, a proposta vai para um piloto na tela de Processos e a pessoa dona decide no app rodando.

## 2. O esqueleto

**Estado atual:** `AppLayout` (`src/components/shell/AppLayout.tsx`) monta a casca: barra lateral com
ícones e texto (`Sidebar`), cabeçalho (`Header`), migalhas (`Breadcrumbs`), banner de integração e
`<main>` com `Outlet`. As telas de listagem repetem a mesma forma pelo `ListPageLayout`: título, ações à
direita, painel de indicadores, `FilterBar`, depois a `DataTable`.

Isso é o esqueleto de um painel administrativo genérico. O padrão aponta isso como o principal risco de
identidade. Não há uma raiz única por tela verificada por teste.

**Componentes de domínio** (`src/components/domain/`): `DataTable`, `FilterBar`, `FormModal`,
`EntityPicker`, `StatCard`, `EmptyState`, `ConfirmDialog`, `KanbanBoard`, `TabBar`, gráficos (`BarChart`,
`DonutChart`, `CashFlowChart`) e campos monetários e de máscara. Gerais, sem identidade própria ainda.

**Primitivas que o conceito pediria:** nenhuma ainda. Ficam para depois da decisão do conceito.

**Telas genéricas que ficam:** Configurações e área administrativa podem continuar como ferramenta. Listagens
de dados também. O que muda com o conceito são as telas de leitura frequente (Meu Painel, detalhe do
processo).

Guarantee: nenhuma. Uma regra de raiz única por tela só vale depois que o conceito existir.

## 3. Significados das cores

Os tokens semânticos estão em `frontend/src/index.css` (variáveis HSL por `:root` e `.dark`) e são
expostos em `frontend/tailwind.config.ts`.

| Cor ou marca | Significa | Nunca usada para |
|---|---|---|
| `accent` (azul) | ação principal e foco; navegação ativa | estado de alerta |
| `danger` (vermelho) | erro ou ação necessária agora (prazo vencido, falha) | itens antigos em lista |
| `warning` (âmbar) | atenção não urgente (dado desatualizado, revisão pendente) | ação de confirmação |
| `success` (verde) | confirmação de algo concluído | decoração |
| `muted` (texto esmaecido) | metadados e legendas | botões |
| `surface` / `surface-muted` | fundo de tela e de faixa | texto |
| `default` (borda) | separação entre blocos | estado |
| `overlay` | véu atrás de diálogos e gaveta mobile | texto |

**Orçamento:**
- uma ação principal sólida por tela (`variant="default"` do `Button`, em `accent`);
- `danger` só para o que pede ação agora. Hoje não há orçamento escrito verificado por teste; fica como
  débito;
- cor nunca carrega o sentido sozinha: o `FieldConfidenceBadge`, por exemplo, precisa do texto.

**Cores de gráfico** (`--chart-*`): conteúdo, não tema. Mesmos valores nas duas temas. As quatro fases do
ciclo (prospecção, produção, execução, rotação completa) têm nomes fixos no token, para que a mesma fase
tenha a mesma cor em todas as abas. Ver débito sobre contraste no tema escuro.

**Conteúdo do usuário**: a paleta de cores do texto do editor de modelos (`TemplateEditor`) é escolha do
usuário sobre o documento, não tema. Fica fora dos tokens, como exceção declarada.

## 4. Tipografia

- **Fontes:** nenhuma fonte customizada. A pilha é a do sistema operacional (padrão do Tailwind). Não há
  `@font-face` nem Google Fonts. Escolher as tipografias é decisão da pessoa dona, feita num piloto no
  app rodando. Não usar Inter em projeto novo (padrão).
- **Escala:** Tailwind padrão, com dois tamanhos extras como tokens, `text-micro` (10 px) e
  `text-caption` (11 px). Nenhum `text-[NNpx]` no componente. A escala padrão tem ainda nove tamanhos;
  reduzir para cerca de cinco é débito.
- **Números comparados:** nenhuma classe `tabular-nums` aplicada ainda. Tabelas de valores (financeiro,
  relatórios) são candidatas.
- **Corpo:** `text-sm` (14 px) é o corpo dominante das telas. O padrão sugere 15 px a 16 px decidido no
  app rodando. Não alterado.

## 5. Temas

- **Claro:** superfície branca, texto azul-escuro quase preto, acento azul.
- **Escuro:** superfície azul-escura profunda (não o claro invertido), texto quase branco, acento um pouco
  mais claro.

Cada tema tem valores próprios nos tokens. Não há inversão automática. A escolha segue o sistema até a
pessoa alternar (`ThemeProvider`, chave `rito.theme`). Débito: o provedor não acompanha mudanças do
sistema depois de carregar.

## 6. Movimento

- Transições de cor (`transition-colors`) e largura da barra lateral (`transition-[width]`). Nenhuma
  animação de entrada em massa.
- Loops: só carregamento. `animate-spin` (`Loader2`) em indicadores e `animate-pulse` em esqueletos de
  carregamento.
- Nenhum `@keyframes` próprio.
- **Movimento reduzido:** em `index.css`, `prefers-reduced-motion: reduce` zera transições e para o
  `animate-pulse`. O giro do `Loader2` continua de propósito, porque indica carregamento em curso.
- Som e vibração: nenhum.

## 7. Telas

| Tela | O que é no conceito atual | O que mudaria com o conceito proposto |
|---|---|---|
| Meu Painel | caixa de entrada e tarefas | leitura do dia, com o que pede ação em primeiro plano |
| Processos (listagem e detalhe) | tabela com filtros | a pasta do caso; piloto recomendado |
| Financeiro, Relatórios | painéis de número e gráficos | números com tabulação fixa; sem mudança de layout |
| CRM | quadro kanban | igual ao atual |
| Configurações, Conta, Suporte | formulários | igual ao atual (ferramenta) |
| Login, convite, erro | telas soltas centralizadas | a mesma linguagem visual da casca |

## 8. Piloto e ordem

Piloto proposto: a tela de **Processos** (detalhe), a mais aberta pelas pessoas usuárias. Passos:

1. a pessoa dona decide o conceito e as tipografias no app rodando, em 390 px e no desktop, claro e escuro;
2. primitivas (tokens de tipografia, esqueleto de processo, estados compartilhados);
3. piloto na tela de Processos;
4. demais áreas, um commit por área.

Até o piloto ser aprovado, nada além das correções de token deste documento muda.

## 9. Garantias

| Regra | Garantia hoje |
|---|---|
| Cor literal do Tailwind proibida | `rito/no-literal-tailwind-color` (eslint) |
| Classe de cor semântica precisa existir na configuração | `src/lib/tokens.test.ts` |
| Bloco de movimento reduzido presente | `src/lib/tokens.test.ts` |
| Altura de tela com `dvh`, não `vh` | revisão manual; sem lint |
| Tamanho de texto só por token | revisão manual; sem lint (débito) |
| Cor hexadecimal fora de tokens | revisão manual; sem lint (débito) |
| Contraste de pares de texto nos dois temas, ≥ 4,5:1 | `src/index.contrast.test.ts` |
| Uma raiz por tela | não existe (depende do conceito) |
