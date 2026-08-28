# 115 — Bandit (S): a superfície de segurança que o lint alcança

**Fase:** 11 · **Tipo:** correção · **Orçamento:** +0,5 s
**Depende de:** 113 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar a família `S` (bandit) do Ruff. Ela não substitui o `security-review` nem os
meta-testes de RLS e RBAC que já existem — ela pega a fatia que dá para pegar lendo o código:
SQL montado por concatenação, segredo literal, `assert` usado como validação, subprocess com
caminho parcial.

> Muda comportamento em um ponto (regra 4, os 44 `assert` de produção). O resto é forma.

## 2. O problema de escala — e por que ele tem uma resposta certa

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **3.880 violações**. Desse
total, **3.827 são `S101` (`assert`)**, e 3.781 delas estão em `tests/`.

Isso não é um achado, é uma característica da regra: `S101` existe porque `assert` some sob
`python -O`, o que é irrelevante num teste — a suíte inteira é feita de `assert`. Ligar `S`
sem tratar isso reprovaria todo PR para sempre, e a reação previsível seria desligar `S`.

A resposta padrão, e a única defensável:

```toml
[tool.ruff.lint.per-file-ignores]
# S101: `assert` É a interface do pytest. A regra existe para código que roda sob
# `python -O`, o que nunca é o caso aqui.
"tests/**/*.py" = ["S101"]
"scripts/*.py" = ["S101"]
```

Sobram **53 violações reais**, que são o escopo de verdade desta spec.

## 3. Escopo — as 53 que sobram

| Regra | Qtd. | Onde | Leitura |
|---|---|---|---|
| `S101` | 44 | `app/` | `assert` em código de produção — ver regra 4 |
| `S608` | 37 | `app/` (9), `alembic/versions/` (8), `scripts/` (2), `tests/` (18) | SQL por string |
| `S105`/`S106`/`S107` | 8 | `core/bootstrap.py`, `domain/api_tokens/service.py`, testes | falso positivo de nome de constante |
| `S603`/`S607` | 6 | `app/cli.py` | `subprocess` do comando `rito backup` |
| `S112` | 1 | `core/observability/metrics.py:128` | `try/except/continue` sem log |
| `S311` | 1 | `integrations/http/client.py:67` | `random` no jitter de backoff |

## 4. Como tratar cada grupo

**`S101` em `app/` (44).** Este é o grupo que muda comportamento, e é o mais importante da
spec. `assert` em produção some sob `python -O` — a validação simplesmente deixa de existir,
silenciosamente. As 5 de `integrations/storage/s3.py`, 4 de `domain/financial/service.py` e 3
de `core/errors.py` precisam de triagem individual, e cada uma cai num de dois baldes:

- **invariante de programador** (o tipo já garante, é documentação) → vira comentário ou some;
- **validação de dado** → vira `raise` de erro do domínio, com o tipo certo.

Nenhuma vira `# noqa`.

**`S608` (37).** Nenhuma é injeção: são `text(f"...")` com nome de tabela vindo de constante
ou de catálogo do próprio Postgres. Mas o inventário se divide em três destinos diferentes:

- `app/` (9, em `core/provisioning.py`, `core/migrations.py`, `workers/aggregates.py`) —
  interpolação de **identificador**, que parâmetro de bind não resolve. A correção é passar
  por uma função de quoting explícita e centralizada, o que também documenta a intenção;
- `alembic/versions/` (8) — `CLAUDE.md` §9 proíbe editar migration commitada.
  `per-file-ignores`, com o §9 citado no comentário;
- `tests/` (18) e `scripts/` (2) — `per-file-ignores`, mesma justificativa de `S101`.

**`S105`/`S106`/`S107` (8).** Falso positivo clássico: a regra dispara pelo *nome* da
variável. `EXAMPLE_SECRET_KEY` (`core/bootstrap.py:24`) e `TOKEN_PREFIX`
(`domain/api_tokens/service.py:23`) não são segredos. `# noqa: S105` com justificativa — este
é o uso legítimo de `noqa`, e o `test_final_audit.py` (estendido pela 106) já exige o texto.

**`S603`/`S607` (6, `app/cli.py`).** O comando `rito backup` chama `pg_dump`/`pg_restore`.
`S607` (caminho parcial) tem correção real: caminho absoluto resolvido de configuração, o que
elimina uma dependência do `PATH` do container. `S603` fica com `noqa` justificado — o
argumento não vem de entrada de usuário.

**`S112` (1).** Correção real e barata: logar a exceção antes do `continue`. O
`core/observability/metrics.py` é o último lugar do projeto onde engolir exceção em silêncio
faz sentido.

**`S311` (1).** `random` no jitter de backoff não é uso criptográfico. `noqa` justificado.

## 5. Herança da spec 113

A 113 removeu 31 `# noqa` mortos, e um deles suprimia exatamente `S608`, em
`tests/integration/test_post_comments.py:452`. Ele foi registrado na §8 daquela spec. **Ler
esse registro é a primeira tarefa desta** — com o `per-file-ignores` de `tests/**` proposto
aqui, ele provavelmente não precisa voltar, e essa conclusão tem que ser escrita, não
presumida.

## 6. Fora de escopo

- `gitleaks` / varredura de segredo no histórico. Gate próprio, spec futura.
- Revisão de segurança de arquitetura — RLS, RBAC, SSRF, upload. Já coberto pela 100 §3 e
  pelos meta-testes.
- `pip-audit`/`npm audit`, que já rodam em todo PR.

## 7. Modelo de dados / API / Front-end

Nada. As 44 conversões de `assert` para `raise` podem mudar o **código de status** de casos
que hoje estourariam como 500 — e devem: um dado inválido merece 422, não 500. As afetadas vão
listadas em `## 9. Descobertas`.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | nenhum `assert` em `app/` (AST) | `tests/meta/test_final_audit.py` (estende) | ~0,2 s |
| meta | todo `# noqa: S*` tem justificativa na linha acima | `tests/meta/test_final_audit.py` (estende) | ~0,1 s |
| integração | as validações que viraram `raise` devolvem o status certo, não 500 | conforme a triagem da regra 4 | ~0,4 s |
| — | testes das specs de origem passam sem edição, exceto os listados em §9 | — | — |

**Total estimado:** +0,7 s

## 9. Descobertas

Preencher durante a implementação. **Obrigatório:** a triagem das 44 `assert` (qual virou
`raise`, qual sumiu) e a conclusão sobre o `noqa` herdado da 113.

## 10. Definição de pronto

- [ ] `S` no `select`, com `per-file-ignores` de `S101` para `tests/` e `scripts/`
- [ ] `per-file-ignores` de `S608` para `alembic/versions/`, citando o §9
- [ ] As 44 `assert` de `app/` triadas: nenhuma vira `noqa`
- [ ] Quoting de identificador centralizado para os 9 `S608` de `app/`
- [ ] `pg_dump`/`pg_restore` por caminho absoluto de configuração
- [ ] `S112` logando antes do `continue`
- [ ] Todo `noqa: S*` restante com justificativa, travado por meta-teste
- [ ] Conclusão sobre o `noqa` herdado da 113 escrita em §9
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 115 em ✅
- [ ] Commit `fix(115): superfície de segurança do lint`
