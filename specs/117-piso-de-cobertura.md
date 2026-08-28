# 117 — Piso de cobertura

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s no `make test` (passo próprio no CI)
**Depende de:** 009 · **Status:** ⬜ pendente

---

## 1. Objetivo

`pytest-cov` e `@vitest/coverage-v8` estão instalados desde a fundação. Não existe
`--cov-fail-under`, não existe `thresholds` no Vitest, e o CI nunca roda nenhum dos dois — o
que significa que, em 100 specs, **ninguém nunca soube qual é a cobertura do Rito**, nem se
ela subiu ou desceu. Esta spec mede, publica o número e trava o piso.

> Refatoração: nenhuma mudança de comportamento. Nenhum teste novo de feature; só medição,
> configuração e as exclusões justificadas.

## 2. O número — medido em 28/08/2026, commit `44469bd`

### Backend

```
1496 passed · 21.467 statements · 2.343 não cobertos → 89,1%
```

Boa notícia e surpresa agradável para quem esperava o pior de um projeto grande. Mas a média
esconde uma estrutura que importa:

| Recorte | Statements | Não cobertos | Cobertura |
|---|---|---|---|
| `app/` inteiro | 21.467 | 2.343 | **89,1%** |
| `app/` sem `workers/` | 20.732 | 1.842 | **91,1%** |
| só `app/workers/` | 735 | 501 | **31,8%** |

### Frontend

```
Statements 55,03% (13.417/24.380) · Branches 74,87% · Functions 49,13%
```

A assimetria é o achado real desta spec: **o backend está em 89% e o frontend em 55%**. Onde
o gate tem dente é do lado que ninguém estava olhando.

## 3. O buraco dos workers — e por que ele não é um buraco

Os 501 statements não cobertos de `app/workers/` não são descuido. O `pyproject.toml` já
documenta a decisão, ao abrir a exceção de `disallow_untyped_decorators`:

> «os corpos das tasks continuam sob `strict`. E eles são finos de propósito — a regra de
> negócio mora nos services, exercitada direto pelos testes.»

E a memória do projeto reforça: nenhum teste importa worker, porque chamar um worker de
varredura por tenant abre um engine por tenant e leva minutos.

Isso é uma decisão defensável. O problema é que, sem gate, ela é indistinguível de
negligência — e, com gate mas sem cuidado, `workers/` vira o esconderijo natural de código que
alguém não quis testar.

**A resolução é dupla, e as duas metades são obrigatórias:**

1. `app/workers/*` sai da medição, com a justificativa acima escrita no `pyproject.toml`,
   citando esta spec. O piso passa a valer sobre os 91,1% que significam alguma coisa.
2. Um meta-teste garante que os corpos de task continuam finos — nenhuma função de
   `app/workers/` acima de 15 statements, e nenhuma contendo `if`/`for` que não seja iteração
   de despacho. Sem isso, a exclusão vira porta dos fundos.

## 4. Onde o backend perde, fora dos workers

| Arquivo | Statements | Cobertura | Leitura |
|---|---|---|---|
| `ai/tools/write.py` | 252 | **58%** | é o módulo que o §7 regra 4 mais protege — toda ferramenta de escrita exige confirmação humana e `ai_audit_log`. 105 statements sem teste aqui é o achado mais desconfortável da tabela |
| `public/router.py` | 233 | **57%** | a API pública tem contrato travado (22 endpoints) mas não cobertura de comportamento |
| `cli.py` | 148 | 53% | `rito backup`/`restore`/`health` — testado pela imagem no CI, não pela suíte |
| `domain/automations/actions.py` | 91 | 64% | ações de automação |
| `domain/automations/conditions.py` | 56 | 57% | condições de automação |
| `integrations/ocr/tesseract.py` | 54 | 44% | OCR |
| `integrations/messaging/*.py` | 64 | 50% | e-mail |

Esta spec **não fecha esses buracos** — ver §6. Ela os torna visíveis e impede que cresçam.

## 5. Escopo

**A. Medir e publicar.** Passo de CI próprio, ao lado do `bundle:check` e do `pip-audit` que a
098 e a 100 já criaram. **Fora do `make test`**: instrumentação de cobertura custa tempo, e o
wall-clock está em 288 s de 300 s — pôr cobertura dentro do orçamento seria gastar a margem
que a 105 vai comprar.

**B. Piso no valor medido.** `--cov-fail-under` no backend, `coverage.thresholds` no Vitest,
ambos no número que a implementação medir, arredondado para baixo no inteiro. Nunca um alvo
redondo aspiracional: um número que ninguém atinge reprova o PR de quem não causou o problema,
e o gate morre desligado na semana seguinte.

**C. Exclusão dos workers**, com as duas metades da §3.

**D. `test-timing.json` ganha vizinho.** `coverage.json` versionado com os números da entrega,
para que a evolução fique no histórico do git como o wall-clock já fica.

## 6. Fora de escopo

- **Escrever testes para subir a cobertura.** Vinculante. Esta spec mede e trava; subir é
  trabalho de spec própria, e o inventário da §4 é a fila dela. Misturar as duas coisas faz o
  piso ser escolhido em função do que deu tempo de testar.
- Cobertura de branch como gate. O backend nem mede hoje; ligar junto com o piso de statements
  seria dois números novos ao mesmo tempo.
- Cobertura de e2e. Playwright mede outra coisa e não entra nesta conta.
- Mutação. Spec própria — e ela mede o que a cobertura não vê (§7).

## 7. O que este gate vê e o que ele não vê

**Vê:** percentual de statements executados, exato e comparável entre dois commits. Uma queda
é um número, não uma opinião. É gate programático de verdade — pode reprovar PR sem revisão
humana.

**Não vê:** se a asserção aperta. Um arquivo com 100% de cobertura e
`assert response is not None` em todo teste passa igual. Cobertura mede linha executada, não
propriedade verificada — e é por isso que ela é um piso, nunca uma meta.

## 8. Modelo de dados / Contratos de API / Front-end

Nada.

## 9. Regras de negócio

1. Cobertura é medida em passo próprio do CI, nunca dentro do `make test`.
2. O piso do backend é o valor medido sem `app/workers/`, arredondado para baixo.
3. O piso do frontend é o valor medido de **statements**, arredondado para baixo. Que ele
   comece perto de 55% é um fato, não um endosso — a spec registra isso explicitamente para
   que o número não seja lido como aprovação.
4. `app/workers/*` fica fora da medição, com justificativa no `pyproject.toml` citando esta
   spec **e** o meta-teste da regra 5. As duas coisas ou nenhuma.
5. Meta-teste: nenhuma função em `app/workers/` passa de 15 statements. Se passar, a regra de
   negócio vazou para o worker e a exclusão deixou de ser honesta.
6. `coverage.json` versionado, atualizado a cada spec que mexer no número, no molde do
   `test-timing.json`.
7. O piso é **piso**: sobe quando a medição sobe, nunca desce. Baixar o número exige spec
   própria com justificativa — igual ao orçamento de wall-clock.

## 10. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | nenhuma função de `app/workers/` acima de 15 statements (AST) | `tests/meta/test_workers_finos.py` | ~0,2 s |
| meta | todo módulo excluído da cobertura tem justificativa no `pyproject.toml` | `tests/meta/test_workers_finos.py` | ~0,1 s |

**Total estimado:** +0,3 s no `make test`. A medição de cobertura em si roda fora dele.

### Aceite

```bash
# backend, passo próprio de CI
cd backend && uv run pytest -n 3 --cov=app --cov-report=term --cov-fail-under=<piso>

# frontend, passo próprio de CI
cd frontend && npm run test:coverage
```

Os dois números vão para o `GITHUB_STEP_SUMMARY`, como o wall-clock já vai.

## 11. Descobertas

Preencher durante a implementação. **Obrigatório:** os quatro números medidos (backend com e
sem workers, frontend statements e functions) e os dois pisos escolhidos, com a conta.

## 12. Definição de pronto

- [ ] Passo de cobertura no CI, fora do `make test`
- [ ] `--cov-fail-under` no backend e `thresholds` no Vitest, no valor medido
- [ ] `app/workers/*` excluído com justificativa no `pyproject.toml`
- [ ] Meta-teste de corpo fino de worker, verde
- [ ] `coverage.json` versionado
- [ ] Números publicados no resumo do CI
- [ ] **Nenhum teste de feature escrito nesta spec**
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 117 em ✅
- [ ] Commit `refactor(117): piso de cobertura`
