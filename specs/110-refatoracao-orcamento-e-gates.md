# 110 — 🔧 REFATORAÇÃO — Orçamento e gates

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** devolver o wall-clock para ≤ 200 s
**Depende de:** 101, 104–109 · **Status:** ⬜ pendente

---

## 1. Objetivo

A décima da faixa. Não entrega feature nem liga gate novo: entrega a garantia de que as sete
anteriores formam um conjunto coerente — e que os gates que elas ligaram continuam **valendo**,
não apenas configurados.

> Refatoração não muda comportamento. **Todos** os testes anteriores passam sem edição.

Especificidade desta: as specs 104–109 são, elas mesmas, sobre qualidade. Auditar uma faixa de
specs de qualidade é diferente de auditar uma faixa de features — o risco aqui não é código
ruim ter entrado, é **gate ligado ter deixado de morder**.

## 2. As sete auditadas

| Spec | Entregou | O que pode ter apodrecido |
|---|---|---|
| 101 | stubs desbloqueados e dívida nomeada | os três meta-testes de reincidência ainda pegam? |
| 104 | imports pesados fora do boot | alguém devolveu um import pesado ao topo? |
| 105 | template DB e `ROLLBACK` por teste | `@pytest.mark.commits` cresceu além dos 4 arquivos? |
| 106 | `C901` em 6 | os `noqa` passaram de 3? alguma função voltou a crescer? |
| 107 | RET, PTH, ERA, TID, ICN | a exceção de `ERA001` virou guarda-chuva? |
| 108 | `ASYNC` | apareceu I/O bloqueante novo em corrotina? |
| 109 | `PLR0915` | `create_app` voltou a inchar? |

## 3. Auditoria dos gates ligados na faixa

Cada item é uma pergunta com resposta verificável, não uma impressão.

- [ ] Nenhum `per-file-ignores` novo entrou no `pyproject.toml` sem comentário justificando
- [ ] O total de `# noqa` no projeto **não cresceu** desde a 109 — contar e comparar
- [ ] Todo `# noqa` tem justificativa na linha acima (o `test_final_audit.py` já exige; conferir
      que ninguém afrouxou o teste)
- [ ] As listas de exceção versionadas das specs 104–109 estão nos tetos declarados
- [ ] Nenhum gate desta faixa foi silenciado por arquivo em vez de corrigido na origem
- [ ] `make lint` roda sobre o repositório inteiro, não sobre subconjunto

## 4. Auditoria de orçamento — o item central desta spec

As specs 104 e 105 existem para devolver wall-clock. Esta confere que ele foi devolvido e que
não vazou de volta.

- [ ] `test-timing.json` com o número medido em cada uma das sete
- [ ] Wall-clock de `make test` **≤ 200 s**. Se estiver acima, esta spec não fecha: o ganho da
      105 foi perdido em algum lugar e achar onde é o trabalho
- [ ] `import app.main` continua abaixo de 9 s
- [ ] Coleta do pytest medida e registrada — a 104 a reduziu de raspão; se ela voltou a crescer,
      o motivo é import novo em `tests/`
- [ ] Duas execuções seguidas de `make test` não acumulam linha no `rito_test`
- [ ] Nenhum teste novo da faixa entrou sem custo declarado

## 5. Auditoria de coerência

- [ ] Os meta-testes das sete usam AST, não regex — nenhum foi escrito com `grep` e falso
      positivo em comentário
- [ ] Nenhum dos meta-testes novos importa worker (memória de projeto: abre um engine por tenant)
- [ ] Nenhum meta-teste novo é cronometrado — tempo em CI compartilhado oscila e vira flake
- [ ] Os inventários citados nas sete specs conferem com a realidade do código hoje. Onde
      divergirem, a spec de origem ganha uma linha em `## Descobertas`, não uma correção
      silenciosa
- [ ] Sobreposição entre 106 e 109 reconciliada: nenhuma função foi "corrigida" duas vezes de
      formas incompatíveis

## 6. Auditoria de testes

- [ ] Nenhum teste passa por acidente: mutar a asserção quebra
- [ ] Nenhum teste depende da ordem de execução — verificar rodando a suíte em ordem invertida
      pelo menos uma vez, à mão, e registrar o resultado
- [ ] Nenhum `sleep`
- [ ] Nenhum teste faz I/O de rede
- [ ] `@pytest.mark.commits` (spec 105) em no máximo 4 arquivos, todos ainda justificados
- [ ] Nenhum teste anterior foi editado por nenhuma das sete specs — este é o critério que
      separa refatoração de reescrita, e vale conferir no `git log`

## 7. Auditoria de dívida

- [ ] Percorrer as seções `## Descobertas` das sete specs, item a item
- [ ] Resolver o que for barato
- [ ] O que não for, entra em `docs/DIVIDA-TECNICA.md` com número, impacto e spec-alvo
- [ ] Nenhum `TODO` ou `FIXME` órfão
- [ ] Nenhum código morto deixado pelas extrações da 106 e da 109

## 8. Fora de escopo

- Ligar qualquer gate novo. A faixa 111–119 faz isso; esta spec só confere a anterior.
- Escrever teste de feature.
- Mexer em `app/` além do necessário para resolver dívida registrada nas sete.

## 9. Plano de testes

Nenhum teste novo, por definição. O trabalho é conferir os que existem.

Se a auditoria descobrir uma propriedade que deveria ter teste e não tem, o teste entra **e o
achado vai para §10** — porque uma spec de refatoração precisando escrever teste novo significa
que a spec de origem fechou com buraco, e isso é informação sobre o processo, não só sobre o
código.

**Total estimado:** 0 s, salvo o caso acima.

## 10. Descobertas

Preencher durante a implementação.

## 11. Definição de pronto

- [ ] As seis auditorias percorridas, item a item
- [ ] Wall-clock ≤ 200 s, medido e registrado no `test-timing.json`
- [ ] Suíte rodada em ordem invertida ao menos uma vez, resultado registrado
- [ ] Contagem de `noqa` comparada com a da 109
- [ ] Dívida encontrada resolvida ou registrada com spec-alvo
- [ ] Nenhum comportamento alterado; nenhum teste anterior editado
- [ ] `make test` verde
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 110 em ✅
- [ ] Commit `refactor(110): auditoria de orçamento e gates`

---

## Nota

Se as specs 102 e 103 tiverem sido usadas (o plano de corte da 101), elas entram nesta
auditoria junto com as demais. Se continuarem reservadas, a faixa é 101 + 104–109.
