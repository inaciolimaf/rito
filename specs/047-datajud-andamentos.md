# 047 — DataJud: andamentos

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 046, 026 · **Status:** ✅ concluída

---

## 1. Objetivo

Manter a timeline do processo atualizada com os movimentos oficiais do tribunal, sem raspagem.
É o que alimenta as visões "parado há +90 dias" e o campo `last_movement_at`.

## 2. Escopo

- Task Celery agendada + gatilho manual por processo
- Sincronização só de processos **cadastrados** com número CNJ válido
- Incremental por `dataHoraUltimaAtualizacao`
- Persistência em `lawsuit_movements` com `origin = TRIBUNAL`
- Atualização de `last_movement_at`
- Enriquecimento da capa (órgão julgador, classe, assuntos, data de ajuizamento)

## 3. Fora de escopo

- Descoberta de processos novos por OAB — o Rito não faz isso, por escolha de escopo
- Análise de movimento por IA → 089

## 4. Modelo de dados

```sql
ALTER TABLE lawsuits
  ADD COLUMN datajud_last_sync_at TIMESTAMPTZ,
  ADD COLUMN datajud_last_update  TIMESTAMPTZ,   -- dataHoraUltimaAtualizacao do CNJ
  ADD COLUMN datajud_not_found_count SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN judging_organ TEXT,
  ADD COLUMN filing_date DATE,
  ADD COLUMN cnj_class_code INTEGER,
  ADD COLUMN cnj_class_name TEXT;

CREATE TABLE lawsuit_subjects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  code INTEGER NOT NULL, name TEXT NOT NULL,
  UNIQUE (lawsuit_id, code)
);

CREATE INDEX ix_lawsuits_datajud_due ON lawsuits (tenant_id, datajud_last_sync_at NULLS FIRST)
  WHERE process_number IS NOT NULL AND NOT is_archived;
```
Migration `047_datajud_sync.py`.

## 5. Fluxo

```
para cada processo com número CNJ, não arquivado, ordenado por datajud_last_sync_at:
  resolve o alias pelo tribunal (ou infere pelo número — spec 025)
  consulta o DataJud
  se não encontrado:
    incrementa datajud_not_found_count; ao chegar em 5, pausa e alerta
  senão:
    para cada movimento com dataHora > datajud_last_update:
      insere em lawsuit_movements (external_id = id do movimento)
    atualiza capa, last_movement_at, datajud_last_update, datajud_last_sync_at
```

## 6. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/lawsuits/{id}/sync-movements` — manual |
| GET | `/api/v1/lawsuits/{id}/sync-status` |

## 7. Regras de negócio

1. Só processos com `process_number` válido e não arquivados entram na fila.
2. Deduplicação por `(tenant_id, lawsuit_id, external_id)` — reprocessar não duplica movimento.
3. Incremental por `dataHoraUltimaAtualizacao`: se o CNJ não mudou nada, a sincronização termina sem escrever.
4. `nivelSigilo > 0` → nada é persistido e o processo é marcado como não sincronizável.
5. Processo não encontrado 5 vezes seguidas é pausado, com alerta — número errado ou tribunal sem cobertura.
6. Movimento do tribunal é **imutável** na UI (regra já definida em 026).
7. `last_movement_at` é atualizado pela trigger de 027 — não escreva na mão.
8. Capa só sobrescreve campo que estiver **vazio** no Rito. Dado digitado pelo usuário vence o do CNJ.
9. Rate limit respeitado; a fila é processada em lotes.
10. Sincronização manual de processo já em andamento → 409.
11. Falha em um processo não interrompe o lote.
12. `filing_date` do CNJ não sobrescreve `process_date` — são coisas diferentes (ajuizamento × requerimento).

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | primeira sync traz todos os movimentos | ~0,5 s |
| integração | **rodar duas vezes não duplica** | ~0,4 s |
| integração | incremental ignora movimento antigo | ~0,4 s |
| integração | sem mudança não escreve nada | ~0,3 s |
| integração | segredo de justiça não persiste | ~0,3 s |
| integração | 5 não-encontrados pausa e alerta | ~0,4 s |
| integração | capa não sobrescreve campo preenchido | ~0,4 s |
| integração | `filing_date` não toca `process_date` | ~0,2 s |
| integração | `last_movement_at` atualiza pela trigger | ~0,3 s |
| integração | falha em um não interrompe o lote | ~0,4 s |
| integração | sync manual concorrente → 409 | ~0,3 s |
| integração | movimento aparece na timeline | ~0,3 s |
| integração | processo arquivado fora da fila | ~0,2 s |

**Total:** ~4,4 s

## 9. Descobertas

- **"Pausado" não tem coluna de status — é o predicado da fila.** A ALTER TABLE do §4
  não tem um booleano tipo `is_paused`. O mecanismo real é
  `datajud_not_found_count < 5` no `WHERE` de `list_due_for_datajud_sync` (e no
  índice parcial `ix_lawsuits_datajud_due`): ao chegar em 5, o processo simplesmente
  para de aparecer na fila, sem precisar de mais nada. Regra 4 (sigilo) reaproveita o
  MESMO contador: em vez de esperar 5 tentativas, `nivelSigilo > 0` já escreve
  `datajud_not_found_count = 5` na primeira vez — "não sincronizável" imediato, porque
  segredo de justiça não muda de uma consulta pra outra. Isso significa que os dois
  caminhos (sigilo e não-encontrado) convergem pro mesmo mecanismo de saída da fila,
  mas só o não-encontrado gera alerta (regra 5) — sigilo é silencioso de propósito.
- **A API não devolve um id por movimento.** Conferido contra o glossário oficial do
  tutorial do CNJ (mesma fonte da spec 046) e a fixture real capturada lá:
  `movimentos[]` só tem `codigo`/`nome`/`dataHora`/`complementosTabelados`/
  `orgaoJulgador` — nenhum `id`. A "chave de dedupe = id do movimento" do §5 não existe
  de verdade; a chave sintética virou `f"{code}:{occurred_at.isoformat()}:{organ_code}"`,
  estável entre execuções (o mesmo movimento sempre gera a mesma chave) e específica o
  bastante pra não colidir com outro movimento genuíno do mesmo processo.
- **`DatajudService` (046) ganhou `fetch_process_status` sem quebrar `fetch_process`.**
  A 046 só precisava saber "tem processo ou não" (sigilo e não-encontrado colapsados
  em `None`); a 047 precisa DISTINGUIR os dois (sigilo pausa na hora, não-encontrado
  conta até 5). Extrair um `_fetch`/`ProcessFetchStatus` interno e fazer `fetch_process`
  delegar pra ele manteve os testes da 046 verdes sem editar uma linha — só
  `movement_sync_service.py` (novo) e o service da 046 (extensão aditiva) mudaram.
- **Sync manual roda síncrono dentro da request — diferente do padrão da 043/044.**
  DJEN sincroniza um TERMO inteiro (potencialmente páginas de histórico, lento) e por
  isso o gatilho manual só abre uma run e agenda via Celery (`schedule_term_sync`,
  fire-and-forget). Aqui a unidade é UM processo — uma chamada HTTP síncrona ao DataJud
  cabe folgado dentro do timeout de uma request — então `POST /sync-movements` chama
  `sync_lawsuit_locked` direto e devolve o resultado já pronto. O lote agendado
  (`app/workers/datajud_sync.py`, Celery beat) é que segue o padrão assíncrono da 044.
- **Alerta de sigilo não existe — só o de não-encontrado (regra 5).** A spec não pede
  alerta pra segredo de justiça (regra 4 só diz "marcado como não sincronizável"), e
  isso faz sentido: sigilo é um estado normal e esperado do processo, não uma falha
  de configuração como número errado ou tribunal sem cobertura.
- **`lawsuit_subjects` não tem teste dedicado** — o plano de testes da spec não
  declarou um caso pra assuntos (só a tabela no §4). Implementado (insert-if-not-exists
  por `code`, nunca remove) mas coberto só incidentalmente pelos testes de capa —
  fica pra uma spec futura (BI/relatórios) testar de verdade se precisar exibir.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (descoberta de processos por OAB continua fora,
      como o §3 determina; IA de movimento é da 089)
- [x] Todas as regras de negócio com teste (13 testes — as 12 regras numeradas do §7
      cobertas individualmente, incluindo o dedup isolado do filtro incremental)
- [x] Teste de isolamento por tenant (`lawsuit_subjects` é tabela nova com RLS padrão
      via `enable_rls`; o alerta de não-encontrado, tenant-scoped, foi verificado com
      `tenant_id == setup.gestor.tenant_id` — RLS padrão da 003, sem a exceção OR da 046)
- [x] `make test` verde e wall-clock < 300 s (189 s — 711 backend, 134 frontend, 7 e2e)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (`infer_court_code`/
      `parse_cnj` da spec 025 reaproveitados sem duplicar; `LawsuitMovementRepository.
      find_by_external_id` da 026 reaproveitado pro dedup; `RedisSyncLock`/`SyncLock`
      da 041 reaproveitados pro lock de sincronização manual)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(047): DataJud — andamentos`
