# 124 — Correção das dívidas abertas da série 101–123

**Fase:** 12 · **Tipo:** correção · **Orçamento:** +6 s
**Depende de:** 123 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar as **nove dívidas técnicas abertas** que a série 101–123 gerou ou herdou como
pendência ativa. Não é refatoração: sete das nove **mudam comportamento**, e é para isso que
existem.

> Esta spec MUDA comportamento de propósito. Testes anteriores que documentavam o defeito
> serão atualizados — e cada atualização dessas está listada nominalmente na §8.

## 2. As nove, e por que estas

| # | Dívida | Origem | Natureza |
|---|---|---|---|
| **34** | `/api/public/v1/customers/birthdays` devolve 1.000 contatos e ignora `month` | 116 | responde errado |
| **36** | `conditions._compare` decide como `lte` quando não reconhece o operador | 111 | decide errado em silêncio |
| **32** | Timestamp UTC comparado com data do escritório (3 pontos) | 114 | responde errado |
| **31** | `func.now()` é constante na transação; ordenação por data vira sorteio | 114 | gate que mente |
| **28** | `TemplateEditor.test.tsx` intermitente | 104 | gate que mente |
| **39** | Gate de bundle não roda em caminho com acento/espaço | 123 | gate que não roda |
| **40** | Oito auxiliares privados em português sobreviveram à 120 | 120 | inconsistência que se propaga |
| **15** | Enums do banco espelhados à mão em TS | 101 | duplicação sem alarme |
| **27** | Passo registrado some quando o timeout mata a sessão | 103 | meia-verdade no banco |

**Ficam de fora, e por quê:** as dívidas 3, 6, 7 e 8 estão marcadas *"Spec-alvo: nenhuma —
aceito"* (limites estruturais de cobertura, não pendências). As 18, 19, 25 e 26 nascem de
specs 008–050 e são **feature**, não correção: cálculo de prazo processual, PII em fixtures,
`last_assigned_at` calculado e tela de Atividades. Cada uma pede spec própria e escopo de
produto.

## 3. Escopo

**A. Dívida 34 — o filtro de aniversário.** `_filtro_de_aniversario` passa a receber escopo
**e mês explícito**. A rota pública passa o mês pedido. Duas rotas cobertas por teste que
cria aniversariante e não-aniversariante.

**B. Dívida 36 — o operador desconhecido.** O `return` final de `_compare` deixa de decidir
por `lte`.

**C. Dívida 32 — fuso nas comparações.** `created_at` convertido para o fuso da conta antes
de virar data, nos relatórios afetados. O CHECK `ck_tx_payment_not_future` entra na migration.

**D. Dívida 31 — a causa raiz.** `server_default` de `created_at`/`updated_at` passa de
`now()` para `statement_timestamp()`, com migration.

**E. Dívida 28 — o teste intermitente.** Corrigir a causa REAL, medida nesta spec (§9), não
a suposta pela dívida.

**F. Dívida 39 — o gate de bundle.** `fileURLToPath`, e varredura por `new URL(...).pathname`
no repositório inteiro.

**G. Dívida 40 — os oito nomes.** Renomear para inglês **mais o meta-teste** que a 120 não
escreveu: varre `app/` inteiro e reprova nome novo em português.

**H. Dívida 15 — os enums espelhados.** Gerador que escreve os unions TS a partir dos
`StrEnum` do Python, e meta-teste que reprova divergência.

**I. Dívida 27 — commit por passo.** `_record_step` deixa de escrever na transação de quem
chamou.

## 4. Fora de escopo

- As dívidas 3, 6, 7, 8, 18, 19, 25 e 26 (§2).
- Feature nova de qualquer espécie.
- Baixar teto de gate. Nenhum teto muda nesta spec.
- Reescrever o runtime de agentes além do necessário para a 27.

## 5. Modelo de dados / Contratos de API / Front-end

**Migration — uma só (§9 do CLAUDE.md), `124_relogio_e_fuso`:**
1. `server_default` de `created_at`/`updated_at` → `statement_timestamp()` (dívida 31).
2. `ck_tx_payment_not_future` (dívida 32, item 3).

**Contrato de API:** os 311 caminhos e 384 operações continuam os mesmos. O que muda é a
**resposta** de `/api/public/v1/customers/birthdays`, que hoje está errada — a rota existe,
o schema não muda, o conteúdo passa a ser o correto.

**Front-end:** os unions gerados (dívida 15) substituem os escritos à mão. Nenhum componente
muda.

## 6. Regras de negócio

1. `birthdays=month` sem `month` explícito usa o mês corrente do fuso do escritório; com
   `month=N`, usa `N`. `birthdays=day` ignora `month`.
2. Operador não reconhecido em `_compare` **não decide**: a condição não é satisfeita, e o
   fato é registrado em log. Escolhido por consistência — `evaluate` já trata condição
   inválida como `False`, e derrubar a automação puniria o escritório por um dado que ele não
   controla.
3. Relatório que filtra por data compara `created_at` **no fuso da conta**, não em UTC.
4. Nome de função privada em `app/` é inglês. O meta-teste passa a cobrar.
5. Union TS de enum de domínio é **gerado**, nunca escrito à mão.
6. Nenhum teste tem asserção enfraquecida. Onde um teste documentava o defeito, ele passa a
   afirmar o comportamento correto — e isso está listado na §8.

## 7. O que esta spec herda das anteriores

- **A dívida pode estar errada sobre a própria causa.** A 120 tentou a correção prescrita da
  28 e quebrou o teste. **Reproduzir antes de corrigir** não é conselho, é pré-requisito.
- **Verificação mecânica prova o que mede.** A da 120 provou que o mapa de renomeação foi
  aplicado certo, não que estava completo — é a dívida 40. Todo gate novo desta spec varre o
  universo, não a entrada.
- **Compactar não é extrair**, e o teto de 30 linhas da 123 continua valendo para todo código
  novo aqui.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | aniversariante do mês volta; não-aniversariante não (rota pública) | `test_public_api.py` | 1 s |
| integração | `month=N` devolve o mês pedido, não o corrente | `test_public_api.py` | 1 s |
| integração | tempo de processo nunca sai negativo (mesmo fuso nos dois lados) | `test_reports_tabular.py` | 1 s |
| unidade | operador desconhecido não satisfaz a condição | `test_automations_dispatch.py` | 0 s |
| integração | relatório inclui contato criado às 23:47 no fuso do escritório | `test_reports_tabular.py` | 1 s |
| integração | os 3 CHECK restantes barram escrita direta (era 4) | `test_transactions.py` | 0 s |
| integração | duas linhas criadas na mesma transação têm `created_at` distintos | `test_relogio_dos_carimbos.py` | 1 s |
| frontend | `TemplateEditor` — negrito, com espera pela condição real | `TemplateEditor.test.tsx` | 0 s |
| meta | nenhuma função privada de `app/` tem nome português | `test_nomes_em_ingles.py` | 0 s |
| meta | unions TS conferem com os `StrEnum` do Python | `test_enum_mirror.py` (já existia, spec 101) | 0 s |
| integração | passos anteriores sobrevivem ao timeout que mata a sessão | `test_ai_runtime_timeout.py` | 1 s |

**Testes atualizados (não enfraquecidos):** `test_reports_tabular.py` e `test_transactions.py`
hoje falam `_HOJE_UTC`/`datetime.now(UTC).date()` com comentário citando a dívida 32 — passam
a falar o fuso do escritório, que é o comportamento correto.

**Total estimado:** +6 s.

## 9. Descobertas

### Em três das nove, a dívida estava errada sobre si mesma

Esta é a descoberta que atravessa a spec. Uma dívida é escrita por quem viu o sintoma, muitas
vezes de passagem, no meio de outro trabalho — e o palpite de causa que ela registra envelhece
sem ninguém conferir.

| Dívida | O que ela dizia | O que era |
|---|---|---|
| **28** | teste lento em host frio; corrigir separando montagem de interação | corrida de POSIÇÃO DO CURSOR; a falha nem é o teto de 5 s, é o `waitFor` de 3 s |
| **15** | gerador de enums «continua pendente» | a spec 101 tinha entregado gerador, arquivo e alarme; a entrada ficou 23 specs desatualizada |
| **40** | oito auxiliares em português | eram **onze** — três só o gate novo achou, um deles criado pela própria spec 123 |

### Dívida 28: quatro correções plausíveis, todas piores

Reproduzido primeiro, como a própria entrada exigia: 1 falha em 8 execuções do arquivo
isolado. Depois, quatro tentativas — cada uma parecendo a certa:

| Tentativa | Resultado |
|---|---|
| `beforeAll` que aquece o editor | sem efeito: teste 1 continua ~306 ms, os outros ~45 ms |
| esperar `document.activeElement === .ProseMirror` | pior (8/10 falham): em jsdom isso NUNCA é verdade, e o `waitFor` só queimava 1 s |
| esperar a classe `ProseMirror-focused` | pior: a classe fica `true` e o teste falha assim mesmo |
| `skipClick` no `user.type` | 10 falhas em 10: sem o clique não entra tecla nenhuma |

O que resolveu foi **instrumentar**: imprimir o HTML final revelou `<p>!Olá</p>` — o "!"
entrando na posição 0. O `autofocus: "end"` é assíncrono e o clique na toolbar tira o foco do
contenteditable, cuja seleção o jsdom não restaura. A correção é seleção EXPLÍCITA (`Ctrl+A`,
tratado pelo keymap do ProseMirror, não por coordenada). **25 execuções verdes**, e a asserção
ficou mais forte: era `<strong>`, virou `<strong>Olá</strong>`.

Cinco minutos de instrumentação resolveram o que quatro correções plausíveis não resolveram.

### Dívida 40: o gate achou o que quem o escreveu não tinha achado

A varredura manual que abriu a dívida usou regex sobre nomes e achou oito. O meta-teste novo,
no primeiro minuto de vida, achou mais três — incluindo `build_payload`, que a spec 123 tinha
acabado de escrever em português por imitação do arquivo em volta.

É o argumento inteiro a favor de gates, num caso só: a diferença entre **verificar a entrada**
(a 120 provou que o mapa de renomeação foi aplicado certo) e **varrer o universo** (existe
alguma função de `app/` com nome português?). A 120 respondeu a primeira pergunta e a deu por
respondida; a segunda ficou três specs sem ser feita.

O gate decide por LISTA DE PALAVRAS, não por morfologia: uma heurística de terminação
(`-ao`, `-cao`) reprovaria `_relation`, `_action` e `_names`, e gate com falso positivo é gate
que as pessoas contornam.

### Dívida 34: dois defeitos empilhados, e o teste que faltava

O filtro só reconhecia `"day"` e `"month"`; a rota pública mandava `"month:<n>"`. Nenhuma
condição era aplicada e a rota respondia os primeiros 1.000 contatos do escritório. E mesmo
que o valor casasse, o filtro comparava com `today.month` — o parâmetro `month` era decorativo.

A correção separou o ESCOPO (`birthdays`) do PARÂMETRO (`birthday_month`) em dois campos
tipados: o valor que o schema não conseguia expressar deixou de existir. A spec 116 tinha
tornado o descasamento VISÍVEL no tipo; esta o eliminou.

**Por que passou tanto tempo:** a rota pública só tinha teste de CONTRATO — que confere que
ela existe e responde. Rota testada por existência é rota não testada. Os dois testes novos
criam um aniversariante e um não-aniversariante, e foram verificados reprovando contra o
código antigo.

### Dívida 36: o comentário já dizia a verdade que o código não fazia

O `evaluate` documentava que operador desconhecido «devolve False — condição inválida não roda
a ação». O `_compare` terminava em `return bool(esquerda <= direita)`. A prosa e o código
discordavam havia specs, e a prosa é que estava certa: a correção fez o código cumprir o que
já estava escrito.

Escolhido `False` e não `raise` por consistência com o resto do `evaluate` — e porque
automação que não roda aparece no histórico de execuções, enquanto automação que roda o ramo
errado não aparece em lugar nenhum.

De quebra, o teste de exaustividade parou de espelhar `{"gt","lt","gte","lte"}` à mão: agora
lê `_ORDER_BY_NAME` do código.

### Dívidas 31 e 32: a migration, e por que o CHECK saiu em vez de mudar

`now()` do Postgres é o instante de início da TRANSAÇÃO. Medido contra o banco real, do jeito
que a aplicação insere: duas linhas na mesma transação recebem `created_at` idêntico ao
microssegundo; com `statement_timestamp()`, diferentes. São 105 defaults em 39 arquivos, e a
migration os descobre do CATÁLOGO em vez de listá-los — uma lista literal envelheceria na
primeira tabela nova. Verificado: 87 colunas trocadas, zero `now()` restante, `downgrade`
simétrico.

O `ck_tx_payment_not_future` **saiu** em vez de ganhar fuso. O banco não tem como acertar
essa: `transactions.tenant_id` existe, mas o fuso mora em `accounts`, e um CHECK não consulta
outra tabela. Uma regra de banco que não consegue estar certa é pior que nenhuma — ela dá a
impressão de que alguém está conferindo. Quem valida é o service, que tem o fuso e é testado
(`test_pagamento_futuro_retorna_422`).

Os testes que documentavam o defeito passaram a afirmar o certo: `_HOJE_UTC` sumiu de
`test_reports_tabular.py`, e o teste dos CHECKs foi de 4 para 3 com a razão escrita.

### Dívida 27: a ordem valeu mais que a mudança

A primeira versão commitava passo e checkpoint numa sessão própria ANTES de tocar a sessão da
requisição — e com isso engolia o sinal de sessão morta de que o `_fail` depende para
registrar a falha fora de banda. O thread terminava `pending` em vez de `error`, e os testes
de timeout da spec 103 pegaram na hora.

O `flush` na sessão de quem chama vem primeiro: é ele que levanta quando a conexão morreu. E o
commit à parte escreve só as tabelas FILHAS — a linha de `ai_threads` continua com a sessão da
requisição, porque ela já está travada por essa transação e uma segunda conexão esperaria um
commit que não vem. Um deadlock trocado por uma meia-verdade não seria progresso.

### O verde falso do `tsc`, e a lição pela terceira vez na série

A troca dos 15 unions por re-export foi verificada com `npx tsc --noEmit` — que devolveu **0**.
O `make lint` seguinte acusou **13 arquivos com erro**: `export type { X } from "..."` reexporta
sem trazer o nome para o escopo do módulo, e todo uso local de `X` no próprio arquivo quebrou.

O `tsc --noEmit` sem `-p` lê o `tsconfig.json` da raiz, que neste projeto é *solution-style*:
só `references`, sem `include`. Ele checou **zero arquivos** e saiu com sucesso.

É a terceira vez na série que uma verificação mecânica reporta êxito sem medir nada — a 110
teve o contador de CPU que imprimia zero, a 120 teve dois harnesses que comparavam nenhum
arquivo, e agora esta. A regra prática que fica: **antes de acreditar num verde, confira que a
ferramenta viu arquivos.** `tsc -p tsconfig.app.json` acusa; `tsc` sozinho, não.

### O efeito colateral da 31: uma fila de sincronização que podia matar de fome

Corrigir a dívida 31 revelou um defeito de PRODUÇÃO que ela escondia.

`list_due_for_datajud_sync` ordena por `datajud_last_sync_at ASC NULLS FIRST` e aplica
`LIMIT`. Todo processo que nunca sincronizou tem esse campo `NULL` — então, na prática, o
`ORDER BY` empatava para a fila inteira, e **um `ORDER BY` que empata sob `LIMIT` não é uma
fila**: o Postgres pode devolver quaisquer `limit` linhas entre as empatadas, e as mesmas de
novo na volta seguinte. Com mais processos que o lote, um processo podia nunca ser escolhido.
Fome, não lentidão — e silenciosa.

Isso estava lá antes da 124. O que a 124 fez foi tirar a sorte que o escondia: enquanto
`created_at` vinha de `now()` e empatava dentro da transação, a ordem era a física do heap, e
um teste de sincronização (`test_datajud_ganha_historico_de_execucao_sucesso_e_erro`) passava
por acaso. Com `statement_timestamp()` o acaso mudou de lado e o teste passou a reprovar —
determinístico, cinco em cinco.

A correção é o desempate que faltava: `created_at ASC` (o mais antigo primeiro, que é a
política justa de uma fila) e `id` para fechar a ordem total.

**A lição é a mesma da dívida 31, um nível acima:** empate em `ORDER BY` não é detalhe de
teste. Onde há `LIMIT`, ele é a diferença entre uma fila e um sorteio — e o teste que
reprovou era o único aviso de que existia um sorteio em produção.

### Dívida 39: um gate que nunca tinha rodado

`URL.pathname` devolve o caminho percent-encoded. Em `/home/.../Área de trabalho/...` o gate
de bundle estourava `ENOENT` com o `dist` construído ao lado; no CI passava porque lá o
caminho é `/home/runner/work`. Corrigido com `fileURLToPath`, ele rodou pela primeira vez
nesta máquina: **135,2 KB** de bundle inicial contra o teto de 300 KB.

Varredura no repositório: era a única ocorrência do padrão em código nosso — `check-duplication.mjs`
e o e2e já usavam `fileURLToPath`.

## 10. Definição de pronto

- [x] As nove dívidas marcadas `~~título~~ — RESOLVIDO na spec 124` no TÍTULO
- [x] Uma única migration, aplicada e revertida com sucesso
- [x] Nenhuma asserção enfraquecida; as atualizadas listadas na §8 e justificadas na §9
- [x] Contrato inalterado: 311 caminhos, 384 operações, 276 com params
- [x] Um meta-teste NOVO (`test_nomes_em_ingles.py`), provado mordendo de duas formas —
      função com nome português reprova, e esvaziar a lista de palavras reprova. O de
      enums (`test_enum_mirror.py`) já existia desde a 101; a §9 explica o engano da
      dívida 15 sobre isso.
- [x] `make test` verde dentro do orçamento
- [x] `make lint` verde
- [x] `ROADMAP.md` com a linha da 124 em ✅
- [x] Commit `fix(124): correção das dívidas abertas da série 101–123`
