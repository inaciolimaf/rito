# 110 — 🔧 REFATORAÇÃO — Orçamento e gates

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** devolver o wall-clock para ≤ 200 s
**Depende de:** 101, 104–109 · **Status:** ✅ concluída

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

### O orçamento foi devolvido, e agora dá para saber quando ele não foi

Wall-clock de **138 s** contra o alvo de ≤ 200 s desta spec e os 300 s do `CLAUDE.md` §3.
`import app.main` em **2,2 s** (teto de 9 s), coleta do pytest em **1,57 s**, e o banco
template com **zero** linhas depois de várias execuções — a garantia da 105 se sustenta.

O item central, porém, não era o número: era a **confiabilidade** dele. A dívida 33
registrou a mesma árvore medindo 434 s e 140 s em execuções seguidas, por carga externa. Um
gate que varia 3× por causa de quem mais usa a máquina não separa «o projeto ficou lento»
de «o laptop estava ocupado» — e a primeira reprovação sem motivo real é a que faz alguém
aumentar o teto.

O `run-tests.sh` passou a registrar, sempre:

```
wall-clock: 138s (orçamento: 300s)
cpu das suítes: 396s | núcleos: 12 | carga: 0.98 -> 3.94
```

**396 s de CPU é a linha de base que faltava.** Numa reprovação futura, CPU perto disso com
wall-clock estourado significa máquina disputada; CPU também inflado significa que o
projeto engordou. E o próprio gate imprime essa leitura ao falhar, para quem for consertar
não precisar redescobri-la.

**A métrica do gate não mudou, e isso foi deliberado.** O `CLAUDE.md` §3 promete
*wall-clock*, que é o que o desenvolvedor de fato espera; trocá-la por tempo de CPU mudaria
a promessa da constituição, e isso não é decisão de uma spec de refatoração. Fica registrado
como escolha em aberto na dívida 33.

**Dois defeitos no próprio código de medição**, ambos achados só porque o número foi
conferido contra uma execução real em vez de aceito:

1. `cpu=$(times | ...)` devolvia **sempre zero**: a substituição de comando roda numa
   subshell, e ali o `times` reporta os filhos DELA, que não existem. Corrigido com
   redirecionamento, que acontece na shell atual.
2. Mesmo corrigido, continuava zero: em locale `pt_BR` o `times` imprime `0m0,195s`, e o
   `awk` lê `"0,195s"` como zero. Corrigido com `tr ',' '.'`.

Os dois teriam passado despercebidos para sempre — o gate seguiria verde, imprimindo um
`cpu=0s` que ninguém questionaria. É a lição 7 da leva outra vez: **verificação mecânica
prova o que ela mede, e o que ela mede também precisa ser conferido.**

### A dívida 35 tinha correção barata, e ela é o análogo exato da 105

A 105 deu a cada worker do xdist uma cópia própria do Postgres; o Redis continuou sendo
**um banco para todos**. E o que mora no Redis é justamente estado que atravessa
requisições: o token bucket do rate limit por host e o circuito do breaker — com chave por
HOST, não por tenant, então nem o RLS nem a transação por teste alcançam.

`_redis_url_do_worker` dá a cada worker um dos 16 bancos do Redis (`gw0` → 15, `gw1` → 14,
…), de trás para a frente para não esbarrar no 0. Acima de 16 workers ela **recusa com
mensagem**, em vez de voltar a compartilhar em silêncio, que é o modo de falhar que criou a
dívida.

Dois meta-testes travam o resultado, em `test_isolamento_transacional.py` — a casa da 105,
porque isto estende a garantia dela.

### A suíte inteira em ordem invertida: 1.603/1.603

Descoberta que deu valor ao exercício: **`pytest-randomly` não está instalado.** A ordem é
determinística — file order —, então a independência de ordem *nunca* tinha sido testada,
apesar de a suíte parecer embaralhada.

Rodei tudo invertido (plugin de uso único, processo único): **1.603 passaram, 197,5 s**.
Nenhuma dependência de ordem.

Isso também **refina a dívida 35**: ela é de **paralelismo**, não de ordem — o teste de
rate limit não falha por causa de quem rodou antes, mas por causa de quem roda ao mesmo
tempo, no mesmo Redis. As duas coisas se pareciam e não são a mesma.

### Zero asserções removidas pelas sete specs — verificado, não afirmado

O item «nenhum teste anterior foi editado» é o que separa refatoração de reescrita, e a
§6 manda conferir no `git log`. Conferido mecanicamente, contando linhas `-assert` no diff
de `backend/tests/` de cada uma das sete:

```
c56d952 (101): 0    2dbab3d (104): 0    4b9b223 (105): 0    c55a17a (106): 0
c1f473f (107): 0    2ca3c2d (108): 0    ab4827b (109): 0
```

**Zero em todas.** A 105 toca 26 arquivos de teste, mas só acrescenta marcadores
`@pytest.mark.commits` — nenhuma asserção existente foi tocada em nenhuma das sete.

### Zero código morto, e o primeiro resultado era falso

Varredura por AST das funções privadas nunca referenciadas em `app/` deu **19** — e as 19
eram falso positivo: validadores do Pydantic e handlers de sinal do Celery, chamados por
**decorador**, nunca pelo nome. Excluindo funções decoradas: **zero**. As extrações da 106
(~50 auxiliares) e da 109 não deixaram órfão nenhum.

Vale como aviso para a próxima auditoria: uma varredura de código morto que não entenda
decoradores acusa toda a camada de validação do projeto.

### Dois números desta spec estavam desatualizados

A 110 foi escrita antes de a 105 existir e antes de a fila ser reordenada, e dois itens do
checklist não batem com a realidade:

1. **§6: «`@pytest.mark.commits` em no máximo 4 arquivos».** A 105 fechou com teto de **19
   arquivos / 69 testes**, declarado e travado pelo próprio meta-test dela. Hoje são 19, no
   teto. O «4» era uma estimativa de antes da implementação.
2. **§3: «o total de `# noqa` não cresceu desde a 109».** Cresceu de 4 para **12** — mas
   todos os 8 novos vieram das specs 115 e 116, que rodaram DEPOIS da 109 e autorizaram
   cada um com teto próprio e justificativa obrigatória: `PLR0913` ×2 (teto 2), `S*` ×6
   (teto 6). Zero `C901`, contra teto 3.

Nenhum dos dois é problema; os dois são a spec de auditoria medindo contra um retrato que
envelheceu. Corrigir o checklist agora seria reescrever a pergunta depois de ver a
resposta — ficam registrados aqui, que é onde a §5 manda pôr divergência de inventário.

### As seis auditorias, item a item

**Gates (§3):** três `per-file-ignores`, todos com comentário justificando
(`alembic/versions` por causa do §9; `tests/`+`scripts/` porque `assert` é a interface do
pytest). Nenhum silencia gate em `app/`. 12 `# noqa`, todos com justificativa exigida por
meta-teste, todos dentro dos tetos. `make lint` roda no repositório inteiro.

**Orçamento (§4):** acima. `test-timing.json` com as sete medições.

**Coerência (§5):** os meta-testes com maior superfície usam AST (`test_camadas` 23,
`test_imports_pesados` 19, `test_final_audit` 12, `test_workers_finos` 11); os que usam
regex o fazem sobre texto (Dockerfile, prompts), não sobre código. Nenhum meta-teste é
cronometrado. `test_workers_finos` cita `app/workers/` mas **parseia com AST, nunca
importa** — a memória de projeto («worker abre um engine por tenant») está respeitada.

**Testes (§6):** ordem invertida verde; zero `sleep` de espera (os dois `asyncio.sleep`
encontrados são o *objeto* do teste — um nó que demora para estourar o timeout —, não
espera); rede bloqueada por `--disable-socket`; `commits` no teto.

**Dívida (§7):** duas resolvidas (35 inteira, 33 pela metade), duas registradas novas (36 e
37), zero `TODO`/`FIXME` órfão — os 9 encontrados por `grep` são a palavra portuguesa
«TODO» em prosa, e o meta-teste da 100 já exige a forma `# TODO`.

### O meta-teste me impediu de fechar a spec deixando três dívidas órfãs

Eu tinha percorrido as seis auditorias, resolvido a 35, atacado metade da 33 e ia commitar.
O `make test` reprovou:

```
DIVIDA-TECNICA.md fora da própria regra:
  item '28' aberto com spec-alvo 110, já ✅
  item '29' aberto com spec-alvo 110, já ✅
  item '31' aberto com spec-alvo 110, já ✅
```

**Três dívidas apontavam para esta spec e eu não tinha olhado nenhuma.** O
`test_toda_divida_aberta_tem_numero_e_alvo_no_futuro` (spec 100) existe exatamente para
isso: impedir que uma spec feche marcando ✅ enquanto o que estava marcado para ela vira
órfão. É a §7 desta spec — «percorrer as Descobertas, resolver o barato, registrar o
resto» — cobrada por um teste em vez de pela minha memória.

Foi o quarto meta-teste da leva a pegar um erro meu que eu não tinha visto, e o mais
constrangedor: ele pegou a spec de auditoria falhando na própria auditoria.

### Dívida 29: a trava que nunca protegeu nada, e por que passou cem specs

`pg_advisory_lock` é trava de **sessão** — vive enquanto a conexão viver. Quem a tomava era
`_psql`, que abre uma conexão e a **fecha no `finally`**. A trava morria no instante
seguinte; o `unlock` do fim rodava numa conexão nova, sem trava nenhuma, e o Postgres
respondia `false` com um aviso que ninguém lia.

Passou cem specs porque o caminho protegido **nunca é tomado no fluxo normal**: o
`run-tests.sh` migra o template antes do pytest, e quando os workers chegam ali
`_template_esta_pronto` já é `True` para todos. A trava quebrada só apareceria com template
novo — N workers entrando juntos, N `DROP`/`CREATE DATABASE`, N `alembic upgrade`
concorrentes, e a suíte caindo antes do primeiro teste.

Troquei o mecanismo por `flock`, e a troca foi medida, não preguiça: manter a trava do
Postgres exigiria que a checagem, o `DROP`/`CREATE` e o `alembic` rodassem no mesmo
`asyncio.run` da conexão que a detém, e os helpers do arquivo abrem cada um o seu —
aninhá-los é erro em tempo de execução. O limite do `flock` (duas máquinas contra o mesmo
Postgres não se veriam) está escrito na docstring, e não existe: o template é local por
definição.

**Verificado com o cenário que a dívida descreve:** `DROP DATABASE rito_test`, depois
`pytest -n 3`. Os três workers entraram juntos, o template foi reconstruído uma vez e
migrado até a head, 372/372 passaram. E a trava foi conferida bloqueando de fato — segundo
processo com `LOCK_NB` recebe `BlockingIOError`.

### Dívida 31: o levantamento que faltava dava zero

A dívida 31 dizia, textualmente, «escopo real, ainda não medido». Medido: dos cinco testes
que afirmam ordem entre linhas que eles mesmos criam, **um** estava quebrado (o que a 106
corrigiu), dois já escreviam `created_at` explicitamente, um é **imune por desenho** —
`test_ordenacao_estavel_com_mesmo_timestamp` injeta o timestamp e existe justamente para
afirmar o desempate — e um ordena por `id`, não por data. Cinco execuções seguidas dos
candidatos, verdes.

O risco do lado dos testes é **nulo hoje**. O que continua aberto é a causa raiz, e ela é
de produção: `func.now()` é o instante da transação, então importação em lote,
provisionamento e geração de parcelas criam linhas com `created_at` idêntico. Trocar por
`statement_timestamp()` pede migration — spec própria.

### O que ficou para depois, e por quê

- **Dívida 33, metade do `EntityPicker`:** as cinco jornadas e2e que caem sob carga são as
  cinco que usam o seletor assíncrono. O teto de espera próprio é mudança de e2e, não de
  gate — alvo 120.
- **Dívida 36 (`_compare` decide como `lte`):** corrigir muda comportamento, e a 110 é
  refatoração. Além disso a escolha entre `raise` e `False` é de produto.
- **Dívida 37 (identificadores em duas línguas):** ~50 renomeações sem ganho até que a
  decisão seja tomada, e a decisão é de quem lê o código todo dia — não minha.
- **Dívida 28 (`TemplateEditor.test.tsx` intermitente em host frio):** o conserto é
  reestruturar um teste de **front-end**, e esta spec é auditoria de orçamento e gates do
  back-end. Mexer no Vitest aqui seria escopo emprestado. Realvo para a 120.
- **Dívida 31, causa raiz:** `statement_timestamp()` no `server_default` muda produção e
  pede migration.

As três dívidas que apontavam para cá saíram desta spec com destino: **29 resolvida**, 28 e
31 realvadas com o motivo escrito. Nenhuma ficou órfã — que era exatamente o que o
meta-teste estava defendendo.

## 11. Definição de pronto

- [x] As seis auditorias percorridas, item a item — resultados na §10
- [x] Wall-clock **138 s** (alvo ≤ 200 s), registrado no `test-timing.json`, e agora
      acompanhado do tempo de CPU e da carga, que é o que faltava para interpretá-lo
- [x] Suíte rodada em ordem invertida: **1.603 passaram em 197,5 s**, processo único
- [x] Contagem de `noqa` comparada: 4 → 12, todos das specs 115/116, todos dentro dos
      tetos que elas mesmas declararam. Ver §10.
- [x] Dívida resolvida ou registrada: **29 e 35 resolvidas**, **33 resolvida pela
      metade**, **31 com o levantamento que faltava feito**, **36 e 37 registradas** —
      e as três que apontavam para esta spec (28, 29, 31) saíram com destino, não órfãs
- [x] Nenhum comportamento de `app/` alterado — as mudanças são em `tests/conftest.py` e
      `scripts/run-tests.sh`. Zero asserções removidas pelas sete specs, verificado no
      `git log`.
- [x] `make test` verde
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 110 em ✅
- [x] Commit `refactor(110): auditoria de orçamento e gates`

**Dois testes novos**, e a §9 previu o caso: a auditoria descobriu uma propriedade que devia
ter teste e não tinha — o isolamento de Redis entre workers. Pela regra da §9, isso é
informação sobre o processo: a **spec 105 fechou com buraco**, isolando o Postgres e
deixando o Redis de fora, e nada apontava para isso até a dívida 35 aparecer duas vezes.

---

## Nota

Se as specs 102 e 103 tiverem sido usadas (o plano de corte da 101), elas entram nesta
auditoria junto com as demais. Se continuarem reservadas, a faixa é 101 + 104–109.
