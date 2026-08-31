# 104 — Imports pesados fora do caminho de import

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** −0 s (alvo: reduzir; não pode subir)
**Depende de:** 011, 041, 065, 066, 067, 088 · **Status:** ✅ concluída

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

### A linha de base da spec não reproduz — e o critério de aceite não discrimina

Os números do §2 foram medidos em 28/08/2026, no commit `44469bd`. Refeitos hoje, na
mesma máquina em que a suíte roda, com bytecode quente:

| Medida | Spec (28/08) | Antes (hoje) | Depois |
|---|---|---|---|
| `import app.main` | 13,1 s | **1,79 s** | **1,35 s** |
| `pytest --collect-only` | 17,5 s | **1,73 s** | 1,73 s |

Ou seja: o alvo declarado ("abaixo de 9 s") já estava cumprido **antes** de qualquer
linha mudar. Um critério que passa sem o trabalho não mede o trabalho, e registrar isso
importa mais do que marcar o item como atingido.

A explicação mais provável do 13,1 s é bytecode frio: repetindo a medição com
`PYTHONPYCACHEPREFIX` apontando para um diretório vazio (todo `.pyc` recompilado), este
host dá **6,62 s antes** e **3,65 s depois** — mesma ordem de grandeza, e a diferença
restante é máquina. É essa a medida que corresponde ao caso real que a spec queria
atacar: o worker que sobe pela primeira vez.

### O número que discrimina: a fatia das cinco bibliotecas

Medido com `-X importtime` sobre `import app.main`, custo cumulativo de cada uma:

| Biblioteca | Antes | Depois |
|---|---|---|
| `xhtml2pdf.pisa` | 209 ms | — |
| `fpdf` | 117 ms | — |
| `openpyxl` | 36 ms | — |
| `boto3` | 33 ms | — |
| `sqlglot` | 32 ms | — |
| `num2words` | 10 ms | — |
| **total** | **437 ms (24% de 1,79 s)** | **0 — nenhuma aparece na árvore** |

Os 437 ms batem com a queda medida de 1,79 s → 1,35 s. É esse o resultado da spec, e é
ele que o meta-teste protege — por estrutura, não por tempo (regra 5).

### `botocore` ficou no topo, de propósito

`s3.py` importa `boto3` dentro do `__init__`, mas `Config` e `ClientError` continuam no
topo: são tipos usados na assinatura e no `except`, o `botocore` é dependência direta do
`boto3` (vem junto quando ele é de fato usado) e custa pouco perto dos 33 ms do cliente.
Mover os três teria sido cargo cult.

### `PLC0415` (regra 6) ainda não morde

O `select` do ruff hoje é `["E", "F", "I", "UP", "B", "SIM"]` — a família `PL` inteira
está fora, então nenhum dos cinco módulos precisa de exceção agora. A lista de exceção
que a regra 6 descreve é trabalho de **quem ligar `PL`** (106, 109, 111, 112 ou 116), e
o meta-teste desta spec é o que vai denunciar se alguém "resolver" o conflito devolvendo
os imports para o topo.

### O teste do editor de modelos é intermitente (fora de escopo)

Durante o ciclo, `frontend/src/features/templates/TemplateEditor.test.tsx` falhou quatro
vezes seguidas por estourar o `testTimeout` padrão do Vitest (5 s) e depois passou em
325 ms, sem nenhuma mudança no front-end (esta spec não toca uma linha dele). É custo de
aquecimento de transform/tiptap ultrapassando o teto no primeiro `render` de um host
frio. Nada a ver com imports do backend, mas é um teste que faz o gate mentir nos dois
sentidos — virou a **dívida nº 28**, alvo 110, que é a spec cujo objeto é justamente
gate que deixou de morder.

## 10. Definição de pronto

- [x] Os cinco imports movidos (seis bibliotecas), nenhum sétimo tocado
- [x] `sql_guard.py` com `from __future__ import annotations` + `TYPE_CHECKING`
- [x] Meta-teste em `tests/meta/test_imports_pesados.py`, verde — e verificado contra a
      versão anterior de cada um dos cinco arquivos, onde acusa as seis bibliotecas
- [x] `import app.main` medido antes/depois, quente e frio, registrado em §9
- [x] Nenhum teste anterior editado
- [x] `make test` verde e wall-clock dentro do orçamento (132 s de 300 s)
- [x] `make lint` verde — repositório inteiro, não só os arquivos tocados
- [x] Sem `Any`, `as any` ou `# type: ignore` novo
- [x] `ROADMAP.md` com a linha da 104 em ✅
- [x] Commit `refactor(104): imports pesados fora do boot`
