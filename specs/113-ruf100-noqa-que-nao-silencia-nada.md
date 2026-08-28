# 113 — RUF100: noqa que não silencia nada

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 107, 108, 109, 111, 112 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar `RUF100` e apagar as 31 diretivas `# noqa` que não silenciam mais nada. Supressão morta
é pior que ruído: ela documenta um problema que não existe, e treina quem lê o código a
ignorar `noqa` — inclusive os que estão segurando algo de verdade.

> Refatoração: nenhuma mudança de comportamento. Só comentários saem.

## 2. Escopo

`pyproject.toml`: `select` ganha `RUF100`.

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **31 violações**, todas com
correção automática (`ruff check --fix`).

| Onde | Qtd. | Códigos silenciados que não estão ligados |
|---|---|---|
| `app/core/observability/*` | 6 | `ANN401`, `ANN001`, `E501`, `BLE001` |
| `app/core/cache.py` | 4 | `ANN401`, `BLE001` |
| `app/domain/automations/*` | 4 | `BLE001` |
| `app/core/migrations.py` | 2 | `BLE001` |
| `app/domain/{financial,templates}/router.py` | 2 | `A002` |
| `app/workers/celery_app.py` | 1 | `F401` |
| `tests/integration/*` | 9 | `F401`, `ANN001`, `S608` |
| `tests/meta/test_ai_guardrails.py` | 2 | `SLF001` |
| `tests/perf.py` | 1 | `ANN001`, `E501` |

## 3. A armadilha desta spec — leia antes de rodar `--fix`

`RUF100` diz «este `noqa` é inútil **dadas as regras ligadas hoje**». Três dos códigos
suprimidos estão programados para serem ligados por specs desta mesma leva:

- **`S608`** em `tests/integration/test_post_comments.py:452` — a spec 115 liga a família `S`.
  Apagar aqui e reintroduzir lá é trabalho ao quadrado, e pior: se a 115 não olhar essa linha,
  ela vai aparecer como violação nova sem contexto.

A ordem escolhida para a leva resolve isso de propósito: esta spec vem **antes** da 115, e a
115 tem no escopo reavaliar essa linha específica. A regra 3 abaixo torna isso obrigatório em
vez de esperar que alguém lembre.

`ANN*`, `BLE001`, `A002` e `SLF001` **não** estão programados para nenhuma spec desta leva —
esses saem sem ressalva.

## 4. Fora de escopo

- Ligar `ANN`, `BLE`, `A` ou `SLF`. Se alguma dessas famílias merecer gate, é spec própria —
  e a decisão fica mais fácil depois desta, porque o inventário acima mostra onde elas
  doeriam.
- `eslint-disable` órfão no frontend. Spec futura.

## 5. Modelo de dados / API / Front-end

Nada.

## 6. Regras de negócio

1. `RUF100` no `select`.
2. As 31 diretivas saem. `ruff check --fix` resolve todas; conferir o diff antes de commitar,
   porque `--fix` também mexeria em outras regras se rodado sem `--select`.
3. **A linha `tests/integration/test_post_comments.py:452` é registrada em `## 8. Descobertas`
   com o texto original do `noqa`**, e a spec 115 cita esta spec ao reavaliá-la. Nenhuma das
   duas fica dependendo da memória de quem implementa.
4. Nenhum `noqa` novo é criado por esta spec.
5. Depois desta spec, todo `# noqa` que sobrar no projeto está segurando algo de verdade — e o
   `test_final_audit.py`, estendido pela 106, exige justificativa em todos eles.

## 7. Plano de testes

Nenhum teste novo. O gate é o `make lint`.

```bash
cd backend && uv run ruff check . --select RUF100
```

**Total estimado:** +0 s

## 8. Descobertas

Preencher durante a implementação. **Obrigatório:** o texto original do `noqa` de
`tests/integration/test_post_comments.py:452` e por que ele existia.

## 9. Definição de pronto

- [ ] `RUF100` no `select`
- [ ] As 31 diretivas removidas
- [ ] Diff conferido: só comentários saíram, nenhuma linha de código mudou
- [ ] `noqa` de `test_post_comments.py:452` registrado em §8 para a spec 115
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 113 em ✅
- [ ] Commit `refactor(113): remove noqa que não silencia nada`
