# 075 — BI: Safra e Qualidade

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 074 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Critério da taxa explícito na UI · Commit `feat(075): BI — safra e qualidade`
