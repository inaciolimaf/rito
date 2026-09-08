# 131 — O gate de dívida que só via um quarto do registro

**Fase:** 12 · **Tipo:** correção · **Orçamento:** +0 s
**Depende de:** 100, 101, 124 · **Status:** ✅ concluída

---

## 1. Objetivo

`test_toda_divida_aberta_tem_numero_e_alvo_no_futuro` existe desde a spec 101 para impedir
que uma dívida ABERTA aponte para uma spec já entregue. Medido contra o arquivo real, ele
enxergava **1 das 4** dívidas abertas. Esta spec faz o gate ler o alvo **efetivo** em todas
as formas que o registro usa, faz o helper de "item resolvido" reconhecer as quatro formas
de fechamento em uso, e transforma em gate a recomendação que a nota de método da 124
deixou em prosa.

Correção: muda o que os gates ENXERGAM, não o que o produto faz. Nenhum código de `app/` é
tocado.

## 2. Por que um gate verde não provava nada

O helper lia o alvo assim:

```python
re.findall(r"\*\*Spec-alvo:\*\*\s*(\d{3})", bloco)
```

O `\s*` exige o número **colado** no marcador. Medido no `docs/DIVIDA-TECNICA.md` antes
desta spec:

| Item aberto | O que a regex via | O que a linha diz |
|---|---|---|
| 18 | `['126']` | `**Spec-alvo:** 126 (prazo processual…)` |
| 25 | `[]` | `**Spec-alvo:** ~~123~~ → **125**` |
| 26 | `[]` | `**Spec-alvo:** ~~124~~ → **125**` |
| 7 | `[]` | `**Spec-alvo:** reavaliar na 020 ou quando…` |
| 41 | `[]` | `**Spec-alvo:** spec própria de correção…` |

As duas invisíveis por causa do tachado — 25 e 26 — são exatamente as que **foram
re-atribuídas duas vezes cada, por este mesmo acidente**: a 122, a 123 e a spec que nasceu
125 e virou 127 tomaram números que uma dívida já reservava. O gate escrito para avisar
disso ficava cego justamente no estado que mais precisa de vigilância — o de um alvo que
já mudou de dono uma vez.

A dívida 41 (`spec própria`) não tem número e está certa assim; a dívida 7 (`reavaliar na
020`) tem um número, ele venceu há mais de cem specs, e ninguém foi avisado.

**A lição é a da dívida 40**, registrada no próprio arquivo: *verificação mecânica prova o
que ela mede, e o que ela mede precisa ser conferido contra o universo, não contra a
própria entrada*. A pergunta que faltava não era "o gate passou?", era "o gate LEU todas as
linhas de alvo do arquivo?". Não ter achado nada e não haver nada a achar eram
indistinguíveis — e é por isso que a leitura de hoje **reprova a forma que não souber ler**
em vez de devolver silêncio.

O segundo helper tinha o mesmo formato de falha. `_e_item_resolvido` testava
`"RESOLVIDO" in cabecalho or cabecalho.startswith("~~")`, e nenhum título começa com `~~` —
todos começam com `## <n>. `. Metade dos itens fechados continuava sendo tratada como
aberta:

| Item | Como fechou | Por que escapava |
|---|---|---|
| 4, 5 | `~~título~~ — RECLASSIFICADO … na spec 100` | palavra diferente, tachado no meio |
| 16 | `~~título~~ — FECHADA na spec 101` | idem |
| 19 | `### ✅ RESOLVIDO na spec 100`, no corpo | o título nunca foi atualizado |

Um item fechado lido como aberto é um falso positivo esperando a hora — e falso positivo
ensina a ignorar a saída do gate, que é como um gate morre sem que ninguém o apague.

## 3. Escopo

**A. Leitura do alvo efetivo** (`_LINHA_DE_ALVO`, `_REATRIBUICAO`, `_ALVO_COM_NUMERO`,
`_ALVO_SEM_NUMERO`, `_ler_alvo`, `_alvos_do_bloco`). As formas do arquivo, levantadas lendo
as 28 linhas de alvo que existem nele: `NNN`, `~~AAA~~ → **NNN**` (em laço — nada impede a
terceira re-atribuição), `reavaliar na NNN`, `nenhuma — …`, `spec própria …`, `própria, a
definir`, `alguma spec …`, `a spec que …`, `a próxima spec …`, mais as duas grafias
históricas `**Spec-alvo original:**` e `**Spec-alvo (original):**`.

**B. As grafias com "original" são história, não alvo.** Elas guardam o alvo de antes de
uma re-atribuição, quase sempre de spec já entregue. Lê-las como alvo corrente
transformaria todo item fechado em falso positivo; ignorá-las sempre deixaria passar o item
aberto cujo único alvo é o original vencido. Valem como **fallback**: só quando o item não
declara alvo corrente nenhum.

**C. Forma desconhecida reprova.** A lista de alvos textuais é fechada de propósito. Forma
nova falha o gate até alguém classificá-la — o oposto do que a regex anterior fazia, que
era ignorar em silêncio.

**D. `_e_item_resolvido` reconhece as quatro formas de fechamento**: tachado em qualquer
posição do título (não só no começo), as palavras `RESOLVIDO`/`RECLASSIFICADO`/`FECHADA`/
`REMOVIDO`, e o `### ✅ RESOLVIDO` no corpo. Passa a receber o **bloco** inteiro, porque
uma das formas mora no corpo, e o título é o primeiro **parágrafo** — o item 1 tem título
quebrado em duas linhas, com o `~~` de fechamento na segunda.

**E. Gate novo: `test_nenhuma_spec_ocupa_numero_que_uma_divida_aberta_reserva`.** O §4
abaixo.

**F. Os dois gates provados mordendo**, com casos plantados e com os dois lados: o que deve
reprovar e o que não pode reprovar.

**G. Higiene do registro** (`docs/DIVIDA-TECNICA.md`): título do item 19 marcado como
resolvido desde a 100 (o corpo já dizia), dívida 7 re-atribuída de `020` para **132**, e a
nota de método com a lista de números reservados no estado real.

## 4. A recomendação da 124, virada gate

A "Nota de método: número de spec é recurso reservado" manda rodar

```bash
grep -n "Spec-alvo:.*\bNNN\b" docs/DIVIDA-TECNICA.md   # antes de criar specs/NNN-*.md
```

ao **ABRIR** a spec, que é o único momento em que renumerar é de graça. Recomendação
depende de alguém lembrar, e ninguém lembrou três vezes seguidas.

O gate novo faz o cruzamento sozinho: para cada número que uma dívida **aberta** reserva,
se existe `specs/NNN-*.md`, o arquivo da spec precisa **citar a dívida** que está
consumindo. Quem escreve a 126 para calcular prazo processual escreve "dívida 18" e passa;
quem escolheu o 126 por ser o próximo livre não escreve, e descobre no primeiro `make test`
do ciclo.

A saída legítima é a citação, **não** uma lista de exceções por arquivo — gate que aceita
exceção por arquivo deixa de morder, que é o alerta que a própria spec 110 registra.

**O que ele não faz, e é honesto dizer:** conferir que a spec resolve a dívida citada. Isso
é revisão humana. O gate impede a colisão *silenciosa*, que é a parte que apodrece sozinha
porque ninguém a percebe até o trabalho estar feito no número errado. Marcar a dívida como
resolvida continua manual, e continua cobrado pelo gate irmão.

E não cobra que a dívida seja resolvida **no** número que ela reservou. As dívidas 25 e 26
reservam o 125 e estão sendo resolvidas na 128 neste mesmo ciclo — o que é legítimo: a
reserva existe para impedir que **outro** trabalho tome o número, não para prometer que ele
será usado. Cobrar isso transformaria toda mudança de plano em vermelho, que é a receita
para o gate ser desligado.

## 5. Modelo de dados

Nenhuma migration. A spec não toca em schema.

## 6. Contratos de API

Inalterados.

## 7. Front-end

Nada.

## 8. Regras

1. O alvo de uma dívida é o que vem **depois da última seta de re-atribuição**; o tachado é
   história e não conta.
2. Só o **começo** da linha de alvo é alvo. O item 18 cita a 122 e a 123 na própria linha,
   ao contar a história das re-atribuições — um `findall` sobre a linha inteira acharia três
   alvos onde há um.
3. Alvo textual (`nenhuma`, `spec própria`, `a spec que trouxer e-mail`) é legítimo e não
   reprova: dívida sem número reservado é decisão registrada, não esquecimento.
4. Forma de alvo que o gate não sabe classificar **reprova**.
5. `**Spec-alvo original:**` só vale como alvo quando não há alvo corrente no item.
6. Item fechado por qualquer das quatro formas em uso não é cobrado por alvo.
7. Spec cujo número uma dívida aberta reserva precisa citar a dívida, ou renumerar.

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | alvo re-atribuído para spec entregue reprova (plantado) | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | forma de alvo desconhecida reprova (plantado) | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | alvo textual **não** reprova (plantado) | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | item fechado por `RECLASSIFICADO` **não** reprova (plantado) | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | item fechado só no corpo **não** reprova (plantado) | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | toda linha de alvo do arquivo real é classificável | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | spec sobre número reservado que não cita a dívida reprova | `tests/meta/test_final_audit.py` | ~0,01 s |

**Total estimado:** +0 s (37 testes do arquivo em 2,6 s)
**Fixtures externas:** nenhuma. Os dois gates leem arquivo do repositório.

## 10. Descobertas

- **O gate mordeu na hora em que foi consertado.** Com a leitura corrigida, a dívida 7
  ("reavaliar na 020") reprovou de imediato — e reprovou **com razão**: o alvo tinha vencido
  cem specs antes e o gate nunca tinha conseguido lê-lo. Re-atribuída à **132**, que é a
  spec de teste de mutação. É a melhor prova de que o conserto valia: o primeiro achado veio
  do arquivo real, não de um caso plantado.
- **A demonstração dos dois gates mordendo foi feita no arquivo real**, com o caso plantado
  e revertido: a dívida 25 apontada para a 124 (✅) reprova o gate de alvo; a dívida 18
  apontada para o 129 (número já ocupado por `specs/129-*.md`, que não cita a dívida 18)
  reprova o gate de reserva. Os dois voltam a passar com o arquivo intacto.
- **Reconhecer item fechado mudou o resultado do outro gate.** Os itens 16, 17 e 20 guardam
  só `**Spec-alvo original:** NNN`, com NNN já entregue. Sem a regra de fechamento por
  `FECHADA`/`RECLASSIFICADO`/corpo, o fallback para o alvo histórico os transformaria em
  falso positivo. Os dois consertos precisavam vir juntos: o helper de leitura sozinho teria
  deixado o gate vermelho por um motivo errado.
- **O item 19 estava fechado no corpo e aberto no título há 31 itens.** É a mesma família da
  lição do item 15 ("dívida fechada por uma spec que não a citava fica aberta para sempre no
  papel"), num nível mais discreto: aqui a spec citou a dívida, e só metade do registro foi
  atualizada.
- **`test_registro_de_gates.py` conta arquivo, não função.** Os gates novos moram num
  arquivo que já tem linha em `docs/GATES.md`, então o inventário continua íntegro — mas a
  linha do `test_final_audit.py` descreve o que ele cobre, e essa descrição ficou incompleta.
  Ver o §11.

## 11. Fora de escopo, e vinculante

- **Marcar como resolvidas as dívidas 18, 25, 26 e 41.** Estão sendo trabalhadas em specs
  paralelas; quem as fechar marca.
- **`docs/GATES.md` e `ROADMAP.md`** não foram editados (arquivos de outra frente neste
  ciclo). A linha do `test_final_audit.py` no registro de gates ganha, na integração, a
  menção ao gate de número reservado.
- **O `CLAUDE.md` §8** continua recomendando o `grep`. A recomendação não some porque virou
  gate: ela é o que faz alguém escolher o número certo antes de o gate precisar avisar.

## 12. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras com teste
- [x] Nenhuma tabela nova (nada de RLS a testar)
- [x] Os dois gates provados **mordendo**, com os dois lados (reprova / não reprova)
- [x] `tests/meta/test_final_audit.py` verde (37 testes, 2,6 s)
- [x] `ruff`, `black` e `mypy --strict` verdes no arquivo tocado
- [x] Sem `Any`, `# type: ignore` ou `# noqa`
- [x] `ROADMAP.md` — texto entregue para a integração (§11)
- [x] Commit `fix(131): o gate de dívida que só via um quarto do registro`
