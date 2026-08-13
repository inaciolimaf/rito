# 068 — Biblioteca pública de modelos

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 064 · **Status:** ✅ concluída

---

## 1. Objetivo

A biblioteca do escritório (spec 064) só tem o que o próprio tenant criou. O
levantamento pede uma 2ª aba — "Biblioteca Pública" — com modelos prontos, iguais
para todo escritório, que qualquer um pode copiar como ponto de partida.

## 2. Escopo

- Catálogo global de modelos públicos — taxonomia imutável, mesmo padrão de
  `Court`/`Occupation`/`Step` (sem `tenant_id`, sem RLS, sem CRUD por tenant, seedado
  uma vez).
- Listagem com filtro por tipo (mesmos 4 tipos da spec 064).
- Copiar um modelo público para os modelos do escritório — a cópia é um `Template`
  normal do tenant (regra: editável, some da lixeira/duplicação como qualquer outro).

## 3. Fora de escopo

- CRUD do catálogo público pela UI — quem mantém a biblioteca pública é o próprio
  Rito (seed), não o usuário do tenant; o levantamento não pede um editor disso.
- Avaliação/favoritos/busca por popularidade — o levantamento só pede filtro por
  tipo, igual à biblioteca do escritório.

## 4. Modelo de dados

```sql
CREATE TABLE public_templates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  type TEXT NOT NULL,              -- mesmos 4 valores de template_type
  content TEXT NOT NULL DEFAULT '',
  header_content TEXT NOT NULL DEFAULT '',
  footer_content TEXT NOT NULL DEFAULT '',
  watermark_text TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
Sem `tenant_id`, sem RLS — catálogo global (mesmo padrão de `courts`/`occupations`).
Migration `068_public_templates.py`, seedando 6 modelos (2 contratos, 2 petições, 1
recurso, 1 documento) com conteúdo real de exemplo.

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/public-templates?type=` | query | `200 [template]` | autenticado |
| POST | `/api/v1/public-templates/{id}/copy` | — | `201 template` (schema da spec 064) | autenticado |

Erros: `404` (modelo público inexistente).

## 6. Front-end

**Componentes reutilizados:** `TabBar` (spec 070), `DataTable`.
**Componentes criados:** nenhum — a aba nova é uma variação de listagem que já usa o
mesmo esqueleto da biblioteca do escritório.
**Rotas:** nenhuma nova — 2ª aba em `/library` ("Meus modelos" / "Biblioteca
Pública", `?tab=public`).
**Estados:** loading, vazio, erro; "copiado" (toast/mensagem curta antes de navegar
pro modelo copiado).

## 7. Regras de negócio

1. Biblioteca pública é a mesma para todo tenant — sem filtro de tenant (não tem
   `tenant_id` na tabela).
2. Copiar cria um `Template` novo do tenant atual, com `deleted_at = NULL` — a cópia
   é um modelo comum, editável e sujeito às mesmas regras da spec 064 (lixeira,
   duplicar, etc.) dali em diante.
3. Copiar não altera o modelo público de origem — a mesma origem pode ser copiada
   várias vezes, por vários tenants, sem afetar uns aos outros.
4. Nome da cópia é igual ao do modelo público de origem (sem sufixo) — diferente de
   "fazer cópia" (spec 064, regra 6, que sufixa "(cópia)"): aqui é a **primeira**
   cópia de um modelo de outro lugar, não uma duplicata de um modelo que o tenant já
   tem.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | lista modelos públicos e filtra por tipo | `tests/integration/test_public_templates.py` | ~0,3 s |
| integração | copiar cria modelo editável do tenant, sem sufixo no nome | idem | ~0,3 s |
| integração | copiar duas vezes por tenants diferentes não interfere entre si | idem | ~0,3 s |
| integração | copiar modelo público inexistente → 404 | idem | ~0,2 s |
| frontend | troca para "Biblioteca Pública" e copia um modelo | `src/features/templates/*.test.tsx` | ~0,3 s |

**Total estimado:** ~1,4 s
**Fixtures externas:** nenhuma.

## 9. Descobertas

- A migration desta spec ficou depois da 070 na cadeia real de aplicação (`Revises:
  070_documents_templates_indexes`) — a refatoração foi antecipada nesta sessão pra
  recuperar orçamento de suíte (ver Descobertas da 067) antes de reabrir a fase 6 com
  spec de feature nova. A ordem numérica das specs continua 067→068→069→070 no
  `ROADMAP.md`; só a cadeia de migrations no banco reflete a ordem real de execução.
  Comentário deixado no topo do arquivo de migration pra não confundir quem ler
  depois.
- `TabBar` (extraído na 070) já paga a segunda utilização aqui — a 3ª aba de biblioteca
  (mine/pública) e a de escopo do processo (spec 065) confirmam que a extração era
  legítima antes mesmo de qualquer 3º caso surgir de fato.
- `test_inbox_perf.py` (spec não relacionada) flakou uma vez sob carga concorrente
  durante a suíte completa desta spec e passou isolado — mesmo padrão de
  ambiente compartilhado já registrado nas Descobertas da 066, não uma regressão.

## 9.1. Perfil de acesso da biblioteca pública

Qualquer usuário autenticado (`require_role(COLABORADOR)`) lê e copia — o catálogo é
público *entre tenants do mesmo Rito*, não editável por ninguém fora do seed da
migration, então não há necessidade de uma trava de perfil mais alta.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock < 300 s (292 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(068): biblioteca pública de modelos`
