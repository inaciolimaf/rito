# 048 — Módulo Intimações

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 045, 007 · **Status:** ⬜ pendente

---

## 1. Objetivo

A tela onde a controladoria trabalha as intimações do dia: o que chegou, o que já virou tarefa,
o que ficou sem processo e precisa de vínculo manual.

## 2. Escopo

- Listagem com filtros
- Leitura do inteiro teor
- Vínculo manual a processo
- Marcação de lida
- Destaque para não vinculadas e canceladas
- Export

## 3. Fora de escopo

- IA (resumo, prazo, tarefa sugerida) → 086 · Painel de status dos termos → 049

## 4. Modelo de dados

```sql
CREATE TABLE publication_reads (
  publication_id UUID NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (publication_id, user_id)
);
```
RLS ligado. Migration `048_publication_reads.py`.

## 5. Contratos de API

```
GET /api/v1/publications
  ?interval=today|3d|7d|custom&from=&to=
  &user_id=&customer_id=&court_code=&process_number=
  &linked=true|false&cancelled=true|false&read=true|false
  &cursor=&limit=&sort=&order=
```

| Método | Rota |
|---|---|
| GET | `/api/v1/publications/{id}` — inteiro teor |
| POST | `/api/v1/publications/{id}/read` |
| POST | `/api/v1/publications/export` |
| GET | `/api/v1/publications/counts` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `EmptyState`, `EntityPicker`, `ConfirmDialog`
**Cria:** `PublicationListPage`, `PublicationDetailDrawer` (inteiro teor + metadados),
`LinkToLawsuitDialog`, `UnlinkedBanner`, `CancelledBadge`
**Rota:** `/publications`

Colunas: Data de disponibilização · Tribunal · Órgão · Processo · Partes · Responsável · Status

## 7. Regras de negócio

1. Padrão da tela: intervalo "últimos 7 dias", não vinculadas no topo.
2. Não vinculadas ganham banner de destaque com contador e ação de vínculo em massa.
3. Cancelada aparece com badge e o motivo; nunca some da lista.
4. Inteiro teor abre em drawer lateral, sem sair da lista.
5. Leitura é **por usuário** — o que um leu não marca para os outros.
6. Vínculo manual dispara o roteamento de 045 e cria a tarefa.
7. Filtro `linked=false` é o modo de trabalho da controladoria — deve ser um clique.
8. Sem termo monitorado cadastrado, a tela mostra estado vazio explicativo com link para 043.
9. Export respeita os filtros; teto de 50.000.
10. Paginação keyset por `(availability_date, id)`.
11. Busca por número de processo aceita com e sem máscara.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | filtro por intervalo (hoje, 3d, 7d, custom) | ~0,5 s |
| integração | filtro `linked=false` | ~0,3 s |
| integração | filtro por tribunal e por responsável | ~0,3 s |
| integração | busca por número com e sem máscara | ~0,3 s |
| integração | leitura é por usuário | ~0,3 s |
| integração | vínculo manual cria a tarefa | ~0,4 s |
| integração | cancelada continua listada com motivo | ~0,3 s |
| integração | contadores em query única | ~0,3 s |
| integração | keyset estável | ~0,3 s |
| frontend | drawer abre o inteiro teor | ~0,4 s |
| frontend | banner de não vinculadas com contador | ~0,3 s |
| frontend | estado vazio sem termo cadastrado | ~0,3 s |
| e2e | **jornada 7/25:** intimação chega → vincular → tarefa criada | ~5 s |

**Total:** ~9,0 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Fluxo da controladoria em 1 clique · Commit `feat(048): módulo intimações`
