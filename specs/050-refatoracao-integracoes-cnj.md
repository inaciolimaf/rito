# 050 — 🔧 REFATORAÇÃO — Integrações CNJ

**Fase:** 4 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 041–049 · **Status:** ⬜ pendente

---

## 1. Objetivo

Metade do caminho. As duas integrações externas estão de pé e são a parte do sistema com mais
risco operacional — dependem de API de terceiro, rodam sem ninguém olhando e, quando falham,
custam prazo. Esta refatoração é sobre **confiabilidade**, não só limpeza.

> Refatoração não muda comportamento. Testes de 041–049 passam **sem edição**.

## 2. Alvo 1 — abstrair o padrão de sincronização

DJEN (044) e DataJud (047) implementaram o mesmo esqueleto: buscar unidades pendentes, iterar,
deduplicar, registrar execução, tratar falha isolada, atualizar status. Extraia:

- [ ] `SyncJob[T]` genérico: fila de unidades, lote, lock, registro de execução, isolamento de falha
- [ ] `SyncRun` unificado (hoje `term_sync_runs` só cobre o DJEN — o DataJud não tem histórico)
- [ ] Política de retry e pausa por unidade em um só lugar
- [ ] Contadores e métricas padronizados

Ganho concreto: o DataJud passa a ter histórico de execução de graça, e a spec 092 (automação)
reaproveita a infraestrutura.

## 3. Alvo 2 — auditar a resiliência de verdade

- [ ] Simular DJEN retornando 500 por 1 hora — o sistema se recupera sozinho?
- [ ] Simular DataJud com 401 permanente — pausa mesmo, sem loop?
- [ ] Simular resposta malformada (JSON truncado, campo com tipo errado)
- [ ] Simular timeout no meio da paginação — a página parcial não persiste?
- [ ] Simular relógio adiantado/atrasado na janela incremental
- [ ] Verificar que nenhuma falha externa deixa transação aberta ou lock preso

Cada cenário vira teste permanente.

## 4. Alvo 3 — o cálculo de prazo ainda não existe

A spec 045 deixou `deadline_date` vazio de propósito. Registre isso de forma visível:

- [ ] `docs/DIVIDA-TECNICA.md` com a pendência apontando para 086
- [ ] A UI de intimações mostra "prazo não calculado" em vez de campo vazio ambíguo
- [ ] Nenhum código em produção infere prazo por conta própria

## 5. Checklist

### Cobertura
- [ ] Toda regra numerada de 041–049 com teste
- [ ] Os 3 caminhos de casamento e os 4 de roteamento (045) cobertos
- [ ] Idempotência provada nas duas sincronizações
- [ ] Cancelamento de publicação testado ponta a ponta
- [ ] Isolamento entre tenants nas tabelas novas

### SOLID
- [ ] `PublicationSource` como interface — o DJEN é uma implementação, não o contrato
- [ ] Parse separado de persistência (funções puras testáveis sem banco)
- [ ] Roteamento de intimação em serviço próprio, com as 4 rotas explícitas
- [ ] Nenhum worker chamando `httpx` direto — tudo pelo `HttpClient` de 041

### Duplicação
- [ ] Padrão de sincronização extraído (alvo 1)
- [ ] Normalização de número de processo em um só lugar
- [ ] `IntegrationAlertBanner` servindo as duas integrações

### Segurança e configuração
- [ ] Nenhuma chave literal no código (grep no CI)
- [ ] `DATAJUD_API_KEY` documentada como chave pública, não segredo pessoal
- [ ] `raw_payload` sem dado que não deveria ser persistido
- [ ] Fixtures sem dado real de pessoa identificável (anonimize)

### Banco
- [ ] Índice parcial de não vinculadas sendo usado
- [ ] `publications` com 100.000 linhas: listagem ainda rápida
- [ ] Retenção de `external_requests` e `term_sync_runs` funcionando

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] E2E com no máximo 7 jornadas até aqui
- [ ] Fixtures HTTP enxutas (não guarde 500 itens quando 3 bastam)

## 6. Entregáveis

1. `SyncJob` genérico com as duas sincronizações migradas
2. Seis cenários de caos virando teste permanente
3. Dívida do cálculo de prazo registrada e visível na UI
4. `docs/DECISOES.md` com a arquitetura de integração
5. `test-timing.json` atualizado

## 7. Definição de pronto

- [ ] Testes de 041–049 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] DataJud com histórico de execução (ganho do alvo 1)
- [ ] Nenhum cenário de caos deixa o sistema travado
- [ ] Commit `refactor(050): padrão de sincronização e auditoria de resiliência`
