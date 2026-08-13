# 066 — Modelos: engine de variáveis

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 065 · **Status:** ✅ concluída

---

## 1. Objetivo

O modelo (spec 064/065) hoje é só texto fixo. Esta spec permite escrever
`{{cliente.nome_completo}}` no corpo/cabeçalho/rodapé e resolver contra o cliente e o
processo escolhidos na hora de gerar o documento (spec 067 consome isso).

## 2. Escopo

- Catálogo de variáveis do levantamento (docs §4.9): cliente, processo, escritório,
  usuário.
- Resolução com dados reais: dado um modelo + `customer_id`? + `lawsuit_id`?, devolve
  o HTML com `{{namespace.campo}}` substituído pelo valor.
- Valor por extenso: datas (`cliente.data_nascimento_extenso`,
  `processo.data_ajuizamento_extenso`, `processo.data_arquivamento_extenso`) e dinheiro
  (`processo.valor_honorarios_extenso`, `processo.valor_causa_extenso`).
- Variável ausente (sem dado ou sem escopo informado) fica sinalizada no HTML de
  saída, nunca vira texto vazio silencioso nem quebra a resolução das outras.
- Endpoint que lista o catálogo (pra um seletor "Inserir variável" no editor).

## 3. Fora de escopo

- Autocomplete ao digitar `{{` no editor (spec 065) — o seletor da toolbar já cobre a
  necessidade real (inserir sem decorar o nome da variável); autocomplete inline é UX
  incremental, não funcional.
- Máscara de CPF/CNPJ/telefone na saída — os valores saem como estão gravados
  (a validação/máscara de entrada já é de specs anteriores, 017/018); reformatar na
  saída é decisão de exibição, não de resolução.
- Variáveis condicionais (`{{#if}}`) ou laços (`{{#each}}`) — o levantamento não pede
  lógica no modelo, só substituição direta.

## 4. Modelo de dados

Nenhuma tabela nova. O catálogo é uma constante Python (`app/domain/templates/variables.py`),
não dado de banco — mesmo padrão de `PLAN_QUOTA_GB` (spec 063) e dos 10 grupos DRE.

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/template-variables` | — | `200 [{namespace, key, label}]` | autenticado |
| POST | `/api/v1/templates/{id}/resolve` | `{customer_id?, lawsuit_id?}` | `200 {content, header_content, footer_content, missing[]}` | autenticado |

Erros: `404` (modelo/cliente/processo inexistente ou de outro tenant).

## 6. Front-end

**Componentes reutilizados:** nenhum de `components/domain`.
**Componentes criados:** `VariablePicker` (select agrupado por namespace, insere o
token `{{ns.campo}}` no cursor do `TemplateEditor`) — 2º uso de "inserir algo na
posição do cursor do editor" (o 1º é a imagem, spec 065); ainda não vira componente
genérico, mas é a peça que a spec 067 vai reusar pro preview antes de gerar o PDF.
**Rotas:** nenhuma nova — o seletor entra na toolbar de `/library/:id` (spec 065).
**Estados:** variável ausente aparece destacada (`<mark>`) no HTML — sem estado de UI
próprio, é conteúdo.

## 7. Regras de negócio

1. Variável reconhecida é `{{namespace.campo}}` — `namespace` ∈
   `cliente`/`processo`/`escritorio`/`usuario`; padrão fora disso não é tocado (fica
   literal no texto, não quebra a resolução).
2. `cliente.*`/`processo.*` exigem `customer_id`/`lawsuit_id` no pedido de resolução —
   sem o escopo, toda variável daquele namespace vira "ausente" (regra 4), mas
   `escritorio.*`/`usuario.*` resolvem de qualquer forma (não dependem de escopo).
3. `usuario.*` sempre resolve contra quem está gerando o documento (usuário logado),
   nunca contra o responsável do processo — esse é `processo.responsavel`.
4. Variável ausente (namespace sem escopo, campo nulo no banco, ou nome de variável
   desconhecido) vira `<mark data-missing="true">{{namespace.campo}}</mark>` na saída —
   visível, nunca some nem quebra a resolução das demais.
5. Datas resolvem em `DD/MM/AAAA` (regra de UI do CLAUDE.md) por padrão; a variante
   `_extenso` do mesmo campo resolve por extenso ("20 de agosto de 2026" → "vinte de
   agosto de dois mil e vinte e seis").
6. Dinheiro resolve como string com vírgula decimal por padrão (`Numeric` → BR); a
   variante `_extenso` resolve por extenso, incluindo "reais"/"centavos".
7. A resolução nunca modifica o modelo salvo — é sempre uma cópia (a mesma spec 067 vai
   gerar PDF a partir do resultado, sem tocar em `templates.content`).

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | extenso de data (1º dia usa "primeiro", demais cardinal) | `tests/unit/test_template_variables.py` | ~0,1 s |
| unit | extenso de dinheiro (reais/centavos, valor inteiro sem centavos) | idem | ~0,1 s |
| unit | `resolve_content` substitui variável conhecida e marca a desconhecida | idem | ~0,1 s |
| unit | variável de namespace sem dado vira `<mark>` sem quebrar as outras | idem | ~0,1 s |
| integração | resolução real: cliente + processo + escritório + usuário, um campo de cada | `tests/integration/test_template_resolve.py` | ~0,4 s |
| integração | sem `customer_id`: variável de cliente vira ausente, resto resolve | idem | ~0,3 s |
| integração | catálogo de variáveis lista os 4 namespaces | idem | ~0,2 s |
| RLS | resolver com `customer_id`/`lawsuit_id` de outro tenant → 404 | idem | ~0,3 s |

**Total estimado:** ~1,6 s
**Fixtures externas:** nenhuma.

## 9. Descobertas

- `num2words` (pt_BR) cobre cardinal e `to='currency'` prontos — sem stubs de tipo
  publicados, entrou como override `ignore_missing_imports` no mypy (mesmo padrão do
  Celery), isolado em `variables.py`.
- `processo.numero_cnj` precisou de `format_cnj(parse_cnj(...))` (spec 025) — o banco
  guarda só dígitos (regra 9 daquela spec), e "por extenso"/apresentação sempre quer a
  máscara.
- `Occupation`/`MaritalStatus`/`Court`/`Step` são carregados via `session.get()` direto
  (não via repositório) quando a PK é inteira e não há método `get_by_id` genérico
  pronto pra ela — mesmo padrão já usado em `attachments/service.py`.
- **Orçamento:** wall-clock da suíte cheia fechou em 287 s (teto 300 s) — ainda
  apertado. Um teste de performance pré-existente (`test_inbox_perf.py`, sem relação
  com esta spec) flakou uma vez sob carga concorrente e passou isolado — ambiente
  compartilhado, não regressão. A spec 067 precisa ser a mais enxuta possível em teste
  novo; se estourar, a refatoração 070 é o lugar de otimizar.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock < 300 s (287 s — apertado, ver Descobertas)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(066): modelos — engine de variáveis`
