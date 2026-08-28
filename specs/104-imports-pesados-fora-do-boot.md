# 104 — Imports pesados fora do caminho de import

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** −0 s (alvo: reduzir; não pode subir)
**Depende de:** 011, 041, 065, 066, 067, 088 · **Status:** ⬜ pendente

---

## 1. Objetivo

Tirar do caminho de import cinco bibliotecas pesadas que hoje são carregadas em todo processo
que toca a aplicação, e que a maioria dos testes nunca usa. Depois desta spec, subir um worker
de teste custa menos, e o custo que sobra é o da aplicação, não o de um gerador de PDF que
ninguém chamou.

> Refatoração: **nenhuma mudança de comportamento**. Todos os testes anteriores passam sem
> edição, incluindo os de geração de PDF, export, upload e guarda de SQL.

## 2. Escopo

Medido em 28/08/2026, no commit `44469bd`: `import app.main` custa **13,1 s** e a coleta do
pytest custa **17,5 s** — e cada worker do `-n 3` paga os dois, independentemente, antes do
primeiro assert.

Cinco módulos, todos folhas isoladas: a biblioteca é usada dentro de uma função, nunca em
tempo de import.

| Arquivo | Import a mover | Usado em | Observação |
|---|---|---|---|
| `app/domain/templates/pdf.py:8` | `from xhtml2pdf import pisa` | linha 33 | trivial: uma chamada, uma função |
| `app/core/export.py:14-15` | `from fpdf import FPDF`, `from openpyxl import Workbook` | linhas 49 e 36 | duas funções distintas, um import em cada |
| `app/integrations/storage/s3.py:3` | `import boto3` | linha 29 (`__init__`) | trivial |
| `app/domain/templates/variables.py:14` | `from num2words import num2words` | linhas 47, 49, 61 | três funções; um import em cada |
| `app/domain/ai/sql_guard.py:14-15` | `import sqlglot`, `from sqlglot import exp` | linhas 67, 75, 89, 101, 106 | **não é trivial** — ver regra 4 |

## 3. Fora de escopo

- Reduzir o tempo de **coleta** do pytest por outros meios (importar menos em `tests/`) — some
  junto com este trabalho ou vira spec própria depois de medido.
- Qualquer outra biblioteca. Se durante a implementação aparecer uma sexta, anote em
  `## 9. Descobertas` e siga.
- Trocar `xhtml2pdf`, `fpdf` ou `openpyxl` por alternativa mais leve. Outra discussão.
- `langgraph` já custa 163 µs no topo (`app/ai/graphs/base_agent.py:15`) — não é alvo.

## 4. Modelo de dados

Nenhuma tabela nova, nenhuma coluna, nenhuma migration.

## 5. Contratos de API

Nenhum contrato muda. Nenhuma rota entra, sai ou altera resposta — é exatamente isso que os
testes existentes provam ao continuarem passando sem edição.

## 6. Front-end

Nada.

## 7. Regras de negócio

1. Nenhuma das cinco bibliotecas é importada em tempo de import de módulo. O import vive
   dentro da função que a usa, na primeira linha do corpo.
2. Nenhum comportamento muda: a primeira chamada a cada função paga o import, as seguintes
   pegam do `sys.modules`. Nenhuma função vira mais lenta de forma observável em teste.
3. Nenhum `# type: ignore` novo. `mypy --strict` continua verde sem exceção nova no
   `pyproject.toml`.
4. `sql_guard.py` é o caso especial: `exp.Expression` aparece em **anotação de assinatura**
   (linhas 67 e 101), e o projeto não usa `from __future__ import annotations` em arquivo
   nenhum (0 de 445). Mover o import para dentro da função quebraria a resolução dessas
   anotações em runtime. A forma correta é a combinação padrão:
   `from __future__ import annotations` no topo do arquivo, `if TYPE_CHECKING: from sqlglot
   import exp` para o que é só tipo, e `import sqlglot` dentro de `parse`/`_relations` para o
   que é execução.
5. Um meta-teste garante que a regra 1 continua valendo. Ele verifica **estrutura, não
   tempo**: parseia o AST dos cinco módulos e falha se algum dos nomes voltar para o topo.
   Tempo de import medido em CI compartilhado oscila e viraria teste instável — o mesmo
   raciocínio que a 098 usou para tirar o perfilamento de volume do PR.
6. Se a família `PL` completa for ligada numa spec futura, `PLC0415` (import fora do topo)
   entra em conflito direto com esta spec. Os cinco módulos vão para a lista de exceção do
   `pyproject.toml`, com o número desta spec no comentário.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | os cinco módulos não importam a lib pesada no topo (AST) | `tests/meta/test_imports_pesados.py` | ~0,1 s |
| meta | cada módulo ainda importa a lib em algum lugar — pega o import apagado por engano | `tests/meta/test_imports_pesados.py` | ~0,1 s |
| — | geração de PDF, export xlsx/pdf, upload S3 e guarda de SQL continuam cobertos pelos testes das specs 011, 066, 067 e 088, **sem edição** | — | 0 s |

**Total estimado:** +0,2 s
**Fixtures externas:** nenhuma.

### Medição de aceite (fora da suíte)

Rodar antes e depois, na mesma máquina, e registrar os dois números em `## 9. Descobertas`:

```bash
cd backend && uv run python -X importtime -c "import app.main" 2>&1 | tail -1
cd backend && uv run pytest --collect-only -q 2>&1 | tail -2
```

Alvo: `import app.main` **abaixo de 9 s** (hoje 13,1 s). O wall-clock de `make test`
**não pode subir** — se subir, algo além de import mudou.

## 9. Descobertas

Preencher durante a implementação.

## 10. Definição de pronto

- [ ] Os cinco imports movidos, nenhum sexto tocado
- [ ] `sql_guard.py` com `from __future__ import annotations` + `TYPE_CHECKING`
- [ ] Meta-teste em `tests/meta/test_imports_pesados.py`, verde
- [ ] `import app.main` medido antes/depois e registrado em §9
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento (CLAUDE.md §3)
- [ ] `make lint` verde — repositório inteiro, não só os arquivos tocados
- [ ] Sem `Any`, `as any` ou `# type: ignore` novo
- [ ] `ROADMAP.md` com a linha da 104 em ✅
- [ ] Commit `refactor(104): imports pesados fora do boot`
