# 115 — Bandit (S): a superfície de segurança que o lint alcança

**Fase:** 11 · **Tipo:** correção · **Orçamento:** +0,5 s
**Depende de:** 113 · **Status:** ✅ concluída

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

### A escala confirmada, e o `per-file-ignores` que a spec previu

4.122 violações da família `S`; **4.069 são `S101`**, e 4.020 delas em `tests/`. A §2
acertou o diagnóstico e o remédio. Com `S101` e `S608` silenciados em `tests/` e
`scripts/`, sobraram **72** violações reais — e depois das que a 113 já tinha limpado, o
trabalho de `app/` foram **47 `assert`** (a §3 estimava 44).

### O `assert` de produção: 47, e nenhum virou `noqa`

A triagem deu três baldes, não os dois que a regra 4 previa:

**1. Invariante de programador (32).** `assert x is not None` depois de uma busca que a
regra de negócio garante ter achado algo. A regra 4 mandava «vira comentário ou some» — e
isso **não funciona**: esses `assert` estreitam `T | None` para `T`, e apagá-los quebra o
`mypy` em cascata. Trocar cada um por `if x is None: raise` custaria duas linhas e um ramo
morto em 32 pontos, afundando cobertura e batendo no gate de complexidade da 106.

A saída foi `app/core/invariants.py::not_none`, que checa e devolve: uma linha no ponto de
uso, zero ramos novos lá, e o `mypy` estreita pelo tipo de retorno como estreitava pelo
`assert`. **O único ramo morto do projeto é o da própria função**, testado uma vez.

O `why` é obrigatório de propósito: ele descreve a GARANTIA que falhou («o RLS já filtrou
por tenant», «validado em validate_references»), que é o que a pessoa de plantão precisa
ler. Os 32 comentários que já existiam ao lado dos `assert` viraram esse texto — nenhuma
explicação se perdeu.

**2. Configuração ausente (9).** Cinco em `create_file_storage` e quatro nos workers
(`MIGRATIONS_DATABASE_URL`). Estes não são invariantes: são validação de deploy. Viraram
`ConfigurationError`. Sob `python -O` o `assert` sumia e o `boto3` recebia `None` como
endpoint, falhando lá dentro sem dizer qual variável faltava.

**3. Verificação de sistema de arquivos (1).** `tenant_catalog` conferia se a migration
existe; virou `FileNotFoundError` com o caminho na mensagem.

E dois casos que não eram nada disso:

- **Os três `assert isinstance(exc, ...)` dos handlers de erro.** O FastAPI tipa todo
  handler como recebendo `Exception` mas despacha pelo tipo registrado. Viraram `_como`,
  que checa e devolve com o tipo certo. O detalhe que fez valer a pena: se o `assert`
  sumisse sob `-O`, o `mypy` teria estreitado um tipo que nada garante, e um erro de
  registro viraria `AttributeError` **durante a montagem da resposta de erro** — o pior
  momento possível para um erro novo.
- **`assert payload.tone in TONE_INSTRUCTIONS`.** Não era invariante: era
  **exaustividade de tabela de despacho**, exatamente o padrão que a 111 tratou. `tone` é
  um `Literal` validado pelo Pydantic na porta; o que o `assert` protegia era a tabela
  ficar sem uma chave. Foi apagado, e a garantia agora mora onde a 111 pôs as outras.

### Uma correção que quebrou dois gates, e o que isso ensinou

Pôr `if url is None: raise ConfigurationError(...)` dentro dos quatro workers levou
`djen_sync.run_due_syncs` de complexidade 6 para 7 e de 8 ramos para 9 — reprovando nos
gates da 106 e da 111 ao mesmo tempo.

O conserto foi melhor que o problema: `migrations_url(para)` em `bootstrap.py`, usada pelos
quatro. Uma mensagem só, o `if` fora de funções que já estavam no teto, e o
`test_workers_finos` registrou três corpos de task encolhendo (34→33, 27→26, 21→20).

A lição: **um gate de tamanho transforma «adicionar validação» em «extrair a validação»**,
e o segundo é o que se queria desde o começo. Os gates da leva 106–116 já estão cobrando
uns dos outros.

### A §4 diagnosticou errado 6 dos 9 `S608` — e o fix certo é melhor

A §4 diz que os nove `S608` de `app/` são «interpolação de identificador, que parâmetro de
bind não resolve» e prescreve uma função de quoting. Medido: **seis são interpolação de
LITERAL**, em `core/provisioning.py`, que bind resolve muito bem.

```python
grupos = ", ".join(f"('{nome}')" for nome in tenant_catalog.action_groups())
... text(f"... FROM (VALUES {grupos}) AS g(name) ...")
```

Nenhum valor vem de fora — são constantes de migration —, mas a forma é a da injeção, e as
aspas eram postas à mão: **bastava um apóstrofo num nome de taxonomia** («Ação de Cobrança
d'Água») para quebrar a query de provisionamento. Os seis viraram `unnest` de arrays
ligados. O driver manda os valores por fora do texto e o problema deixa de existir, em vez
de ser documentado.

Dos três restantes: um era **falso positivo em prosa** (`migrations.py` citava
`SELECT ... FROM migration_locks` numa mensagem de erro; reescrevi a frase para nomear a
tabela e as colunas — falso positivo removido na origem, sem `noqa`); um virou bind
(`interval '{N} days'` → `make_interval(days => :dias)`); e só **um** é de fato
identificador — `SELECT count(*) FROM {name}` em `aggregates.py`, onde `name` já é validado
contra `_KNOWN_VIEWS` na entrada da função. Esse ficou com `noqa` apontando para a
allowlist, que é a defesa real.

### Conclusão sobre o `noqa` herdado da 113 (obrigatória pela §5)

A 113 registrou **dois**, não um. Os dois estão em `tests/`, e com o `per-file-ignores`
desta spec **nenhum precisou voltar**:

- `tests/integration/test_post_comments.py:454` (era `S608`, sem justificativa escrita) —
  coberto por `"tests/**/*.py" = [..., "S608"]`;
- `tests/conftest.py:105` (era `S603 — argumentos fixos, nada vem de fora`) — coberto por
  `"tests/**/*.py" = [..., "S603", "S607"]`.

A conclusão está escrita, como a §5 exigia, e não presumida: o silenciamento por arquivo é
mais honesto que o marcador por linha aqui, porque a razão é a mesma para o arquivo inteiro
— teste que verifica o banco por fora do ORM, com nomes de tabela escritos no próprio
teste.

### Seis silenciamentos, e o teto que os conta

`# noqa: S*` sobreviventes: `S603` ×2 (`rito backup`: argumentos fixos, sem shell), `S105`
×2 (constantes cujo NOME confunde a regra), `S608` ×1 (identificador validado por
allowlist) e `S311` ×1 (jitter de backoff). Teto de 6, travado por meta-teste, com
justificativa exigida em cada um.

Um detalhe que valeu: a primeira versão do jitter usava `lambda` atribuído, o que obrigava
a silenciar `E731` **junto** com o `S311`. Trocar por função nomeada eliminou o segundo —
trocar uma supressão por duas é o oposto do que esta spec faz.

### O teste que prova a tese da spec

`test_invariants.py::test_sobrevive_ao_modo_otimizado` roda o mesmo programa com e sem
`-O` e confirma que a verificação levanta nos dois. É a afirmação central da spec — «o
`assert` some, o `if` não» — verificada em vez de repetida.

### Dívida 35 ganhou confirmação

O `make test` reprovou uma vez em `test_limite_de_get_devolve_429_com_retry_after` (recebeu
200 onde esperava 429); o arquivo passa sozinho e a execução seguinte fechou verde. É a
dívida 35 com o mecanismo agora identificado: o **token bucket de rate limit vive no
Redis**, é global entre workers e não participa do `ROLLBACK` da 105. Registrado lá.

## 10. Definição de pronto

- [x] `S` no `select`, com `per-file-ignores` de `S101` para `tests/` e `scripts/`
      (mais `S105`/`S106`/`S107`/`S603`/`S607`, justificados)
- [x] `per-file-ignores` de `S608` para `alembic/versions/`, citando o §9
- [x] As **47** (não 44) `assert` de `app/` triadas: **nenhuma virou `noqa`** — 32 para
      `not_none`, 9 para `ConfigurationError`, 1 para `FileNotFoundError`, 3 para `_como`,
      1 apagada por ser exaustividade de tabela (padrão da 111)
- [x] Os 9 `S608` de `app/` resolvidos — mas **6 eram literal, não identificador**:
      viraram `unnest` de arrays ligados, que é melhor que quoting. Ver §9.
- [x] `pg_dump`/`pg_restore` por caminho absoluto de configuração (`PG_BIN_DIR`), com o
      `PATH` como padrão de desenvolvimento
- [x] `S112` logando antes do `continue`
- [x] Todo `noqa: S*` restante com justificativa, travado por meta-teste (teto 6)
- [x] Conclusão sobre os **dois** `noqa` herdados da 113 escrita em §9 — nenhum voltou
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 115 em ✅
- [x] Commit `fix(115): superfície de segurança do lint`
