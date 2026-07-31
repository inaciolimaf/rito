# NNN — Título da spec

**Fase:** N · **Tipo:** feature | refatoração · **Orçamento:** +X s no wall-clock
**Depende de:** NNN, NNN · **Status:** ⬜ pendente

---

## 1. Objetivo

Um parágrafo. O que o usuário passa a conseguir fazer depois desta spec.

## 2. Escopo

- Item entregue
- Item entregue

## 3. Fora de escopo

- Item que **não** entra aqui (e em qual spec entra)

> Fora de escopo é vinculante. Se durante a implementação surgir algo daqui,
> anote em `## 9. Descobertas` e siga — não implemente.

## 4. Modelo de dados

```sql
-- tabelas, colunas, tipos, constraints, índices
-- toda tabela de domínio: tenant_id UUID NOT NULL + RLS
```

Migration: `alembic/versions/NNN_<slug>.py`

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/...` | query params | `200 {...}` | perfil mínimo |

Erros relevantes (RFC 7807): `400`, `403`, `404`, `409`, `422`.

## 6. Front-end

**Componentes reutilizados:** `DataTable`, `FormModal`, …
**Componentes criados:** nome + por que não dá para reusar (regra dos 3 usos)
**Rotas:** `/caminho`
**Estados:** loading, vazio, erro, sem permissão

## 7. Regras de negócio

Numeradas, testáveis, sem ambiguidade. Cada uma vira ao menos um teste.

1. …
2. …

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | … | `tests/unit/...` | ~0,1 s |
| integração | … | `tests/integration/...` | ~0,5 s |
| RLS | tenant A não vê dado de tenant B | `tests/integration/test_rls_*.py` | ~0,3 s |
| frontend | … | `src/**/*.test.tsx` | ~0,2 s |
| e2e | *(só se couber no teto de 25 jornadas)* | `e2e/...` | ~2 s |

**Total estimado:** X s
**Fixtures externas:** nenhuma chamada de rede. LLM/DJEN/DataJud sempre mockados.

## 9. Descobertas

Preencher durante a implementação: problemas encontrados, decisões tomadas,
dívidas deixadas para a próxima spec de refatoração.

## 10. Definição de pronto

- [ ] Escopo implementado, nada além
- [ ] Todas as regras de negócio com teste
- [ ] Teste de isolamento por tenant (se criou tabela)
- [ ] `make test` verde e wall-clock < 120 s
- [ ] `make lint` verde
- [ ] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [ ] Componentes reutilizáveis extraídos quando bateu 3 usos
- [ ] `ROADMAP.md` atualizado para ✅
- [ ] Commit `feat(NNN): título`
