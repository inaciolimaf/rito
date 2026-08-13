# 070 — 🔧 REFATORAÇÃO — Documentos e Modelos

**Fase:** 6 · **Tipo:** refatoração · **Depende de:** 061–067 · **Status:** ✅ concluída

---

## 1. Objetivo

Pente fino nas specs desde a última refatoração (060): inadimplência (061),
relatórios DRE/DFC (062), documentos e nuvem (063), e o arco completo de modelos
(064–067). Sem mudar comportamento.

## 2. Escopo

- Duplicação (regra dos 3 usos): barra de abas (`role="tablist"`) repetida em 6 telas
  → extraída para `components/domain/TabBar`.
- Duplicação em teste: `_auth_header` redefinida em cada arquivo de teste das specs
  062–067 → função compartilhada `auth_header` em `tests/integration/conftest.py`.
- Índice faltando: `document_folders.parent_folder_id` (usado pela cascata de
  exclusão, spec 063 regra 4) não tinha índice — a única constraint composta da
  tabela não cobre uma busca só por essa coluna.
- Auditoria de tipos frouxos (`Any`/`as any`/`# type: ignore`) e de SOLID (router com
  query, service acoplado a integração) nas specs 061–067: nada encontrado além do
  já documentado (spec 063, `Any` justificado em teste).

## 3. Fora de escopo

- O item de performance já registrado em `docs/DIVIDA-TECNICA.md` (item 17: custo de
  boot de engine por teste, investigado nas specs 033/050, formalmente atribuído à
  098) — não reaberto aqui; a recomendação documentada é não tentar de novo sem uma
  hipótese nova, e dividir a suíte em grupos paralelos é mudança de tooling de CI,
  não pente fino de código.
- Migration de merge de `deleted_at`/soft-delete entre `templates` (064) e
  `document_folders`/`documents` (063) — os dois already seguem o mesmo padrão onde
  faz sentido (lixeira só em `templates`, que é a única com essa necessidade real).

## 4. Modelo de dados

```sql
CREATE INDEX ix_document_folders_parent ON document_folders (parent_folder_id)
  WHERE parent_folder_id IS NOT NULL;
```
Migration `070_documents_templates_indexes.py`.

## 5. Contratos de API

Nenhuma mudança — refatoração não altera contrato observável.

## 6. Front-end

**Componente extraído:** `TabBar` (`components/domain/TabBar.tsx`) — genérico sobre o
tipo da aba, recebe `items`/`active`/`onSelect`; cada tela continua dona da própria
lógica de `useSearchParams`. Migradas: `UsersSettingsPage`, `FinancialSettingsPage`,
`TransactionsListPage`, `LawsuitDetailPage`, `FinancialReportPage`, `InboxPage`.

## 7. Regras de negócio

Refatoração não muda comportamento — nenhuma regra nova. A verificação é que os
testes existentes (specs 061–067) continuam passando sem edição de asserção (só a
plumbing de `_auth_header` → `auth_header` mudou, não o que cada teste verifica).

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| frontend | `TabBar` marca a aba ativa e avisa a escolha (novo, cobre o componente extraído) | `src/components/domain/TabBar.test.tsx` | ~0,1 s |
| regressão | as 44 integrações de 062–067 seguem verdes com `auth_header` compartilhada | `tests/integration/test_{financial_reports,documents,templates,template_editor,template_resolve,template_generate}.py` | já contado |
| regressão | as 31 telas de 062–067 seguem verdes com `TabBar` | `src/features/{financial,lawsuits,users,inbox,templates,documents}/*.test.tsx` | já contado |

**Total estimado:** ~0,1 s novo (o resto é regressão do que já existia).

## 9. Descobertas

- O item de performance (custo de boot por teste, `docs/DIVIDA-TECNICA.md` #17)
  segue como estava: **não é** um alvo produtivo pra pente fino de código — já
  investigado duas vezes (033, 050), reatribuído formalmente à 098 com a
  recomendação de dividir a suíte em grupos paralelos (mudança de CI/tooling, não de
  código de domínio). Esta spec não reabriu essa frente.
- Wall-clock não mudou de forma perceptível (a extração de duplicação — `TabBar` e
  `auth_header` — reduz linhas de código, não o número de testes nem o custo de boot
  por teste, que é o que domina o tempo). O orçamento continua apertado; **a spec 068
  precisa manter os testes novos mínimos**, como já vinha sendo feito desde a 065.
- 20 arquivos de teste anteriores a 062 ainda redefinem `_auth_header` localmente —
  fora do escopo desta spec (que audita 061–067); fica registrado para uma futura
  refatoração pegar o resto, se algum dia compensar tocar esse tanto de arquivo de
  uma vez.

## 10. Definição de pronto

- [x] Sem mudança de comportamento observável
- [x] Testes existentes (061–067) passam sem edição de asserção
- [x] `make test` verde e wall-clock < 300 s
- [x] `make lint` verde
- [x] Duplicação de 3+ usos extraída (`TabBar`, `auth_header`)
- [x] Índice faltando corrigido (`ix_document_folders_parent`)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `refactor(070): documentos e modelos`
