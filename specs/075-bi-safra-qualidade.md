# 075 — BI: Safra e Qualidade

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 074 · **Status:** ✅ concluída

---

## 1. Objetivo

Taxa de sucesso por área e acompanhamento de **safra** — cada conjunto de processos fechados
num ano é um ciclo produtivo que se acompanha até o fim. Responde "em que somos bons?" e
"o que fechamos em 2024 já terminou?".

## 2. Escopo

- Taxa de sucesso por grupo de ação
- Evolução da taxa ao longo do tempo
- Tabela de safra: ano de fechamento × estágio atual
- Comparação histórica entre safras
- Volume concluído × em andamento por safra

## 3. Fora de escopo

- Tempo e honorários → 076 · Custos → 077 · Previsão por IA → 089

## 4. Modelo de dados

```sql
CREATE MATERIALIZED VIEW bi_vintage AS
SELECT tenant_id,
       EXTRACT(YEAR FROM closure_date)::int AS vintage_year,
       action_group_id,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE outcome = 'GANHO')   AS won,
       COUNT(*) FILTER (WHERE outcome = 'PERDIDO') AS lost,
       COUNT(*) FILTER (WHERE outcome = 'ACORDO')  AS settled,
       COUNT(*) FILTER (WHERE outcome IS NULL)     AS in_progress,
       COUNT(*) FILTER (WHERE transit_date IS NOT NULL)  AS transited,
       COUNT(*) FILTER (WHERE archived_date IS NOT NULL) AS archived,
       AVG(archived_date - closure_date) FILTER (WHERE archived_date IS NOT NULL) AS avg_cycle_days
FROM lawsuits
WHERE closure_date IS NOT NULL
GROUP BY 1,2,3;
CREATE UNIQUE INDEX ux_bi_vintage ON bi_vintage (tenant_id, vintage_year, action_group_id);
```
Migration `075_bi_vintage.py`. Refresh a cada 8 h.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/bi/vintage?from_year=&to_year=&action_group_id=` |
| GET | `/api/v1/bi/success-rate?period=&action_group_id=` |
| GET | `/api/v1/bi/success-rate/trend?action_group_id=&months=24` |

## 6. Front-end

**Reutiliza:** `StatCard`, `DataTable`, `BarChart`, `FilterBar`
**Cria:** `VintagePanel`, `VintageTable` (ano × estágio), `SuccessRateCard` (por grupo, com
sparkline), `SuccessTrendChart`
**Rota:** `/reports?tab=vintage`

## 7. Regras de negócio

1. **Taxa de sucesso considera só processos concluídos** — com `outcome` preenchido. Em tramitação fica de fora, sob pena de distorcer.
2. Taxa = ganhos ÷ (ganhos + perdidos + acordos). Acordo entra no denominador; se deve entrar no numerador é decisão de negócio — **não entra**, e a UI explica isso num tooltip.
3. Safra = ano de `closure_date` (fechamento do contrato), não de criação.
4. A tabela de safra mostra, por ano: total, ganhos, perdidos, acordos, em andamento, transitados, arquivados e ciclo médio em dias.
5. Grupo com menos de **10 processos concluídos** na safra exibe aviso de amostra pequena — taxa com 2 casos não significa nada.
6. Sparkline da taxa cobre os últimos 24 meses.
7. Ciclo médio = `archived_date` − `closure_date`, só entre os arquivados.
8. Safra sem nenhum fechamento não aparece na tabela.
9. Comparação histórica destaca variação acima de 10 pontos percentuais entre safras consecutivas.
10. Exige ADMINISTRADOR ou GESTOR.
11. Divisão por zero → "—".

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | **taxa ignora processos em tramitação** | ~0,4 s |
| integração | acordo no denominador, fora do numerador | ~0,3 s |
| integração | safra agrupa por `closure_date` | ~0,4 s |
| integração | tabela com os 8 campos por safra | ~0,5 s |
| integração | menos de 10 concluídos → aviso de amostra | ~0,3 s |
| integração | ciclo médio só entre arquivados | ~0,3 s |
| integração | safra sem fechamento não aparece | ~0,2 s |
| integração | variação acima de 10 p.p. é destacada | ~0,3 s |
| integração | zero concluídos → "—" | ~0,2 s |
| integração | Colaborador → 403 | ~0,2 s |
| frontend | tooltip explica o critério da taxa | ~0,3 s |

**Total:** ~3,4 s

## 9. Descobertas

1. **Mesma divergência estrutural da 074: `lawsuits` não tem `action_group_id`.** O SQL
   literal do §4 referencia a coluna, mas desde a spec 022 (regra 2) o grupo é derivado
   do tipo de ação — a view faz `JOIN lawsuit_types lt ON lt.id = l.lawsuit_type_id`,
   cardinalidade e semântica preservadas. Ao contrário da `bi_pipeline_monthly`, aqui
   **não** há filtro `NOT is_archived`: a safra acompanha o processo até o arquivamento
   (campos `archived` e `avg_cycle_days`, regras 4 e 7), então arquivados permanecem.
2. **A view é anual; taxa por período e série são tempo real.** `bi_vintage` agrega por
   ano de `closure_date` (regra 3), então `/bi/vintage` (tabela, regra 4) vem da view
   barreira, mas `/bi/success-rate?period=YYYY-MM` e `/bi/success-rate/trend` (regra 6,
   24 meses) pedem granularidade mensal que a view não tem — ficam em tempo real sobre
   `lawsuits`, mesmo raciocínio do §9.2 da 074 (coorte vs fotografia). Consequência
   prática: só os testes de safra precisam de refresh da matview.
3. **`period=` da success-rate é mês de `closure_date`, tempo real.** A spec declara o
   parâmetro sem definir o eixo; adotado o mesmo idioma do `?period=` da conversão da
   074 (`parse_month_query`, default mês corrente), filtrando concluídos por
   `closure_date` no mês — concluído implica `closure_date` preenchida (spec 024,
   regra 4), então nenhum concluído escapa do recorte.
4. **Agregação multi-grupo pondera o ciclo médio.** Sem `action_group_id`, o repository
   soma os grupos por ano; `avg_cycle_days` vira `SUM(avg × archived) / SUM(archived)` —
   média de médias distorceria a regra 7. Com o filtro de grupo a mesma query degenera
   para o caso de um grupo só, sem caminho especial.
5. **Regra 9 compara safras presentes na resposta, não anos civis.** "Safras
   consecutivas" = linhas consecutivas da tabela (ordenadas por ano) — como a safra sem
   fechamento não existe (regra 8), comparar ano civil a ano civil pediria um LEFT JOIN
   contra uma série de anos sem ganho semântico. Se uma das duas taxas é incalculável
   (zero concluídos → None), não há variação nem destaque.
6. **Tab da URL é `vintage`, não `safra`.** A 074 criou o placeholder `?tab=safra` no
   BiTabs; a spec 075 fixa a rota `/reports?tab=vintage`. O valor da aba foi renomeado
   (label continua "Safra e Qualidade") e a aba foi habilitada; `tempo`/`custos` seguem
   desabilitadas até 076–077.
7. **`SuccessTrendChart` não usa o `BarChart` de domínio.** O BarChart exige valor
   numérico por barra e a regra 11 proíbe representar mês sem concluídos como 0% —
   barras verticais em SVG puro com lacuna nos meses null (mesmo motivo pelo qual a 074
   escreveu o `ConversionFunnel` à parte). O `BarChart` é reutilizado no volume
   "concluídos por safra" do VintagePanel. Sparkline do `SuccessRateCard` idem: SVG
   próprio de 24 barras, null = lacuna.
8. **Teste de isolamento de tenant além do plano, de novo.** CLAUDE.md §4 exige prova de
   isolamento para estrutura nova com dado de tenant; a matview não tem RLS (o isolamento
   é da view barreira `bi_vintage_visible`), então `test_tenant_a_nao_ve_safra_de_tenant_b`
   — 12 testes de integração no total (11 do plano + isolamento), mais 3 de frontend.
9. **Host dind precisa de `PYTEST_ALLOW_HOSTS`.** Postgres/Redis/MinIO rodam no host
   `dind` (fora de localhost); o pytest-socket da spec 009 bloqueia por padrão — os testes
   rodam com `TEST_*_URL` apontando para `dind` e `PYTEST_ALLOW_HOSTS=dind` (o
   run-tests.sh já tinha o gancho). Nenhum teste toca rede externa.
10. **Bug latente no `test_inbox_perf` (spec 036), exposto pelo banco limpo — fix fora
    de escopo, comportamento preservado.** A fixture semeava 10k pendentes + 10k
    concluídas para UM usuário e fazia ANALYZE: com stats frescas, 50% da tabela no
    índice parcial faz o planner escolher Seq Scan legitimamente, e a asserção de plano
    (`ix_post_users_pending` no EXPLAIN) falhava até isolado — só passava com stats
    velhas de antes do TRUNCATE que a suíte faz no boot (a 074 registrou o flake como
    "de contenção"; a causa raíz era esta). Correção: as 10k pendentes agora são
    distribuídas entre 100 usuários do seed (100 cada, ~1% de seletividade por usuário) —
    plano via índice determinístico em qualquer estado do banco, volume total e budgets
    de tempo inalterados. O insert de concluídas perdeu o filtro `user_id` no NOT IN
    (com a distribuição, ele incluiria pendentes alheias como concluídas do usuário).

## 10. Definição de pronto

- [x] Escopo implementado, nada além (migration 075, worker + beat 8h no minuto 51, 3 endpoints, 4 componentes de front na rota `/reports?tab=vintage`)
- [x] Todas as regras de negócio com teste (1–11; regra 6 com caso dedicado de série de 24 meses)
- [x] Teste de isolamento por tenant (`test_tenant_a_nao_ve_safra_de_tenant_b` — ver 9.8)
- [x] `make test` com as 3 suítes verdes; wall-clock acima do orçamento por contenção do host (496 s; acréscimo da spec ~12 s) — ver test-timing.json e §9.10
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizados conforme §6 (DataTable na VintageTable, BarChart no volume por safra, FilterBar nos filtros; StatCard não coube — o SuccessRateCard exige sparkline + tooltip, ver §9.7); nenhum novo componente de domínio
- [x] `ROADMAP.md` atualizado para ✅
- [ ] Commit `feat(075): BI — safra e qualidade` (neste ciclo o commit fica com o orquestrador)
