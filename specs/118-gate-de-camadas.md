# 118 — Gate de camadas: os sintomas de SOLID que dá para verificar

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0,4 s
**Depende de:** 003, 005 · **Status:** ⬜ pendente

---

## 1. Objetivo

O `CLAUDE.md` §5 declara as regras de camada em linguagem imperativa — «`router` só faz HTTP»,
«router com `select()` dentro é bug», «`import openrouter` dentro de service é bug» — e
**nenhuma ferramenta as verifica**. As 13 meta-suítes existentes cobrem RAG, rede, RLS, imagem
Docker e contrato da API pública; camada não. O resultado é o esperado: as regras já estão
sendo violadas em 16 lugares.

Esta spec escreve três checagens de AST e corrige as 16.

> Refatoração: nenhuma mudança de comportamento. Nenhuma rota muda de forma, status ou resposta.

## 2. O que este gate é — e o que ele não é

Este é um gate **por proxy**, e a spec precisa ser honesta sobre isso desde a primeira linha,
porque a tentação de tratá-lo como prova é o que estraga gates assim.

**O que ele verifica** são três propriedades sintáticas, exatas e binárias: existe `select()`
dentro de um `router.py`; um `router.py` importa `repository`; um `service.py` importa uma
classe concreta de `integrations`. A máquina responde sim ou não, sempre igual.

**O que ele não verifica** é SOLID. Não existe teste para «a responsabilidade é única» ou
«esta é a abstração certa» — isso é revisão humana e continua sendo. Um service pode passar
nas três checagens e ainda ter regra de negócio no lugar errado.

Vale escrever assim mesmo: são os três sintomas mais baratos de detectar e os mais comuns, e
cada um que passa vira dívida que a próxima spec de refatoração paga mais caro.

## 3. Inventário — medido em 28/08/2026, commit `44469bd`

**Checagem 1 — `router.py` com acesso a dados.** 2 arquivos, 3 ocorrências.

```
app/domain/api_tokens/router.py:121   select(
app/domain/api_tokens/router.py:132   (await session.execute(stmt)).all()
app/domain/automations/router.py:296  select(AutomationDecision)
```

**Checagem 2 — `router.py` importando `repository`, pulando o service.** 14 módulos.

`ai`, `crm`, `customers`, `documents`, `dunning`, `financial`, `integration_alerts`,
`integrations`, `lawsuits`, `locations`, `publications`, `reports`, `schedule`, `users`.

**Checagem 3 — `service.py` importando classe concreta de `integrations`.** 3 imports em
2 arquivos — e aqui o inventário exige leitura, não contagem:

```
domain/datajud/service.py:21   from app.integrations.datajud.client import DatajudClient, ...
domain/datajud/service.py:22   from app.integrations.datajud.parser import ParsedProcess
domain/publications/service.py:31  from app.integrations.djen.parser import ParsedCommunication
```

Só a primeira é violação de DIP. `ParsedProcess` e `ParsedCommunication` são DTOs — formas de
dado, sem I/O — e importar forma de dado não acopla o service a implementação. Um gate que
reprovasse esses dois seria ruído, e ruído é como um gate morre.

A violação real fica evidente na assimetria com a integração irmã:

| Integração | Tem interface? | Service depende de |
|---|---|---|
| `djen` | sim — `integrations/djen/source.py` | a abstração |
| `datajud` | **não** — só `client.py`, `parser.py`, `health.py` | `DatajudClient`, concreto |

O `djen` fez certo na spec 042 e o `datajud` não seguiu. As outras três interfaces do §5 já
existem e estão sendo respeitadas: `FileStorage` (`integrations/storage/base.py`),
`OcrProvider`, `MessagingChannel`.

## 4. Escopo

**A.** `tests/meta/test_camadas.py` com as três checagens, por AST — nunca por regex, pelo
mesmo motivo que o `test_no_rag.py` já usa AST: `select` aparece dentro de string e de
comentário, e um gate que dá falso positivo em comentário é um gate que alguém desliga.

**B.** As 3 ocorrências da checagem 1 descem para o repositório correspondente.

**C.** Os 14 routers da checagem 2 passam a chamar o service. Onde o service ainda não tem o
método, ele ganha um — de passagem, sem regra nova.

**D.** `LawsuitSource` em `app/integrations/datajud/base.py`, com `DatajudClient`
implementando-a, no molde exato do `PublicationSource` do `djen`. O service passa a receber a
abstração por `Depends`.

**E.** Lista de exceção versionada no próprio teste, vazia na entrega. Se surgir exceção
legítima, ela entra ali com justificativa — não como `# noqa` espalhado.

## 5. Fora de escopo

- Verificar SRP, OCP, LSP e ISP. Não são mecanizáveis; ficam com a revisão.
- Um `import-linter` com grafo de camadas completo. Três checagens de AST no formato das
  meta-suítes que já existem resolvem o caso concreto sem trazer ferramenta nova.
- Camadas no frontend (`features/` importando de outra `features/`). Spec futura.
- Mudar o que qualquer service ou repositório **faz**.

## 6. Modelo de dados

Nenhuma tabela, nenhuma migration.

## 7. Contratos de API

Nenhum contrato muda. As duas rotas da checagem 1 (`/api/v1/api-tokens`,
`/api/v1/automations/.../decisions`) continuam com a mesma forma de resposta — é o que o
snapshot de rotas prova.

## 8. Regras de negócio

1. Nenhum arquivo `app/domain/*/router.py` contém chamada a `select()`, `insert()`,
   `update()`, `delete()` ou `session.execute()`.
2. Nenhum `router.py` importa de um módulo `repository`. Router fala com service; service
   fala com repositório.
3. Nenhum `service.py` importa classe que faz I/O de `app.integrations`. Importar DTO é
   permitido e o teste distingue os dois — a checagem mira em símbolos definidos em
   `client.py`, `source.py` e equivalentes, não no pacote inteiro.
4. `datajud` ganha `LawsuitSource` em `base.py`, e `DatajudClient` a implementa. O service
   recebe a abstração via `Depends`, como o de publicações já faz.
5. As três checagens têm lista de exceção **versionada e vazia** na entrega.
6. Nenhuma regra de negócio muda de lugar entre camadas nesta spec — o que estava no router
   e é HTTP fica; o que é query desce. Se algo parecer regra, registre em §11 e **não mova**.

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | nenhum `router.py` executa query (AST) | `tests/meta/test_camadas.py` | ~0,1 s |
| meta | nenhum `router.py` importa `repository` (AST) | `tests/meta/test_camadas.py` | ~0,1 s |
| meta | nenhum `service.py` importa cliente concreto de `integrations` (AST) | `tests/meta/test_camadas.py` | ~0,1 s |
| meta | a lista de exceção das três checagens está vazia | `tests/meta/test_camadas.py` | ~0,05 s |
| unit | `DatajudClient` satisfaz `LawsuitSource`; o mock de teste também | `tests/unit/test_datajud_source.py` | ~0,1 s |
| — | testes das specs 042, 043, 092 e 095 passam sem edição | — | — |

**Total estimado:** +0,4 s

O teste de LSP da regra 4 é o que o `CLAUDE.md` §5 chama de «o mock é uma implementação real
da interface» — sem ele, a abstração vira decoração.

## 10. Definição de pronto

- [ ] `tests/meta/test_camadas.py` com as três checagens por AST
- [ ] As 3 queries fora dos routers
- [ ] Os 14 routers passando pelo service
- [ ] `integrations/datajud/base.py` com `LawsuitSource`; service via `Depends`
- [ ] Listas de exceção versionadas e vazias
- [ ] Nenhum contrato de API alterado (snapshot de rotas verde)
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 118 em ✅
- [ ] Commit `refactor(118): gate de camadas`

## 11. Descobertas

Preencher durante a implementação. Em especial: qualquer coisa que parecia query e era regra.
