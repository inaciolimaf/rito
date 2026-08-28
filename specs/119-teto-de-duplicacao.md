# 119 — Teto de duplicação

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate fora da suíte)
**Depende de:** 007 · **Status:** ⬜ pendente

---

## 1. Objetivo

A «regra dos 3 usos» do `CLAUDE.md` §6 é a regra cultural mais citada do projeto e a única
sem instrumento: ela depende de alguém lembrar que já viu aquela estrutura duas vezes. Esta
spec dá um número a ela, trava o número, e paga o cluster que a medição expôs.

> Refatoração: nenhuma mudança de comportamento. Nenhuma tela muda de aparência ou de fluxo.

## 2. A boa notícia primeiro

Medido em 28/08/2026, commit `44469bd`, com `jscpd@4` sobre código de produção
(`backend/app` + `frontend/src`, sem testes), `--min-lines 10 --min-tokens 60`:

| Formato | Linhas | Clones | Linhas duplicadas | % |
|---|---|---|---|---|
| Python | 52.861 | 27 | 321 | **0,61%** |
| TSX | 27.269 | 32 | 474 | **1,74%** |
| TypeScript | 7.809 | 1 | 12 | 0,15% |

Isso é baixo de verdade, e é evidência de que a regra dos 3 usos vem sendo seguida sem
instrumento. O gate não existe para consertar um problema — existe para que esse número não
suba um décimo por spec durante as próximas cem.

## 3. O que a medição expôs

Os maiores clones estão todos no frontend, e não são acidentes espalhados: são **um padrão
repetido seis vezes**.

```
47L  features/account/LogoUploader.tsx:65      <-> features/users/AvatarUploader.tsx:68
38L  features/financial/CostCentersListPage    <-> features/financial/FinancialCategoriesListPage
37L  features/customer-origins/…ListPage       <-> features/lawsuit-types/LawsuitTypesListPage
26L  features/lawsuit-types/…ListPage          <-> features/squads/SquadsListPage
25L  components/domain/MoneyField.tsx:23       <-> components/domain/PercentField.tsx:23
21L  features/financial/FinancialReportPage    <-> features/reports/ReportPage
20L  features/action-groups/…ListPage          <-> features/lawsuit-types/…ListPage
```

Três achados distintos:

**A. Seis páginas de CRUD simples** — `CostCenters`, `FinancialCategories`, `CustomerOrigins`,
`LawsuitTypes`, `Squads`, `ActionGroups` — repetem o mesmo bloco de listagem+modal+confirmação.
Seis é o dobro do gatilho do §6. É o oitavo componente de `components/domain/` pedindo para
nascer.

**B. `LogoUploader` e `AvatarUploader` são o mesmo componente com dois nomes.** 47 linhas
idênticas, o maior clone do projeto.

**C. `MoneyField` e `PercentField`** compartilham 25 linhas de máscara e parsing — e ambos já
moram em `components/domain/`, o que significa que a duplicação está dentro do próprio design
system.

## 4. Escopo

**A. `.jscpd.json` versionado na raiz.** O número só serve se for reproduzível: o mesmo
comando, os mesmos caminhos, o mesmo `min-lines`/`min-tokens`, os mesmos formatos. Durante a
medição desta auditoria, o jscpd contou os mesmos arquivos `.tsx` duas vezes (uma como `tsx`,
outra como `javascript`), inflando o total — **calibrar isso e conferir que cada arquivo é
contado uma vez é a primeira tarefa da implementação**, antes de escolher o teto.

**B. Teto no CI**, como passo próprio, ao lado do `bundle:check` que a 098 já criou — fora do
`make test`, porque não é teste e não deve consumir os 300 s.

**C. As três correções** da seção 3: `<CrudListPage>`, fusão dos dois uploaders, extração da
máscara comum dos dois campos.

## 5. O teto — adotar no medido, não no redondo

O teto entra travando **o valor medido depois das correções**, arredondado para cima com
folga de um décimo. Nunca um alvo aspiracional: um número que ninguém atinge reprova o PR de
quem não causou o problema, e o resultado previsível é o gate ser desligado.

Dois tetos separados, um por linguagem. Python e TSX têm perfis de duplicação diferentes —
um teto único seria frouxo para um e apertado para o outro.

## 6. O que este gate vê e o que ele não vê

**Vê:** percentual de linhas em clone token-a-token, exato e comparável entre commits. Um PR
que leve o TSX de 1,4% a 2,1% reprova sem discussão.

**Não vê:** duplicação semântica. As seis páginas de CRUD ele pegou porque são quase idênticas;
uma sétima escrita com outra ordem de props e outros nomes de variável passa despercebida. O
gate reduz o custo de vigiar a regra dos 3 usos — não a substitui.

## 7. Fora de escopo

- Duplicação em `backend/tests` e `frontend/**/*.test.tsx`. Repetição em teste costuma ser
  legítima (cada teste conta sua história inteira), e medir junto contamina o número. Se um
  dia valer um teto próprio para testes, é spec própria.
- Detector de clone semântico. Outra classe de ferramenta.
- Refatorar clones abaixo do gatilho. Só os três achados da seção 3.

## 8. Modelo de dados / Contratos de API

Nada.

## 9. Front-end

**Componentes reutilizados:** `DataTable`, `FilterBar`, `FormModal`, `ConfirmDialog`, `EmptyState`.

**Componentes criados:**
- `<CrudListPage>` — o oitavo de `components/domain/`. Recebe schema Zod, colunas, rótulos e
  os hooks de query/mutation; entrega listagem + criar + editar + excluir. Justificativa da
  regra dos 3 usos: seis usos existentes, o dobro do gatilho.
- `<ImageUploader>` — absorve `LogoUploader` e `AvatarUploader`, que diferem só em proporção,
  tamanho máximo e endpoint.

**Rotas:** nenhuma nova. As seis telas existentes passam a usar `<CrudListPage>` e continuam
nas mesmas URLs.

**Estados:** loading, vazio, erro e sem permissão continuam sendo os das telas atuais — o
componente novo os herda, não os reinventa.

## 10. Regras de negócio

1. `.jscpd.json` versionado; cada arquivo contado uma vez só, verificado antes de fixar o teto.
2. Dois tetos, Python e TSX, cada um no valor medido após as correções + 0,1 pp.
3. O gate roda no CI como passo próprio, fora do `make test`.
4. As seis telas de CRUD passam a usar `<CrudListPage>`. Nenhuma perde funcionalidade —
   filtro, ordenação, export e ações de linha continuam.
5. `LogoUploader` e `AvatarUploader` viram um componente com props. Os dois testes existentes
   continuam passando, apontando para o componente novo.
6. `MoneyField` e `PercentField` compartilham a máscara; o comportamento de cada um é idêntico
   ao de hoje, incluindo a formatação brasileira com vírgula (§9).

## 11. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| frontend | `<CrudListPage>` lista, cria, edita e exclui | `src/components/domain/CrudListPage.test.tsx` | ~0,4 s |
| frontend | `<CrudListPage>` respeita permissão: sem acesso, sem botão de criar | idem | ~0,2 s |
| frontend | `<ImageUploader>` rejeita arquivo acima do máximo e formato fora da allowlist | `src/components/domain/ImageUploader.test.tsx` | ~0,3 s |
| frontend | máscara compartilhada formata dinheiro com vírgula e percentual com sufixo | `src/components/domain/masks.test.ts` | ~0,1 s |
| — | os testes das seis telas de CRUD passam **sem edição** | — | — |

**Total estimado:** +1,0 s de teste novo. As seis telas devem ficar mais rápidas de montar,
então o saldo tende a zero ou negativo — medir e registrar.

## 12. Descobertas

Preencher durante a implementação. **Obrigatório:** o número medido após as correções e o teto
escolhido para cada linguagem, com a conta.

## 13. Definição de pronto

- [ ] `.jscpd.json` versionado, sem contagem dupla
- [ ] Teto por linguagem no CI, no valor medido + 0,1 pp
- [ ] `<CrudListPage>` em `components/domain/`, usado pelas seis telas
- [ ] `<ImageUploader>` substituindo os dois uploaders
- [ ] Máscara compartilhada entre `MoneyField` e `PercentField`
- [ ] Testes das seis telas passam sem edição
- [ ] Número final e teto registrados em §12
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 119 em ✅
- [ ] Commit `refactor(119): teto de duplicação`
