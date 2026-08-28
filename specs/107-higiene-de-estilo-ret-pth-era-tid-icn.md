# 107 — Higiene de estilo: RET, PTH, ERA, TID, ICN

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** — · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar cinco famílias de regra do Ruff que o projeto já respeita sem saber, travando o
comportamento atual antes que ele se perca. É o gate mais barato de toda a leva: quatro das
cinco famílias têm **zero** violações hoje.

> Refatoração: nenhuma mudança de comportamento.

## 2. Escopo

`pyproject.toml`, `[tool.ruff.lint]`: `select` ganha `RET`, `PTH`, `ERA`, `TID`, `ICN`.

Medido em 28/08/2026, commit `44469bd`, sobre o escopo real do `make lint`
(`ruff check .` dentro de `backend/`, que inclui `app/`, `tests/`, `alembic/` e `scripts/`):

| Família | O que pega | Violações |
|---|---|---|
| `RET` | `return` redundante, `else` depois de `return`, variável de retorno inútil | 0 |
| `PTH` | `os.path` onde `pathlib` serve | 0 |
| `TID` | import relativo solto, import banido | 0 |
| `ICN` | apelido de import fora da convenção | 0 |
| `ERA` | código-fonte comentado | **2** |

As duas de `ERA001` estão em migrations já commitadas:

```
alembic/versions/054_chart_of_accounts.py:30
alembic/versions/088_editor_ai.py:49
```

## 3. Conflito com o CLAUDE.md §9 — e como resolver

O §9 é explícito: **«Nunca editar migration já commitada.»** Apagar um comentário não muda o
que a migration faz, mas a regra não abre exceção por tamanho da mudança, e ela existe
justamente porque «é só um comentário» é como toda edição de migration começa.

A resolução é declarar a exceção onde ela pertence, no `pyproject.toml`:

```toml
[tool.ruff.lint.per-file-ignores]
# CLAUDE.md §9: migration commitada não se edita. As duas ocorrências de ERA001
# (054:30, 088:49) são anteriores a esta spec e ficam onde estão — o ganho de
# apagá-las não paga o precedente de mexer em migration aplicada.
"alembic/versions/*.py" = ["ERA001"]
```

Isso mantém `ERA001` valendo para `app/`, `tests/` e `scripts/`, que é onde código comentado
de fato apodrece.

## 4. Fora de escopo

- Qualquer outra família de regra. Cada uma tem spec própria nesta leva.
- Migrar `os.path` para `pathlib` — não há o que migrar, `PTH` já está limpo.
- `ERA001` no frontend (ESLint). Spec futura.

## 5. Modelo de dados / API / Front-end

Nada.

## 6. Regras de negócio

1. `RET`, `PTH`, `ERA`, `TID`, `ICN` no `select` do Ruff. `make lint` reprova, não avisa.
2. `per-file-ignores` para `ERA001` em `alembic/versions/*.py`, com o comentário citando o
   §9 — a exceção precisa dizer por que existe, ou vira uma exceção que ninguém revisita.
3. Nenhum arquivo de `app/`, `tests/` ou `scripts/` ganha exceção.
4. Nenhuma linha de código muda. Se alguma mudar, alguma das quatro famílias «zeradas» não
   estava zerada — registre em `## 9. Descobertas` antes de corrigir.

## 7. Plano de testes

Nenhum teste novo. O gate é o `make lint` do CI, que já roda em todo PR.

A verificação de aceite é uma linha:

```bash
cd backend && uv run ruff check . --select RET,PTH,ERA,TID,ICN
```

**Total estimado:** +0 s

## 8. Descobertas

Preencher durante a implementação.

## 9. Definição de pronto

- [ ] As cinco famílias no `select` do `pyproject.toml`
- [ ] `per-file-ignores` de `ERA001` para `alembic/versions/*.py`, com justificativa
- [ ] `ruff check .` limpo para as cinco
- [ ] Nenhuma linha de `app/`, `tests/` ou `scripts/` alterada
- [ ] `make test` verde (não deveria ser afetado — se for, algo mais mudou)
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 107 em ✅
- [ ] Commit `refactor(107): higiene de estilo — RET, PTH, ERA, TID, ICN`
