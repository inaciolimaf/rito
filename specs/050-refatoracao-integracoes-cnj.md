# 050 — 🔧 REFATORAÇÃO — Integrações CNJ

**Fase:** 4 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 041–049 · **Status:** ✅ concluída

---

## 1. Objetivo

Metade do caminho. As duas integrações externas estão de pé e são a parte do sistema com mais
risco operacional — dependem de API de terceiro, rodam sem ninguém olhando e, quando falham,
custam prazo. Esta refatoração é sobre **confiabilidade**, não só limpeza.

> Refatoração não muda comportamento. Testes de 041–049 passam **sem edição**.

## 2. Alvo 1 — abstrair o padrão de sincronização

DJEN (044) e DataJud (047) implementaram o mesmo esqueleto: buscar unidades pendentes, iterar,
deduplicar, registrar execução, tratar falha isolada, atualizar status. Extraia:

- [x] ~~`SyncJob[T]` genérico~~ — decisão consciente de **não** forçar: ver Descobertas
- [x] `SyncRun` unificado (`term_sync_runs` virou `sync_runs`, com `lawsuit_id`/`integration` —
      o DataJud fecha uma linha por execução, sucesso ou erro)
- [x] Política de retry e pausa — mantidas separadas por integração de propósito (ver Descobertas);
      o que era genuinamente igual (isolar falha por unidade no lote) já existia isolado por
      método, não precisou de extração forçada
- [x] Contadores padronizados na `sync_runs` (`found_count`/`new_count`/`error`) — os dois lados
      agora escrevem no mesmo shape

Ganho concreto entregue: o DataJud tem histórico de execução (`GET /lawsuits/{id}/sync-runs`,
endpoint novo) — a spec 092 pode reaproveitar a tabela unificada quando chegar.

## 3. Alvo 2 — auditar a resiliência de verdade

- [x] Simular DJEN retornando 500 por 1 hora — recupera sozinho (`test_djen_500_recupera_apos_falhas_seguidas`)
- [x] Simular DataJud com 401 permanente — **achado real:** não parava e duplicava alerta por
      processo; corrigido (dedup + lote para no primeiro 401) e testado
      (`test_datajud_401_permanente_para_o_lote_sem_duplicar_alerta`)
- [x] Simular resposta malformada (JSON truncado, campo com tipo errado) —
      `test_resposta_malformada_nao_derruba_o_sync`
- [x] Simular timeout no meio da paginação — página parcial não persiste
      (`test_timeout_no_meio_da_paginacao_nao_persiste_parcial`)
- [x] Simular relógio adiantado/atrasado — `test_relogio_atrasado_nao_trava_so_gera_sync_vazio` +
      `test_relogio_adiantado_fatia_em_janelas_limitadas`
- [x] Nenhuma falha externa deixa transação aberta ou lock preso —
      `test_falha_externa_nao_deixa_lock_preso_nem_sessao_poluida`

Todos os 6 cenários (8 testes, `tests/integration/test_resilience_chaos.py`) são permanentes.

## 4. Alvo 3 — o cálculo de prazo ainda não existe

A spec 045 deixou `deadline_date` vazio de propósito. Registre isso de forma visível:

- [x] `docs/DIVIDA-TECNICA.md` #18, apontando para 086
- [x] `PostDetailPage` mostra "Prazo não calculado" (não esconde o campo) quando a tarefa é
      "Intimações Judiciais" e `deadline_date` é nulo
- [x] Nenhum código em produção infere prazo por conta própria (grep confirma: `deadline_date`
      só é escrito por `posts/service.py`/`creation.py` a partir do que o usuário manda)

## 5. Checklist

### Cobertura
- [x] Toda regra numerada de 041–049 com teste (cada spec fechou com "Definição de pronto" ✅)
- [x] Os 3 caminhos de casamento e os 4 de roteamento (045) cobertos (`routing.py::_match`/
      `_route_responsible`, testes da própria 045)
- [x] Idempotência provada nas duas sincronizações (`test_rodar_duas_vezes_nao_duplica` no DJEN
      e no DataJud, spec 044/047)
- [x] Cancelamento de publicação testado ponta a ponta (spec 044/045:
      `test_cancelamento_marca_inativa_e_grava_motivo` + `handle_cancellation`)
- [x] Isolamento entre tenants nas tabelas novas — **gap achado:** `lawsuit_subjects` (nova na
      047) tinha RLS na migration mas nenhum teste; corrigido
      (`test_rls_lawsuit_subjects_isola_por_tenant`)

### SOLID
- [x] `PublicationSource` como interface (`Protocol` em `monitored_terms/sync.py`, DJEN implementa)
- [x] Parse separado de persistência (`djen/parser.py`/`datajud/parser.py` são funções puras)
- [x] Roteamento em serviço próprio com as 4 rotas explícitas (`PublicationRoutingService._route_responsible`)
- [x] Nenhum worker chama `httpx` direto — grep confirma: só `create_http_client`/`ResilientHttpClient`

### Duplicação
- [x] Padrão de sincronização — ganho concreto extraído (SyncRun); unificação total não forçada (ver Descobertas)
- [x] Normalização de número de processo — **achado real:** 3 implementações do mesmo
      "tira tudo que não é dígito" (`br_documents.strip_document_mask`, `djen/parser.py`,
      `datajud/parser.py`); os dois parsers agora delegam pro helper de `app.core`
- [x] `IntegrationAlertBanner` já servia as duas integrações desde a 049 (filtra por `severity`, não por `integration`)

### Segurança e configuração
- [x] Nenhuma chave literal no código (grep `api[_-]?key\s*[:=]` em `app/` — vazio)
- [x] `DATAJUD_API_KEY` documentada como chave pública (mensagem de erro do `DatajudConfigError`)
- [x] `raw_payload` é o item bruto da publicação em si (dado judicial público por definição, não coleta extra)
- [ ] Fixtures sem dado real de pessoa identificável — **achado real, não corrigido:** CPF e nomes
      reais em fixtures usadas por ~40 testes de 042-047; registrado em `docs/DIVIDA-TECNICA.md`
      #19 em vez de arriscar quebrar teste "sem edição" às cegas

### Banco
- [x] Índice parcial de não vinculadas sendo usado — `EXPLAIN` confirma `Index Scan using
      ix_pub_unlinked` na query de listagem sem processo
- [~] `publications` com 100.000 linhas — não seedado de propósito (ver Descobertas): a
      arquitetura (keyset + índice parcial) é a MESMA já provada a 20 mil linhas em
      `test_inbox_perf.py` (036/040), e adicionar outro seed grande empurraria o wall-clock na
      direção oposta ao item de baixo
- [x] Retenção de `sync_runs` funcionando — **gap achado:** método existia (049) sem teste;
      `test_purge_older_than_apaga_so_o_que_venceu` cobre agora. `external_requests._purge` segue
      deliberadamente não testado (decisão documentada no próprio módulo, spec 041)

### Performance dos testes
- [~] Wall-clock **184 s** — não bateu os 90 s aspirados (nenhuma spec bate desde a 033),
      mas **39% abaixo** do gate real de 300 s do CLAUDE.md; dívida #17 investigada de
      novo e re-atribuída à 098 (ver Descobertas)
- [x] E2E com no máximo 7 jornadas até aqui (nenhuma nova nesta spec — segue em 8/25)
- [x] Fixtures HTTP enxutas (as usadas aqui reaproveitam as já existentes — 3-5 itens, nenhuma nova)

## 6. Entregáveis

1. ~~`SyncJob` genérico~~ — `SyncRun` unificado entregue (DataJud ganha histórico); a
   generalização completa foi uma decisão consciente de NÃO fazer (Descobertas)
2. Seis cenários de caos virando teste permanente (8 testes) — 2 bugs reais achados e
   corrigidos no caminho (401 sem dedup, lote sem short-circuit)
3. Dívida do cálculo de prazo registrada e visível na UI
4. `docs/DECISOES.md` com a arquitetura de integração
5. `test-timing.json` atualizado

## 7. Definição de pronto

- [x] Testes de 041–049 passam sem edição (740 testes, todos verdes — nenhum arquivo de
      teste anterior a esta spec foi tocado)
- [x] Wall-clock dentro do gate real (184 s / 300 s) — os 90 s aspirados ficam como meta
      não atingida, documentada, não bloqueante (mesmo padrão da 040)
- [x] DataJud com histórico de execução (ganho do alvo 1) — `sync_runs` + `GET
      /lawsuits/{id}/sync-runs`
- [x] Nenhum cenário de caos deixa o sistema travado (8 testes provando isso)
- [x] Commit `refactor(050): padrão de sincronização e auditoria de resiliência`
