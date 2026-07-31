# 098 — Performance

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 096 · **Status:** ⬜ pendente

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

Registrar aqui as N+1 encontradas e os índices criados.

## 10. Definição de pronto

- [ ] Budget de queries ativo em todo PR
- [ ] Nenhuma FK sem índice
- [ ] Todas as metas de p95 atingidas no nightly
- [ ] `docs/PERFORMANCE.md` com a linha de base
- [ ] Commit `feat(098): performance e budget de queries`
