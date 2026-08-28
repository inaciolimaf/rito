# Performance — linha de base

> Spec 098, regra 12. Este arquivo é versionado e ganha uma seção por medição. O que ele
> registra não é "o sistema está rápido", é **onde ele estava** em cada data — sem
> histórico, "ficou mais lento" é sempre uma discussão de memória contra memória.

## Como medir

```bash
make test-nightly    # semeia 1,95 milhão de linhas (§4), mede o p95 por tela e limpa
```

O gate que roda em **todo PR** é outro e é barato: orçamento de queries por endpoint
(`tests/integration/test_query_budget.py`) e os invariantes estruturais
(`tests/meta/test_performance_invariants.py`). Tempo não entra no PR de propósito —
máquina de CI compartilhada oscila 30% entre execuções e o gate viraria um gerador de
falso vermelho.

## Volume do perfilamento

| Entidade | Linhas |
|---|---:|
| Contatos | 100.000 |
| Processos | 100.000 |
| Tarefas | 500.000 |
| Lançamentos | 200.000 |
| Publicações | 50.000 |
| Movimentações | 1.000.000 |

Distribuído por 10 usuários e 20 etapas, com nomes variados. As três coisas importam: um
escritório com todas as linhas penduradas num usuário só, numa etapa só e com o mesmo
nome faz o planejador escolher planos que a produção nunca escolhe — e o perfilamento
passa a medir uma ficção. Descoberto medindo: a primeira versão do seed tinha as três
degenerações, e as três produziram números falsos.

## Orçamento de queries (gate de todo PR)

| Endpoint | Orçamento | Medido |
|---|---:|---:|
| Listagem de contatos | 3 | 3 |
| Listagem de processos | 3 | 3 |
| Listagem de tarefas | 3 | 2 |
| Listagem de lançamentos | 3 | 3 |
| Listagem de notificações | 3 | 3 |
| Detalhe de contato | 5 | 2 |
| Detalhe de processo | 5 | 3 |
| Dashboard de processos | 5 | 4 |
| Dashboard de contatos | 5 | 5 |
| Dashboard financeiro | 5 | 4 |
| Quadro do CRM | 5 | 4 |
| Timeline do processo | 3 | 3 |
| Busca global | 4 | 4 |

A contagem inclui a query de autenticação (toda rota autenticada carrega o usuário do
token) e exclui o `SELECT set_config('app.tenant_id')` do preâmbulo de RLS, que é
plumbing de sessão e não acesso a dado.

## Metas de p95 — medição de 2026-08-28

Host de perfilagem: container de 4 núcleos, Postgres 16 em Docker aninhado. **Não é
hardware de produção** — os números absolutos aqui são um piso pessimista, e o que
interessa neles é a comparação antes/depois e quais telas ainda não cabem.

| Tela | Meta | Antes da 098 | Depois |
|---|---:|---:|---:|
| Listagem de contatos | 300 ms | — | ✅ |
| Listagem de processos | 300 ms | 804 ms | ⚠️ 420 ms |
| Listagem de lançamentos | 300 ms | **14.276 ms** | ✅ |
| Busca global | 200 ms | 1.338 ms | ⚠️ 423 ms |
| Dashboard de processos | 500 ms | — | ✅ |
| Dashboard de contatos | 500 ms | — | ✅ |
| Quadro do CRM | 400 ms | 578 ms | ⚠️ 548 ms |

Cinco das oito metas passam. As três marcadas com ⚠️ melhoraram entre 2× e 34×, mas
ainda não cabem **neste host**. O gate noturno fica vermelho de propósito: é o sinal de
que sobrou trabalho, e apagá-lo mexendo na meta seria trocar o problema por uma mentira
mais confortável. O que resta nas três é o mesmo custo — ordenar ou agregar dezenas de
milhares de linhas para devolver vinte — e o próximo passo, quando houver hardware de
referência para decidir, é medir de novo antes de otimizar às cegas.

### Duas armadilhas de medição encontradas no caminho

- **"p95" de 20 amostras é o máximo.** Qualquer definição de percentil sobre 20 valores
  cai na penúltima amostra, e um pico isolado de GC ou checkpoint decide o resultado. A
  mesma rota media 379 ms de requisição real e 714 ms de "p95". São 100 amostras agora.
- **Apagar 1,95 milhão de linhas não devolve o espaço.** As tuplas mortas continuam
  ocupando páginas, e uma varredura sobre 20 mil linhas vivas passa a ler as páginas de
  100 mil: o teste de p95 da busca (spec 096) passou a falhar **depois** de o volume ser
  removido. `make test-nightly` semeia, mede, remove **e roda `VACUUM (ANALYZE)`**.

## O que a 098 encontrou e corrigiu

### 94 chaves estrangeiras sem índice, de 228

A auditoria do catálogo (`test_toda_fk_tem_indice`) achou 94. O Postgres cria índice
para a PK, nunca para a FK — e a conta chega em dois lugares:

- toda leitura pela relação vira Seq Scan;
- todo `DELETE` no lado pai varre a tabela filha **inteira, uma vez por linha apagada**,
  para checar integridade referencial. É o custo que ninguém liga à FK, e é o que
  transforma "excluir um cliente" em trinta segundos de banco travado.

Migration `098_fk_indexes`. O teste virou gate permanente.

### A listagem de lançamentos não paginava

`GET /api/v1/transactions` devolvia **todos** os lançamentos do escritório, cada um com
seis JOINs, e o `total` era o `len()` da lista. Com 200 mil lançamentos: **14,3 s**. O
`next_cursor` estava no schema desde a 056, sempre nulo — o contrato previa a paginação
que a implementação nunca entregou.

Corrigido com keyset em `(due_date, id)`. A contagem do filtro passou a viajar com os
somatórios do rodapé, que já varrem exatamente as mesmas linhas.

### JOIN diferido na listagem de processos

Escolher a página e resolver os rótulos na mesma query obriga o Postgres a materializar
o conjunto filtrado inteiro antes de ordenar: 100 mil linhas lidas para devolver 20,
**623 ms**. Separando em duas — a página só de `lawsuits` (o `ORDER BY created_at` com
`LIMIT` vira leitura de índice), depois os JOINs sobre as 20 escolhidas — a segunda query
caiu para **7,9 ms**.

### A busca de tarefas não tinha índice trigrama

`ILIKE '%termo%'` com curinga à esquerda anula qualquer B-tree; a única estrutura que o
serve é o GIN trigrama. Contatos e processos já tinham o seu desde a 096; tarefas, não.
**465 ms → 1,5 ms**. Migration `098b_posts_trgm`.

### Quatro queries que eram uma

- `_with_derived` do processo fazia quatro `session.get()` em sequência (tipo → grupo,
  etapa → fase) em toda rota que carrega um processo, inclusive na timeline, que não usa
  nenhum dos dois campos. Virou um JOIN.
- O dashboard de contatos fazia três `SELECT count(*)` sobre a mesma tabela, diferindo
  só no predicado. Virou um `count(*) FILTER`.
- A busca global fazia página + contagem por faceta, seis queries. Virou três, com
  `count(*) OVER ()`.
- A timeline fazia contagem + página. Virou uma.

### Cache de 5 minutos com invalidação por evento

`app/core/cache.py`, extraído do cache do dashboard de processos (028) — que era o único
do sistema. Aplicado ao dashboard de contatos e ao catálogo de tipos de tarefa (a
listagem sem filtro, que todo formulário carrega). TTL e evento juntos: o evento cobre o
caso comum, o TTL é o teto do erro quando algum caminho de escrita novo esquecer de
invalidar.

### Bundle inicial: 392 KB → 135 KB gzip

Era um chunk único de 1,34 MB. Cada página virou um chunk de rota (`React.lazy`), e o
editor de modelos (TipTap, 153 KB gzip) e os relatórios saíram do caminho crítico —
telas que a maioria das sessões nunca abre. A tela de login continua estática: é a
primeira coisa que todo mundo vê.

Gate: `npm run bundle:check` depois do build, no CI. A propriedade estrutural que
sustenta o número (nenhuma página de feature importada estaticamente pelo `App.tsx`) tem
teste na suíte de unidade.

### Virtualização acima de 100 linhas

`DataTable` renderiza só a janela visível mais overscan, com linhas-espaçador segurando
a altura total. Abaixo de 100 linhas o DOM inteiro cabe sem ninguém notar, e virtualizar
cobraria complexidade sem devolver nada.
