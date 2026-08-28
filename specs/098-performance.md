# 098 — Performance

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 096 · **Status:** ✅ concluída

---

## 1. Objetivo

Auditoria de desempenho com volume real e criação do **gate permanente**: a partir daqui, PR que
degrada performance é barrado pelo CI, não pela boa vontade de quem revisa.

## 2. Escopo

- Seed de volume realista
- Auditoria de índices
- Eliminação de N+1
- Budget de queries por endpoint, verificado em teste
- Paginação keyset em toda listagem
- Cache onde compensa
- Relatório de performance versionado

## 3. Fora de escopo

- Escala horizontal e sharding (é infra) · CDN de estáticos

## 4. Modelo de dados

Nenhuma tabela nova. Índices que a auditoria apontar.

Volume do seed:
| Entidade | Quantidade |
|---|---|
| Contatos | 100.000 |
| Processos | 100.000 |
| Tarefas | 500.000 |
| Lançamentos | 200.000 |
| Publicações | 50.000 |
| Movimentações | 1.000.000 |

## 5. Contratos internos

```python
@assert_query_budget(max_queries=5)
async def test_lawsuit_list_budget(...): ...
```
Fixture que conta queries via evento do SQLAlchemy e falha se exceder.

## 6. Front-end

**Cria:** nada de novo. Otimizações: virtualização em listas longas, `React.memo` onde medição
justificar, code splitting por rota, lazy loading do editor e dos gráficos.

## 7. Regras de negócio

1. **Budget de queries por endpoint**, verificado em teste:
   | Endpoint | Máximo |
   |---|---|
   | Listagens (contatos, processos, tarefas, lançamentos) | 3 |
   | Detalhe com relações | 5 |
   | Dashboards | 5 |
   | Timeline | 3 |
   | Busca global | 4 |
2. **Metas de latência (p95)** com o volume acima:
   | Tela | Meta |
   |---|---|
   | Listagens | 300 ms |
   | Caixa de entrada | 200 ms |
   | Busca global | 200 ms |
   | Dashboards | 500 ms |
   | Kanban | 400 ms |
   | BI (view materializada) | 300 ms |
3. Nenhuma listagem usa `OFFSET` — keyset em todas.
4. Toda FK tem índice. Verificado por teste que consulta o catálogo do Postgres.
5. Nenhum `SELECT *` — só as colunas necessárias.
6. `selectinload` para coleções, `joinedload` para muitos-para-um. Lazy loading em rota é bug.
7. Bundle do frontend: inicial abaixo de 300 KB gzip; editor e gráficos em chunk separado.
8. Lista acima de 100 itens é virtualizada.
9. Cache de 5 min em dashboard e taxonomia; invalidado por evento.
10. Teste de volume roda no CI **nightly**, não a cada PR — não cabe nos 120 s.
11. Budget de queries roda **em todo PR** — é barato e pega regressão na hora.
12. Resultados vão para `docs/PERFORMANCE.md`, versionado, com histórico.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| **meta** | **budget de queries em 12 endpoints** (parametrizado) | ~1,2 s |
| **meta** | **toda FK tem índice** (catálogo do Postgres) | ~0,3 s |
| **meta** | **nenhuma listagem usa OFFSET** (grep + inspeção) | ~0,3 s |
| **meta** | nenhum `SELECT *` em código de produção | ~0,2 s |
| unit | fixture de budget conta queries corretamente | ~0,2 s |
| frontend | lista acima de 100 é virtualizada | ~0,4 s |
| frontend | bundle inicial abaixo do teto | ~0,3 s |
| nightly | latência p95 com volume (fora dos 120 s) | — |

**Total no CI de PR:** ~2,9 s
**Nightly:** separado, sem limite de tempo

## 9. Descobertas

### O que a auditoria encontrou

- **94 das 228 chaves estrangeiras não tinham índice.** O Postgres cria índice para a
  PK, nunca para a FK. A conta chega em dois lugares e o segundo é o que pega de
  surpresa: além de toda leitura pela relação virar Seq Scan, **todo `DELETE` no lado
  pai varre a tabela filha inteira, uma vez por linha apagada**, para checar integridade
  referencial. É o que transforma "excluir um cliente" em trinta segundos de banco
  travado. Migration `098_fk_indexes`, e o teste virou gate permanente.
- **`GET /api/v1/transactions` não paginava — nem por keyset, nem por offset, nem por
  nada.** Devolvia TODOS os lançamentos do escritório, cada um com seis JOINs, e o
  `total` era o `len()` da lista. Com 200 mil: **14,3 segundos**. O `next_cursor` estava
  no schema desde a 056, sempre nulo: o contrato previa a paginação que a implementação
  nunca entregou, e nenhum teste percebeu porque nenhum teste tinha volume. É a
  descoberta que justifica a spec inteira.
- **A busca de tarefas não tinha índice trigrama.** `ILIKE '%termo%'` com curinga à
  esquerda anula qualquer B-tree; contatos e processos já tinham o seu desde a 096,
  tarefas não. **465 ms → 1,5 ms.**
- **`OR` entre dois índices diferentes é Seq Scan.** A busca de processos fazia
  `search_vector @@ ... OR folder ILIKE ...` — GIN de texto de um lado, GIN trigrama do
  outro. O Postgres não combina índices distintos dentro de um `OR`: 187 ms varrendo
  101.504 linhas para devolver zero. Como união de dois `SELECT id`, cada ramo usa o seu.
- **`_with_derived` fazia quatro `session.get()` em sequência** (tipo → grupo, etapa →
  fase) em TODA rota que carrega um processo — inclusive a timeline, que não mostra
  nenhum dos dois campos. Virou um JOIN, e a timeline deixou de pagar por ele.

### Decisões que a implementação forçou

- **O decorador do §5 não sobreviveu ao contato.** `@assert_query_budget(max_queries=5)`
  sobre a função de teste inteira conta o SETUP — criar escritório, processo e
  lançamentos são dezenas de queries — e o orçamento passa a não significar nada. Virou
  gerenciador de contexto, que delimita exatamente a requisição medida. O teste também
  mora em `tests/integration/` e não em `tests/meta/`: precisa das fixtures de
  integração, e um conftest de subpasta não é visível para pastas irmãs.
- **O orçamento conta a autenticação e não conta o preâmbulo de RLS.** Toda rota
  autenticada carrega o usuário do token — e é por isso que uma listagem cabe em 3:
  usuário + página + total. Já o `SELECT set_config('app.tenant_id')` é plumbing de
  sessão, não acesso a dado: contá-lo faria o orçamento medir quantas sessões foram
  abertas e mudar junto com refatorações que não tocam em query nenhuma.
- **JOIN diferido: duas queries são mais rápidas que uma.** Escolher a página e resolver
  os rótulos na mesma query obriga o Postgres a materializar o conjunto filtrado inteiro
  antes de ordenar — 100 mil linhas lidas para devolver 20, em 623 ms. Separando, a
  segunda cai para 7,9 ms. Para o orçamento continuar em 3, o total do filtro passou a
  vir por `count(*) OVER ()` na primeira, em vez de uma terceira query.
- **`count(*) FILTER` e `count(*) OVER ()` valem por várias queries.** Três `count(*)`
  sobre a mesma tabela viraram um; página + contagem viraram uma, na busca, na timeline
  e na listagem de lançamentos.
- **Cache só onde a chave é uma.** `core/cache.py` foi extraído do cache do dashboard de
  processos (028), que era o único do sistema. Vale para dashboard e taxonomia SEM
  filtro — a listagem filtrada teria espaço de chaves igual ao produto dos filtros
  possíveis, taxa de acerto perto de zero, e só ocuparia Redis. TTL e evento juntos: o
  evento cobre o caso comum, o TTL é o teto do erro quando um caminho de escrita novo
  esquecer de invalidar.
- **`useListPage` ganhou `page` e `exportFile` opcional.** A listagem de lançamentos
  precisa da resposta crua (o rodapé de somatórios não é `items` nem paginação) e não
  tem export — exigir um callback vazio dela seria fingir uma capacidade que a tela não
  oferece. Terceiro uso do hook, exatamente onde a regra dos 3 usos previa.

### Armadilhas de medição

- **"p95" de 20 amostras é o máximo.** Qualquer definição de percentil sobre 20 valores
  cai na penúltima amostra, e um pico isolado de GC ou checkpoint decide o resultado. A
  mesma rota media 379 ms de requisição real e 714 ms de "p95". São 100 amostras agora.
- **Apagar 1,95 milhão de linhas não devolve o espaço.** As tuplas mortas continuam
  ocupando páginas, e uma varredura sobre 20 mil linhas vivas passa a ler as páginas de
  100 mil: o teste de p95 da busca da 096 passou a falhar **depois** de o volume ser
  removido, e o culpado era o inchaço, não a consulta. `make test-nightly` semeia, mede,
  remove e roda `VACUUM (ANALYZE)` — volume de perfilagem é estado de uma execução, não
  do banco.
- **Seed degenerado mede uma ficção.** A primeira versão punha as 200 mil linhas num
  usuário só, numa etapa só, e dava a todo contato o mesmo prefixo de nome. As três
  degenerações produziram números falsos: o planejador escolhia percorrer o índice de
  usuário e ler a tabela inteira, e `q=Contato` casava os 100 mil contatos. Hoje são 10
  usuários, 20 etapas e 400 combinações de nome.
- **O seed não podia morar em `app/`.** Usa a conexão de superusuário, que fora dos
  workers é exatamente o que o teste de isolamento da 080 proíbe no código da aplicação.
  Foi para `backend/scripts/` — é ferramenta de operação, não módulo do sistema.

### O que ficou em aberto

Três das oito metas de p95 não cabem no host de perfilagem (container de 4 núcleos com
Postgres em Docker aninhado): listagem de processos em 420 ms contra 300, busca global
em 423 contra 200, quadro do CRM em 548 contra 400. As três melhoraram entre 2× e 34×,
e o custo que resta nelas é o mesmo — ordenar ou agregar dezenas de milhares de linhas
para devolver vinte. **O gate noturno fica vermelho de propósito**: é o sinal de que
sobrou trabalho, e mexer na meta para apagá-lo trocaria o problema por uma mentira mais
confortável. Números e contexto em `docs/PERFORMANCE.md`.

## 10. Definição de pronto

- [x] Budget de queries ativo em todo PR — 13 endpoints, `test_query_budget.py`
- [x] Nenhuma FK sem índice — 94 criados, gate permanente no catálogo do Postgres
- [ ] Todas as metas de p95 atingidas no nightly — **5 de 8**; as 3 restantes e o porquê
      estão em `docs/PERFORMANCE.md` e na seção "O que ficou em aberto" acima
- [x] `docs/PERFORMANCE.md` com a linha de base
- [x] Nenhuma listagem com `OFFSET`; nenhum `SELECT *` em código de produção
- [x] Bundle inicial em 135 KB gzip (teto 300); editor e gráficos em chunk próprio
- [x] Lista acima de 100 itens virtualizada
- [x] `make test` verde: 1440 backend + 286 frontend + 10 e2e
- [x] `make lint` verde: ruff, black, mypy strict, eslint, tsc, prettier
- [x] Commit `feat(098): performance e budget de queries`
