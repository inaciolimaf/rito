# 044 — DJEN: sincronização

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 043 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Idempotência provada · Cancelamento tratado · Commit `feat(044): DJEN — sincronização`
