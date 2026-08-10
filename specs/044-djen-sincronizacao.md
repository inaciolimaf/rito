# 044 — DJEN: sincronização

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 043 · **Status:** ✅ concluída

---

## 1. Objetivo

O worker que roda todo dia, consulta o DJEN por cada termo ativo e persiste o que é novo. O
requisito mais importante é **idempotência**: rodar duas vezes não pode duplicar nada.

## 2. Escopo

- Task Celery agendada (`DJEN_SYNC_CRON`) + gatilho manual
- Iteração por termo com paginação
- **Deduplicação por `hash`**
- **Tratamento de publicação cancelada**
- Janela incremental por termo
- Registro em `term_sync_runs`
- Transição de status do termo

## 3. Fora de escopo

- Roteamento para tarefa → 045 (esta spec só persiste a publicação)
- Painel de status → 049

## 4. Modelo de dados

Nenhuma tabela nova. Coluna de controle:

```sql
ALTER TABLE monitored_terms ADD COLUMN last_captured_date DATE;
```
Migration `044_sync_control.py`.

## 5. Fluxo

```
para cada termo ativo com next_sync_at <= agora:
  cria term_sync_run
  janela = [coalesce(last_captured_date, backfill_from), hoje]
  para cada página do DJEN:
    para cada item:
      se hash já existe no tenant:
        se status mudou para cancelada → marca is_active=false e registra motivo
        senão → ignora
      senão:
        persiste publication + recipients + lawyers
        enfileira roteamento (spec 045)
  atualiza last_captured_date, last_success_at, next_sync_at, status
  fecha term_sync_run com contadores
```

## 6. Contratos internos

```python
class PublicationSource(Protocol):
    async def fetch(self, term: MonitoredTerm, start: date, end: date,
                    page: int) -> PublicationPage: ...
```
O DJEN é uma implementação. A interface permite trocar a fonte sem tocar no worker.

**Mapeamento termo → query DJEN** (verificado ao vivo em 2026-08-10):
- `OAB` → `numeroOab` + `ufOab`;
- `CPF`/`CNPJ` → o DJEN não filtra por documento, mas aceita `texto` (full-text no
  corpo) — `texto=ZZZZZZZZ` derruba o count de 10.000 para 0 na mesma janela. O valor
  vai só com dígitos, como está gravado no termo.

Agendamento: `DJEN_SYNC_CRON` (5 campos, diário — ex.: `17 3 * * *`) configura o beat
e o cálculo de `next_sync_at` (helper `next_daily_run`).

Run aberta: o sync manual da 043 abre `TermSyncRun` sem processar — a varredura desta
spec consome runs abertas além dos termos devidos (descoberta registrada na 043).

## 7. Regras de negócio

1. Deduplicação por `(tenant_id, hash)`. Reprocessar a mesma janela não cria linha nova.
2. **Publicação cancelada:** se o item retornar com `status` de cancelamento ou
   `motivo_cancelamento` preenchido, a publicação existente vira `is_active = false`,
   grava o motivo e a data. Ela **não é apagada** — e a tarefa gerada (045) recebe um alerta.
3. Janela incremental: a partir de `last_captured_date`, com **1 dia de sobreposição** para
   cobrir publicação que entra com atraso no DJEN.
4. Primeira execução usa `backfill_from`.
5. Falha em um termo **não** interrompe os demais — cada termo é uma unidade de trabalho isolada.
6. Falha marca o termo como `FALHA` com a mensagem; sucesso volta para `ATIVO`.
7. Três falhas consecutivas geram alerta como **tarefa** para o responsável (implementado em 049).
8. Rate limit do DJEN é respeitado via o client de 041; a task não paraleliza por termo além do teto.
9. Persistência de cada página é transacional. Falha no meio não deixa página pela metade.
10. Execução concorrente do mesmo termo é impedida por lock em Redis.
11. Sem itens novos ainda assim atualiza `last_success_at` — silêncio é resultado válido.
12. Janela máxima por execução: 90 dias, fatiada se `backfill_from` for maior.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | primeira sync persiste N publicações | ~0,5 s |
| integração | **rodar duas vezes não duplica** | ~0,5 s |
| integração | janela incremental com sobreposição de 1 dia | ~0,4 s |
| integração | **cancelamento marca inativa e grava motivo** | ~0,5 s |
| integração | cancelamento não apaga a publicação | ~0,3 s |
| integração | falha em um termo não afeta os outros | ~0,4 s |
| integração | falha marca FALHA; sucesso volta a ATIVO | ~0,4 s |
| integração | lock impede execução concorrente | ~0,4 s |
| integração | paginação percorre todas as páginas | ~0,4 s |
| integração | página parcial não persiste pela metade | ~0,4 s |
| integração | backfill de 12 meses é fatiado em janelas de 90 dias | ~0,4 s |
| integração | sem itens atualiza `last_success_at` | ~0,2 s |
| integração | `term_sync_runs` registra os contadores | ~0,3 s |

**Total:** ~5,1 s
Todas as respostas do DJEN vêm de fixture — nenhuma chamada real.

## 9. Descobertas

- **Termos CPF/CNPJ consultam pelo `texto`.** O DJEN não tem filtro por documento, mas
  aceita `texto` (full-text no corpo) — verificado ao vivo em 2026-08-10: mesma janela,
  `count` cai de 10.000 para 0 com `texto=ZZZZZZZZZZ`. O `DjenClient` ganhou
  `text_query` e o `DjenPublicationSource` mapeia OAB → `numeroOab`/`ufOab`,
  CPF/CNPJ → `texto` com os dígitos do termo.
- **SET LOCAL morre no commit.** O service commita por página (regra 9), mas
  `set_config('app.tenant_id', ..., is_local=true)` vale só até o fim da transação.
  Sem rearmar o contexto após cada commit/rollback, o RLS esconderia as linhas seguintes
  — e os UPDATEs afetariam 0 linhas **em silêncio**. O `TermSyncService` rearma
  `app.tenant_id` em `_commit`/`_rollback`; qualquer service futuro com commit interno
  precisa do mesmo padrão (candidato a helper em core na refatoração 050).
- **Objeto de outra sessão não atravessa.** A listagem cross-tenant do worker e a
  sincronização usam sessões diferentes — o service recarrega o termo por id na própria
  sessão antes de qualquer acesso (e devolve None se o termo sumiu no meio do caminho).
- **Ciclo de import pelo `__init__` do pacote.** `domain/monitored_terms/sync` →
  `publications/service` → `djen/parser` → `djen/__init__` → `djen/source` → sync.
  O adapter ficou fora do re-export do pacote (import direto de
  `app.integrations.djen.source`); documentado no próprio `__init__`.
- **Teste sem a fixture `client` precisa registrar os models.** Sem `app.main` importado,
  a FK `publications.lawsuit_id` não resolve no flush
  ("could not find table 'lawsuits'"). Solução: `import app.domain.lawsuits.models`
  explícito no módulo de teste — vale para qualquer teste novo que persista em tabela
  com FK para outro contexto sem passar pela app.
- **Lock com token + release comparado (Lua).** Sem token, uma execução que estourou o
  TTL apagaria o lock de quem re-adquiriu depois — o caso clássico do SET NX EX cru.
- **Run aberta do sync manual é consumida, não duplicada** (a dívida registrada na 043
  fecha aqui): `_execute` reusa `get_running(term.id)` antes de criar run nova, e o
  router agora agenda `sync_term_by_id` com countdown de 5 s (o commit da request
  acontece antes do worker ler). `schedule_term_sync` é no-op em `APP_ENV=test`.
- **Baseline das notas de timing estava errado.** O 043 anotava 662 backend/139 frontend;
  o real medido por `--collect-only` no HEAD era 643/134. O `test-timing.json` desta
  spec registra os números medidos e a divergência.
- **Anulação provavelmente NÃO chega pela listagem** (descoberta da 042, confirmada no
  desenho daqui): o tratamento da regra 2 está implementado e testado com a fixture
  derivada, mas em produção a marcação de anuladas pode depender de re-captura da mesma
  janela — o overlap de 1 dia (regra 3) é o que dá chance ao DJEN de devolver o item
  atualizado. Se o ADVBOX trata por outra via (endpoint de anuladas), fica para a 049/050
  investigar com o painel de observabilidade.
- Roteamento para tarefa (045) tem o gancho pronto: `_process_item` é o ponto único por
  publicação nova; a 045 pendura o casamento processo/advogado ali sem tocar na janela.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (14 integração + 8 unit + 1 client; regra 7 — alerta após 3 falhas — fica para a 049, como a própria spec declara)
- [x] Teste de isolamento por tenant (sem tabela nova; RLS existente coberto nas specs 042/043 — esta spec só adiciona coluna)
- [x] `make test` verde e wall-clock < 300 s (181 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (PublicationService.register reutilizado; RedisSyncLock extraído para core)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(044): DJEN — sincronização`
