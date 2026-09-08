# 137 — Os tetos que faltavam, os índices que o RLS desligava e o expurgo que sobrou

**Fase:** 14 · **Tipo:** correção · **Orçamento:** +3 s no wall-clock
**Depende de:** 019, 037, 045, 051, 078, 093, 098, 101 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar os dez defeitos de desempenho e integridade que a auditoria mediu com 100 mil
contatos, 200 mil lançamentos e 200 mil tarefas. Nenhum deles é uma tela nova: são
consultas sem teto de linhas, índices que existiam e nunca eram usados, contadores
cacheados que mentiam e tabelas de log que só crescem. Nada aqui muda o que o usuário vê,
exceto onde a resposta estava **errada** — e aí muda de propósito.

## 2. O que a auditoria não sabia, e mudou a spec inteira

O defeito 4 dizia: o `WHERE` da busca de contatos usa `unaccent(lower(name))`, o índice é
sobre `immutable_unaccent(lower(name))`, e o planner não casa os dois. Está certo, e a
troca está feita. Mas **trocar a função não bastava**, e a medição foi feita de novo, com
o papel de aplicação (`rito_app`), que é como a produção roda:

| predicado | papel | plano | tempo |
|---|---|---|---|
| `unaccent(lower(name)) ILIKE …` | `rito_app` (RLS ligado) | Parallel Seq Scan | 110 ms |
| `immutable_unaccent(lower(name)) ILIKE …` | `rito_app` (RLS ligado) | **Parallel Seq Scan** | 139 ms |
| `immutable_unaccent(lower(name)) ILIKE …` | `rito` (superusuário, RLS não se aplica) | Bitmap Index Scan | 3,2 ms |

A terceira linha é o diagnóstico. Sob Row Level Security, um predicado só vira **condição
de índice** se for `LEAKPROOF` — senão ele seria avaliado antes da política de tenant,
sobre linhas de outros escritórios, e um erro ou um tempo dependente do dado vazaria o que
a política existe para esconder. O Postgres implementa isso literalmente
(`restriction_is_securely_promotable`): a política tem nível de segurança 0, o filtro do
usuário tem nível 1, e nível 1 só é promovido se for leakproof.

Nenhuma peça do predicado era leakproof: nem o operador `~~*`, nem `lower()`, nem
`immutable_unaccent()`. **Os seis índices `gin_trgm_ops` do schema estavam mortos desde o
dia em que foram criados** — contatos (017), pasta do processo (029), comentário e local
da tarefa (098b), cidade e tribunal (018/021). Nenhum erro, nenhum aviso: só plano ruim.

Isso decide duas coisas desta spec. A primeira é que o defeito 8 (índice trigram novo em
`transactions.description`) seria um índice natimorto sem resolver isto antes. A segunda é
que a correção passa por marcar funções como `LEAKPROOF`, o que é uma decisão de
segurança, não de desempenho — e por isso ela está escrita na regra 3 abaixo, com o que
foi e o que não foi tocado.

## 3. Escopo

**A. Tetos de linhas.** Expurgo de webhooks sem lista de ids (defeito 1); agenda e feed
iCal com teto (2 e 3); candidatos de casamento de publicação com `LIMIT 2` (5).

**B. Índices e o que os torna alcançáveis.** `texticlike` e `immutable_unaccent`
`LEAKPROOF`; `ix_customers_name_trgm` recriado sem `lower()`; índices novos para o filtro
do financeiro, para a agenda, para a listagem de notificações e para o expurgo de webhooks
(4, 8, 3, 10).

**C. Cache que mentia.** `crm:board_counts` e a metade de `customers:stats` que dependia
de escrita de processo (6 e 7).

**D. Expurgo.** Cinco tabelas de log ganham horizonte declarado (10).

**E. Trava de sobreposição** da varredura de agregados (11).

## 4. Fora de escopo

- **A ordenação de `GET /api/v1/posts` (defeito 9).** O índice foi construído e medido:
  ele é usado, e a página fica **mais lenta** — 176 ms contra 126 ms. O gargalo não é a
  ordenação, é o `count(*) OVER ()`, que obriga a ler todas as linhas mesmo com `LIMIT 20`
  e transforma a varredura sequencial em 200 mil acessos aleatórios ao heap quando o
  índice entra. A correção mede 13,4 ms (0,06 ms de página + 13,3 ms de `count`), mora em
  `app/domain/posts/listing.py` e custa **4 queries** onde o §11 do `CLAUDE.md` permite 3.
  Nenhum índice foi deixado para trás; a dívida está registrada.
- **A varredura dupla do filtro `q` do financeiro.** O índice resolveu o custo de cada
  varredura (66 ms → 7,0 ms); unir a consulta da página com a dos cartões de topo é
  mudança de `financial/service.py`. Dívida.
- **`app/domain/lawsuits/listing.py`**, que repete `unaccent(lower(...))` no `EXISTS` de
  partes da busca de processos. Mesma correção do defeito 4, arquivo de outra spec em voo.
- Marcar `lower(text)` como `LEAKPROOF` — ver regra 3.

> Fora de escopo é vinculante.

## 5. Modelo de dados

Nenhuma tabela nova. A migration `alembic/versions/137_tetos_indices_e_expurgos.py` faz
duas marcas de função e seis índices:

```sql
ALTER FUNCTION pg_catalog.texticlike(text, text) LEAKPROOF;
ALTER FUNCTION public.immutable_unaccent(text)   LEAKPROOF;

DROP INDEX ix_customers_name_trgm;  -- era immutable_unaccent(lower(name))
CREATE INDEX ix_customers_name_trgm ON customers USING gin (immutable_unaccent(name) gin_trgm_ops);
CREATE INDEX ix_transactions_description_trgm ON transactions USING gin (description gin_trgm_ops)
  WHERE description IS NOT NULL;
CREATE INDEX ix_posts_schedule ON posts (tenant_id, scheduled_date)
  WHERE show_in_schedule AND scheduled_date IS NOT NULL;
CREATE INDEX ix_posts_schedule_deadline ON posts (tenant_id, deadline_date)
  WHERE show_in_schedule AND deadline_date IS NOT NULL;
CREATE INDEX ix_notifications_recent ON notifications (tenant_id, user_id, created_at DESC, id DESC);
CREATE INDEX ix_deliveries_created ON webhook_deliveries (tenant_id, created_at);
```

## 6. Contratos de API

| Método | Rota | Mudança |
|---|---|---|
| GET | `/api/v1/schedule` | campo novo `truncated: bool` (padrão `false`) — avisa que o teto de 5.000 eventos cortou a janela |
| GET | `/ical/{token}.ics` | `ETag` + `Cache-Control: private, max-age=900`; responde `304` a `If-None-Match` que casa |
| GET | `/api/v1/crm/board` | mesma resposta, agora sempre correta |
| GET | `/api/v1/customers/stats` | mesma resposta, `with_active_lawsuit` sempre fresco |

Nenhum campo saiu e nenhum tipo mudou: cliente antigo continua funcionando.

## 7. Regras

1. **Toda consulta que devolve um intervalo tem teto de linhas, e o teto avisa.** Agenda:
   5.000 eventos (55 por dia numa janela de 90). Feed iCal: 10.000, e a janela passa de
   ±365 dias para 90 atrás / 365 à frente — o passado distante não serve a um calendário,
   e ele era metade dos 115.196 eventos medidos. Teto silencioso é pior que teto nenhum:
   `truncated` existe para a tela poder dizer que não está mostrando tudo.
2. **Expurgo apaga por predicado, nunca por lista de ids.** O corte vai dentro do comando.
   Uma lista de ids não é só lenta: acima de 32.767 ela é impossível, porque é o teto de
   parâmetros do asyncpg — e o expurgo de webhooks morria exatamente aí, em silêncio, uma
   vez por minuto.
3. **Duas funções passam a `LEAKPROOF`, e nenhuma outra.** `texticlike(text,text)` — o
   operador `ILIKE` — é a única peça de catálogo tocada, e é a mínima: sem ela nenhum
   índice trigram é alcançável sob RLS, com ou sem as outras mudanças. Ela é total sobre
   texto: não levanta erro em função do **dado** (só de um padrão malformado, que vem da
   consulta, não da linha), e o projeto já depende de o planner avaliar `texteq` sobre
   linhas de outros tenants em todo índice de igualdade que existe — `=` é leakproof desde
   sempre. `immutable_unaccent(text)` é nossa e tem a mesma natureza. **`lower()` não é
   marcada**: em vez de tocá-la, o predicado deixou de usá-la, porque `ILIKE` já ignora
   caixa. Uma função a menos na expressão é uma decisão de segurança a menos.
4. **O predicado da busca é a MESMA expressão do índice, e existe teste que compara as
   duas.** Não "parecida": o planner casa expressão idêntica.
5. **Agregado que muda por escrita de OUTRO agregado não entra em cache por evento.** O
   contador do CRM saiu do cache; `with_active_lawsuit` saiu do payload cacheado de
   contatos. A alternativa era acrescentar mais um lugar que precisa lembrar de invalidar
   — e a lista de lugares que precisam lembrar é a que ninguém mantém.
6. **Casamento de publicação não aplica função sobre a coluna.** Busca pelas duas grafias
   plausíveis do número (crua e a máscara canônica), que o `ix_lawsuits_number` serve
   direto; o `regexp_replace` fica como segunda tentativa e preserva o comportamento para
   grafia fora do padrão.
7. **Toda tabela de log tem horizonte declarado, com o motivo escrito ao lado.**
   `api_requests` 90 d, `notifications` 180 d, `ai_usage` 730 d, `search_history` 90 d,
   `automation_runs` 180 d (com os passos por cascata). Retenção sem motivo escrito vira
   número que ninguém ousa mexer.
8. **Varredura periódica que pode passar do intervalo tem trava de sobreposição.**
   Advisory lock, não linha em tabela: ele cai sozinho quando a conexão morre.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | predicado de busca == expressão do índice | `tests/integration/test_tetos_e_expurgos.py` | ~0,1 s |
| integração | `texticlike`/`immutable_unaccent` continuam LEAKPROOF (guarda de restore) | idem | ~0,1 s |
| integração | os 6 índices da 137 existem | idem | ~0,1 s |
| integração | busca sem acento continua achando (resultado não mudou) | idem | ~0,3 s |
| integração | expurgo de webhooks apaga 35.000 linhas (acima do teto de binds) | idem | ~1,5 s |
| integração | agenda avisa quando o teto corta | idem | ~0,5 s |
| integração | feed iCal responde `304` ao mesmo `ETag` | idem | ~0,3 s |
| integração | casamento por número acha cru e com máscara, e ainda acha grafia estranha | idem | ~0,9 s |
| integração | `list_by_responsible` para no teto | idem | ~0,4 s |
| integração | quadro do CRM conta o processo recém-criado | idem | ~0,4 s |
| integração | painel de contatos conta processo novo na hora | idem | ~0,4 s |
| integração | expurgo apaga o vencido e preserva o recente, nas 4 tabelas com `created_at` | idem | ~0,4 s |
| unidade | os 5 horizontes estão declarados | idem | ~0,0 s |
| integração | varredura de agregados não se sobrepõe; a chave não colide com a das migrations | idem | ~0,2 s |

**Total estimado:** +3 s
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

Um teste anterior mudou de número, e só um:
`test_dashboard_de_contatos_nao_vai_ao_banco_na_segunda_leitura` afirmava
`log.count == 1` na segunda leitura e agora afirma `2`. O que ele afirma continua sendo "a
segunda leitura não recalcula o painel"; a query a mais é `with_active_lawsuit`, que saiu
do cache porque o cache não tinha como mantê-la certa (regra 5). Ele codificava o defeito
7, e por isso não podia continuar passando sem edição.

## 9. Descobertas

- **O RLS desliga índice, e isso não aparece em lugar nenhum.** É a descoberta que mudou
  a spec (§2). Vale para todo predicado com função ou operador não-leakproof, não só para
  o trigram — e o único sinal é o plano.
- **`pg_dump` não emite `ALTER FUNCTION` de objeto de catálogo.** Depois de um
  `rito backup restore`, as marcas `LEAKPROOF` somem e os índices trigram voltam a ser
  ignorados em silêncio: plano pior, resultado igual, nenhum erro. O teste
  `test_funcao_da_busca_continua_leakproof` é a única forma de isso voltar a ser notado, e
  existe por causa disso.
- **Metade do defeito 6 não era defeito.** A auditoria mediu "arquivar o único processo
  mantém `total = 1`, deveria ser 0". A visão padrão do quadro é `all`, que conta processo
  arquivado de propósito (`LAWSUIT_VIEWS`, spec 027 §5): 1 é a resposta certa. Quem quer o
  quadro sem eles pede `view=active` — e aí o número sempre esteve certo, porque visão com
  filtro nunca passou pelo cache. O defeito real é o outro caso, o do processo criado.
- **O índice de expressão para Atividades foi construído, medido e descartado** (§4). É a
  medição que impediu esta spec de deixar um índice que só ocuparia disco e tornaria a
  página 40% mais lenta.
- **Comentário conta no gate de tamanho de função.** `tests/meta/test_tamanho_de_funcao.py`
  mede do primeiro ao último statement, e o bloco de comentário fica no meio do intervalo.
  Duas funções estouraram o teto de 30 por causa de comentário desta spec; as duas
  justificativas foram para o docstring, que a contagem ignora. Vale saber antes de
  escrever a próxima.
- **`with_active_lawsuit` ficou 10× mais barato ao sair do cache.** O `EXISTS`
  correlacionado percorria os 100 mil contatos (413 ms); contando clientes distintos a
  partir de `lawsuit_parties`, que é a tabela pequena, são 41 ms. E o
  `/api/v1/customers/stats` **caiu de 5 para 4 queries** no caminho frio, porque as três
  distribuições (origem, ocupação, faixa etária) viraram um `UNION ALL` — foi isso que
  abriu espaço no orçamento do §11 para a consulta sempre fresca.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras com teste
- [x] Nenhuma tabela nova (nada de RLS a testar)
- [x] Testes anteriores passando sem edição, com a única exceção do §8, explicada
- [x] Orçamento de queries do §11 respeitado: `/crm/board` 5 (teto 5),
      `/customers/stats` 5 → **4**, `/schedule` 2, `/notifications` 3
- [x] `make lint` verde nos arquivos da spec (`ruff`, `ruff format`, `mypy` em 671 arquivos)
- [x] Sem `Any`, `# type: ignore` ou `# noqa` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `fix(137): tetos, índices e expurgos`
