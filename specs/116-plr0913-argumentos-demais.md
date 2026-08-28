# 116 — PLR0913: argumentos demais

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106, 111, 112 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar `PLR0913` (too-many-arguments) e resolver as funções acima do teto. Assinatura longa é
o sintoma clássico de uma função que faz mais de uma coisa, ou de um conjunto de parâmetros
que já é um objeto e ninguém nomeou — que é exatamente o SRP do `CLAUDE.md` §5 aplicado à
assinatura.

> Refatoração: nenhuma mudança de comportamento. Muda a forma de chamar, não o que acontece.

## 2. Nota sobre esta spec

Na auditoria que originou esta leva, `PLR0913` foi a única regra que eu recomendei **não**
ligar: o `Depends()` do FastAPI infla a contagem por construção, e no teto default de 5
argumentos são 112 violações, das quais 36 em `router.py` são rotas legítimas. A decisão de
ligar assim mesmo foi tomada; a spec cumpre isso, e a forma de cumprir sem transformar o gate
em ruído é a calibragem da seção 3. Registrado aqui para quem ler daqui a seis meses saber que
o número não foi escolhido no chute.

## 3. Calibragem — medida, não arbitrada

Contagem em 28/08/2026, commit `44469bd`, sobre `ruff check .`:

| `max-args` | Total | Em `router.py` | Fora de `router.py` |
|---|---|---|---|
| 5 (default) | 112 | 36 | 76 |
| 6 | 48 | 16 | 32 |
| 7 | 30 | 9 | 21 |
| **8** | **14** | **5** | **9** |
| 10 | 5 | 3 | 2 |
| 12 | 3 | 2 | 1 |

**Escolha: `max-args = 8`.** É o joelho da curva. Abaixo dele o número explode por causa do
padrão de DI do FastAPI e dos repositórios com muitos filtros — que são casos reais, mas não
são o defeito que a regra existe para achar. Em 8, sobram 14 funções, e cada uma tem
assinatura longa de verdade, não por causa de framework.

```toml
[tool.ruff.lint.pylint]
max-args = 8
```

Sem `per-file-ignores` para `router.py`: cinco rotas ficam acima de 8 e elas merecem o mesmo
tratamento que o resto. Silenciar a camada inteira esconderia a rota que realmente tem 14
parâmetros.

## 4. Escopo — as 14

As nove fora de `router.py` são o núcleo do trabalho. Os campeões, e o que fazer:

| Arquivo:linha | Args | Correção |
|---|---|---|
| `domain/customers/repository.py:114` | 14 | filtros de listagem → um dataclass `CustomerFilters` |
| `integrations/http/client.py:45` | 11 | configuração de resiliência → um dataclass `RetryPolicy` |
| `domain/customers/repository.py:63` | 10 | mesmo `CustomerFilters` |
| `domain/financial/repository.py:255` | 10 | `TransactionFilters` |
| `domain/financial/service.py:339` | 10 | idem, repassando o filtro |
| `domain/ai/service.py:361` | 9 | separar contexto de execução dos parâmetros de chamada |
| `domain/posts/service.py:85` | 9 | `PostFilters` |
| `domain/ai/editor.py:365`, `domain/ai/service.py:109` | 8 | idem |
| `core/dates.py:199` | 8 | avaliar caso a caso |

O padrão dominante é evidente: **repositório de listagem recebendo cada filtro como parâmetro
solto**. Aparece em `customers`, `financial`, `posts` e `reports` — quatro vezes, muito além
da regra dos 3 usos do §6. A correção certa não é encurtar quatro assinaturas em quatro
lugares diferentes; é um objeto de filtro por contexto, e possivelmente um tipo base comum,
já que `BaseRepository` existe desde a 003.

As cinco em `router.py` ficam por último: mexer em assinatura de rota é o que tem maior chance
de mudar contrato, e o contrato é o que não pode mudar.

## 5. Fora de escopo

- Baixar `max-args` abaixo de 8. Se um dia fizer sentido, é spec própria, com nova medição.
- `max-positional-args`. Regra diferente, discussão diferente.
- Tocar nas 19 ocorrências em `tests/` que estão abaixo de 8 — no teto escolhido elas nem
  aparecem.

## 6. Modelo de dados / API / Front-end

Nada. **Nenhum contrato de API muda**: as cinco rotas afetadas continuam aceitando exatamente
os mesmos query params, com os mesmos nomes, tipos e defaults. O que muda é como o router
repassa isso para baixo. O `test_public_api_contract.py` e o snapshot de rotas são a prova.

## 7. Regras de negócio

1. `PLR0913` no `select`, `max-args = 8`.
2. Nenhuma mudança de comportamento; nenhum contrato de API alterado.
3. Objeto de filtro é `dataclass` ou modelo Pydantic tipado — nunca `dict[str, Any]`. Trocar
   argumentos demais por um `Any` seria piorar o código para agradar o lint.
4. Onde o mesmo padrão de filtro aparecer pela terceira vez, ele sobe para um tipo comum
   junto ao `BaseRepository` (§6, regra dos 3 usos).
5. Nenhum `per-file-ignores`. No máximo **2** `# noqa: PLR0913`, com justificativa, travados
   por meta-teste.
6. As cinco rotas são as últimas a serem tocadas.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | no máximo 2 `# noqa: PLR0913`, justificados | `tests/meta/test_final_audit.py` (estende) | ~0,1 s |
| meta | as rotas de `/api/v1` aceitam os mesmos query params de antes (snapshot) | `tests/meta/test_public_api_contract.py` (estende) | ~0,3 s |
| — | testes de listagem das specs 018, 022, 052 e 084 passam sem edição | — | — |

**Total estimado:** +0,4 s

## 9. Descobertas

Preencher durante a implementação — em especial, se o objeto de filtro comum apareceu e onde
ele mora.

## 10. Definição de pronto

- [ ] `PLR0913` no `select` com `max-args = 8`
- [ ] As 14 resolvidas; no máximo 2 `noqa` justificados
- [ ] Nenhum `per-file-ignores`
- [ ] Objetos de filtro tipados, sem `dict[str, Any]`
- [ ] Nenhum query param de rota mudou de nome, tipo ou default
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 116 em ✅
- [ ] Commit `refactor(116): argumentos demais`
