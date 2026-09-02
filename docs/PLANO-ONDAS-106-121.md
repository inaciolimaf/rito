# Plano de ondas — specs 106 a 121

**Medido em:** 01/09/2026, commit `4b9b223` · **Método:** `ruff check .` dentro de `backend/`
(o escopo real do `make lint`, que inclui `app/`, `tests/`, `alembic/` e `scripts/`), mais
leitura de `backend/tests/conftest.py` para o comportamento do banco de teste.

Este documento responde uma pergunta operacional: **quantas das 16 specs pendentes dá para
executar em paralelo, e sob que protocolo.** Não substitui nenhuma spec — cada uma continua
sendo a fonte de verdade do próprio escopo. Isto aqui é a ordem de execução e o contrato dos
agentes.

---

## 1. Recontagem — toda spec da leva foi medida em `44469bd` e o número mudou

As specs 106–121 nasceram de uma auditoria de 28/08/2026. Cinco dias e três specs depois, os
inventários drifaram. **A primeira tarefa de qualquer execução é recontar** — as próprias
specs mandam fazer isso, e a tabela abaixo é a razão.

| Spec | Regra | Na spec (`44469bd`) | Hoje (`4b9b223`) | Δ |
|---|---|---|---|---|
| 106 | `C901` (max-complexity 6) | 41 | **46** | +5 |
| 107 | RET, PTH, ERA, TID, ICN | 2 (`ERA001`) | **2** | — |
| 108 | `ASYNC240` | 2 | **2** | — |
| 109 | `PLR0915` | 4 | **4** | — |
| 111 | `PLR0912` | 6 | **6** | — |
| 112 | `PLR0911` | 7 | **7** | — |
| 113 | `RUF100` | 31 | **33** | +2 |
| 114 | `DTZ011` | 90 | **94** | +4 |
| 115 | `S101` total | 3.827 | **3.999** | +172 |
| 115 | `S` total | 3.880 | **4.052** | +172 |
| 116 | `PLR0913` (max-args 8) | 14 | **14** | — |

O que drifa é o que cresce com código novo (complexidade, `assert`, `date.today()`). O que não
drifa são os tetos altos, que quase ninguém estoura. Isso é informação útil por si só: as
regras de teto alto (109, 111, 112, 116) são baratas de manter ligadas; as de teto baixo (106,
114, 115) precisam do gate para não voltarem.

---

## 2. Os dois bloqueios duros

### 2.1 Sobreposição de alvos — o cluster acoplado

Seis specs miram **as mesmas funções**. Não é coincidência: 106 mede caminhos, 109 mede
volume, 111 mede ramos, 112 mede saídas, 116 mede argumentos, 121 mede linhas — cinco réguas
sobre a mesma função grande. As próprias specs assumem isso ("se a 106 fechar antes, a
primeira tarefa desta spec é recontar — pode não sobrar nada").

Arquivos que aparecem em mais de uma spec do cluster {106, 109, 111, 112, 116}:

| Arquivo | Em quantas specs |
|---|---|
| `app/integrations/http/client.py` | 4 |
| `app/domain/templates/variables.py` | 3 |
| `app/domain/lawsuits/listing.py` | 3 |
| `app/domain/lawsuits/cnj.py` | 3 |
| `app/domain/automations/engine.py` | 3 |
| `app/integrations/openrouter/client.py` | 2 |
| `app/domain/reports/tabular_service.py` | 2 |
| `app/domain/financial/service.py` | 2 |
| `app/domain/financial/repository.py` | 2 |
| `app/domain/customers/repository.py` | 2 |
| `app/domain/automations/conditions.py` | 2 |
| `app/domain/ai/service.py` | 2 |

Rodar essas specs em paralelo não é só risco de conflito de merge: **destrói a premissa da
recontagem.** Dois agentes reescrevem `variables.py` ao mesmo tempo, cada um a partir de um
inventário que o outro já invalidou.

### Matriz de sobreposição (nº de arquivos em comum)

|  | 106 | 109 | 111 | 112 | 113 | 114 | 115 | 116 |
|---|---|---|---|---|---|---|---|---|
| **106** | 40 | 3 | 5 | 5 | 2 | 5 | 6 | 5 |
| **109** | 3 | 5 | 3 | 0 | 1 | 0 | 2 | 1 |
| **111** | 5 | 3 | 6 | 2 | 1 | 0 | 2 | 1 |
| **112** | 5 | 0 | 2 | 6 | 0 | 0 | 0 | 0 |
| **113** | 2 | 1 | 1 | 0 | 24 | 1 | 2 | 1 |
| **114** | 5 | 0 | 0 | 0 | 1 | 50 | 4 | 5 |
| **115** | 6 | 2 | 2 | 0 | 2 | 4 | 32 | 3 |
| **116** | 5 | 1 | 1 | 0 | 1 | 5 | 3 | 13 |

A diagonal é o tamanho do alvo de cada spec. Fora dela, qualquer célula > 0 é conflito
potencial se as duas rodarem juntas.

**E todas, sem exceção, editam a mesma lista `select` do `backend/pyproject.toml`.** Conflito
trivial de resolver e garantido de acontecer — tratado pela regra 3 do protocolo (§4).

### 2.2 Suíte concorrente é destrutiva nesta máquina

`backend/tests/conftest.py:180-184` (spec 105):

```python
_psql(
    maintenance_url,
    f'DROP DATABASE IF EXISTS "{banco}" WITH (FORCE)',
    f'CREATE DATABASE "{banco}" TEMPLATE "{_database_name(template_url)}"',
)
```

O nome vem de `_banco_do_worker()` — `rito_test_gw0`, `rito_test_gw1`, … — e é **global por
instância do Postgres**, não por checkout. Duas execuções de `make test` simultâneas (dois
worktrees, dois agentes) fazem uma derrubar o banco da outra no meio, com `FORCE`. O sintoma
não é um erro claro; é falha aleatória e irreprodutível.

Some-se a isso: 12 cores, `pytest -n auto` = 12 workers. Dois agentes testando ao mesmo tempo
já se atropelam por CPU antes de se atropelarem por banco.

**Consequência para o plano:** agente não roda `make test`. Se um agente precisar mesmo rodar
pytest, exporte um template exclusivo:

```bash
TEST_MIGRATIONS_DATABASE_URL=postgresql+asyncpg://rito:rito@localhost:5432/rito_test_a106 \
  uv run pytest -n 2 tests/…
```

Isso dá a ele `rito_test_a106_gw0`, que não colide. Ainda assim: no máximo 2 agentes testando
ao mesmo tempo, e nunca a suíte inteira.

---

## 3. As ondas

### Onda A — 5 em paralelo real, zero conflito de arquivo

| Spec | Escopo | Toca |
|---|---|---|
| **107** | RET, PTH, ERA, TID, ICN | só `pyproject.toml` — zero linha de código |
| **108** | `ASYNC` | `app/integrations/ocr/tesseract.py`, `tests/unit/test_openrouter_client.py` |
| **117** | Piso de cobertura | configs de cobertura, passo de CI, `coverage.json` |
| **118** | Gate de camadas | 2 routers com `select()`, 14 routers → service, `LawsuitSource` |
| **119** | Teto de duplicação | **só frontend** + `.jscpd.json` |

Única atenção: a 118 mexe em `app/domain/lawsuits/router.py`, que também está no inventário da
106. Como a 106 só entra na Onda B, não há simultaneidade — mas a 106 deve **recontar depois
da 118**, porque `create_lawsuit` (cx 7) pode cair sozinha quando o acesso a repositório sair
do router.

### Onda B — o cluster acoplado, sequencial

```
106 → recontar → 109 → 111 → 112 → 116
```

O roadmap já prevê que a 106 pode fechar boa parte das outras quatro. Se depois da 106 a
contagem de `PLR0915`/`PLR0912`/`PLR0911` for zero, essas specs viram "ligar a regra + travar
o meta-teste", que é um ciclo curto cada.

A 106 é grande demais para um ciclo (46 funções). O corte está na própria spec, §Nota de
execução: `max-complexity = 10` → `8` → `6`, cada degrau com `pyproject.toml` verde no fim.

**Alternativa: paralelizar por dono de arquivo, não por spec.** Em vez de 5 agentes brigando
por spec, 5 agentes com fronteira de arquivo, cada um resolvendo C901+PLR0911+PLR0912+PLR0913
do seu território de uma vez:

| Agente | Território |
|---|---|
| B1 | `app/domain/templates/variables.py` (os 3 resolvedores → registro `dict[str, Resolver]`) |
| B2 | `app/domain/lawsuits/listing.py` + `app/domain/financial/repository.py` + `app/domain/customers/repository.py` |
| B3 | `app/integrations/http/client.py` + `app/integrations/openrouter/client.py` |
| B4 | `app/domain/automations/{engine,conditions,decision,actions,service}.py` |
| B5 | `app/domain/lawsuits/cnj.py` + `app/domain/reports/tabular_service.py` |

Custo dessa forma: o commit atômico por spec fica artificial — o trabalho de um agente atravessa
quatro specs. Separar no merge é possível mas trabalhoso. **Escolha consciente entre velocidade
e higiene do histórico**, não um detalhe.

### Onda C — 114, sozinha

94 chamadas, 50 arquivos, `app/core/clock.py` novo, injeção por `Depends`. É a **única spec da
leva que muda comportamento de propósito** e a que mais encosta nas outras (5 arquivos em comum
com a 106, 5 com a 116, 4 com a 115). Não divide onda com ninguém.

### Onda D — 113 → 115, nessa ordem e só nessa

A 113 §3 é explícita: a `# noqa: S608` de `tests/integration/test_post_comments.py:452` é
suprimida hoje e a família `S` só é ligada pela 115. Inverter a ordem faz a linha reaparecer
como violação nova sem contexto. A 113 remove as 33 diretivas mortas; a 115 reavalia essa
linha específica.

### Onda E — fechamento, sequencial

```
110 (auditoria de 101, 104–109) → 120 (auditoria de 111–119) → 121 (teto de 30 linhas)
```

**Observação que vale registrar:** a 110 e a 120 *são* o papel de validador final. O roadmap já
tinha essa estrutura antes da pergunta ser feita — a cada dez specs, uma que só pergunta "os
gates ainda mordem?". Elas não são trabalho de agente; são a revisão humana que fecha a faixa.

E a 121 vem por último com uma primeira tarefa declarada: **recontar**. Depois de 106, 109,
111, 112 e 119, os 134 do backend e 225 do frontend serão outro número.

---

## 4. Protocolo de execução dos agentes

1. **Recontar antes de mexer.** Todo agente começa rodando o `ruff check` da sua regra e
   comparando com o inventário da spec. Divergência vai para `## 9. Descobertas` da spec.
2. **Agente não roda `make test`.** §2.2. Se precisar de pytest dirigido, template exclusivo
   por agente, `-n 2`, no máximo dois agentes por vez.
3. **`backend/pyproject.toml` não é do agente.** O agente entrega o código limpo e *anota* qual
   entrada do `select` (e qual `per-file-ignores`, com a justificativa citando a spec) precisa
   entrar. As edições do `pyproject.toml` são aplicadas na integração, de uma vez. Isso elimina
   o conflito N-way de uma linha.
4. **Integrar uma por vez.** Cinco branches mescladas juntas e a suíte vermelha = bissecção
   cara, que come todo o ganho do paralelismo. Integra, testa dirigido, integra a próxima.
   `make test` + `make lint` completos só uma vez, no fim da onda.
5. **A spec só fecha na mão de quem integra.** `CLAUDE.md` §8: sem verde, sem ✅ no
   `ROADMAP.md`. O agente entrega a correção; o commit `refactor(NNN): …` e a marcação de
   concluída são do ciclo de integração.
6. **Nenhum teste anterior editado.** É a definição operacional de refatoração em toda a leva
   (exceto a 114, que declara quais reescreve e por quê).
7. **Silenciar por arquivo é achado, não solução.** Nenhum `per-file-ignores` novo sem
   comentário citando a spec que o autoriza — a 110 e a 120 conferem exatamente isso.

---

## 5. Resumo em uma tabela

| Onda | Specs | Paralelismo | Bloqueio |
|---|---|---|---|
| A | 107, 108, 117, 118, 119 | **5 simultâneas** | — |
| B | 106 → 109, 111, 112, 116 | 1 (ou 5 por dono de arquivo) | mesmos arquivos |
| C | 114 | 1 | muda comportamento; encosta em A e B |
| D | 113 → 115 | 1 | `S608` herdada, ordem obrigatória |
| E | 110 → 120 → 121 | 1 | são auditorias das anteriores |

**Máximo real de paralelismo: 5.** Nunca 16, e o número não é limitado por máquina — é
limitado pelo grafo de dependência que as specs declaram e pela sobreposição de alvos que a
medição expôs.
