# 108 — ASYNC: I/O bloqueante dentro de corrotina

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 091 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar a família `ASYNC` do Ruff, que pega a classe de bug mais silenciosa de um backend
async: chamada bloqueante dentro de `async def`. Nada estoura — o event loop simplesmente
para, e a latência de **todas** as requisições em voo sobe junto. Num backend FastAPI com
worker Celery, é o tipo de coisa que só aparece sob carga, quando é caro descobrir.

> Refatoração: nenhuma mudança de comportamento observável. Muda quem espera.

## 2. Escopo

`pyproject.toml`, `[tool.ruff.lint]`: `select` ganha `ASYNC`.

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **2 violações**, ambas
`ASYNC240` (método de `pathlib.Path` dentro de corrotina).

| Arquivo:linha | Contexto |
|---|---|
| `app/integrations/ocr/tesseract.py:61` | OCR de documento (spec 091) — código de produção |
| `tests/unit/test_openrouter_client.py:173` | leitura de fixture gravada dentro de teste async |

## 3. Como corrigir cada uma

**`tesseract.py:61`** é a que importa. A integração de OCR já roda uma chamada externa; o
acesso a disco dentro da mesma corrotina bloqueia o loop pelo tempo do IO. As duas saídas
legítimas:

- `anyio.Path`, se a operação é pontual — troca direta, mesma semântica;
- `anyio.to_thread.run_sync(...)`, se o bloco de IO é maior — é o mesmo padrão que
  `integrations/storage/s3.py` já usa para o boto3 síncrono, então não é padrão novo no
  projeto, é o padrão existente aplicado onde faltou.

Escolher olhando o código: se for uma leitura/escrita isolada, `anyio.Path`; se for um bloco,
`to_thread`.

**`test_openrouter_client.py:173`** é teste. Lê fixture do disco dentro de um teste async.
Bloquear o loop num teste não tem consequência de produção — mas silenciar por arquivo abriria
a porta para o próximo. Corrigir do mesmo jeito é mais barato que discutir a exceção.

## 4. Fora de escopo

- Auditar chamadas bloqueantes que o `ASYNC` **não** pega (`time.sleep`, `requests`, driver
  síncrono). O `test_no_network.py` já cobre parte disso, e o resto é spec própria.
- Trocar o `boto3` síncrono por cliente async. Ele já está atrás de `to_thread`.

## 5. Modelo de dados / API / Front-end

Nada.

## 6. Regras de negócio

1. `ASYNC` no `select` do Ruff. `make lint` reprova.
2. `tesseract.py` usa `anyio.Path` ou `anyio.to_thread.run_sync`. Nunca `pathlib` cru dentro
   de `async def`.
3. Comportamento idêntico: os testes de extração da spec 091 passam sem edição.
4. Nenhum `# noqa: ASYNC*` no projeto. Duas ocorrências não justificam abrir exceção.

## 7. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| — | testes de OCR/extração da spec 091 passam sem edição | — | — |

Verificação de aceite:

```bash
cd backend && uv run ruff check . --select ASYNC
```

**Total estimado:** +0 s

## 8. Descobertas

Preencher durante a implementação.

## 9. Definição de pronto

- [ ] `ASYNC` no `select`
- [ ] `ruff check . --select ASYNC` limpo, sem `noqa`
- [ ] Testes da spec 091 passam sem edição
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 108 em ✅
- [ ] Commit `refactor(108): I/O bloqueante fora das corrotinas`
