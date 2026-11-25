# 135 — Autorização interna e as bordas da operação

**Fase:** 13 · **Tipo:** correção · **Orçamento:** +3 s no wall-clock
**Depende de:** 005, 012, 035, 058, 060, 091, 093, 097, 099 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar sete furos de autorização que não estão dentro de nenhum módulo: estão nas
**bordas** — a rota que chega ao mesmo estado por outro caminho, o campo monetário que sai
por uma resposta sem gate, o anexo lido por uma rota que não é a de anexo, a variável que,
por vir vazia, deixa uma rota aberta. Nenhum deles é uma permissão ausente; todos são uma
permissão que existe **em um caminho e não no outro**.

Levantados na auditoria de isolamento e segurança (achados 4, 5, 6, 8 e 10), com prova de
alcance para cada um.

## 2. Por que os cinco viram uma spec só

Porque são a mesma falha em cinco formas, e corrigi-los separadamente esconderia isso.

O Rito tem **dois eixos ortogonais** de autorização (`app/core/permissions.py`): o perfil
(COLABORADOR < ADMINISTRADOR < GESTOR) e o acesso financeiro (NONE < READ_ONLY < FULL). A
promessa é que os dois valem em qualquer lugar. O que a auditoria encontrou foi um padrão:
**o eixo vale onde alguém lembrou de escrevê-lo.** `require_financial` protege as ~40 rotas
de `app/domain/financial/` e para ali; `require_role(GESTOR)` protege o endpoint de meta de
pontos e não o corpo do PUT que grava o mesmo campo; `AttachmentService._get_accessible`
protege o download e não a extração, que lê o mesmo arquivo.

`test_permission_coverage.py` não vê nada disso, e não é defeito dele: ele pergunta se a
rota **declara** permissão, e todas declaram. A pergunta que faltava é se a permissão que
ela declara é a mais estrita entre as rotas que chegam ao mesmo estado.

## 3. Escopo

**A. `PUT /users/{id}` deixa de ser `setattr` cego** (achado 6, MÉDIA-ALTA). Lista explícita
de campos editáveis por perfil, em `app/domain/users/service.py::editable_fields`.

**B. Valores financeiros mascarados no detalhe do processo** (achado 4, ALTA).
`GET/POST/PUT /lawsuits` e `POST /lawsuits/{id}/move-stage` devolvem `case_value`,
`fees_value`, `fees_percentage` e `contingency` como `null` para `financial_access=NONE`.

**C. Autorização de anexo igual em todos os caminhos** (achado 5, ALTA). O eixo financeiro
passa a valer na rota genérica `/attachments`, e a extração de documento passa a ler o anexo
por `AttachmentService.get_accessible`.

**D. `/metrics` fechado por padrão em produção** (achado 10, MÉDIA). `METRICS_TOKEN` vira
obrigatória no boot; a comparação vira `secrets.compare_digest`.

**E. CORS coringa recusado no boot** (BAIXA). `allow_origins` com `*` e
`allow_credentials=True` derruba o processo em produção.

**F. URL pré-assinada de imagem: 7 dias → 15 minutos** (achado 8, BAIXA).

**G. DNS rebinding em webhook: registrado como dívida, com o motivo** (achado 10, BAIXA).
Ver §9.

## 4. Fora de escopo

Vinculante. Cada item aqui é trabalho real que **não** entra nesta spec:

- **Os outros três pontos do achado 4** — `POST /templates/{id}/resolve` e `/generate-pdf`
  (resolvem `{{valor_causa}}` e `{{valor_honorarios}}`, inclusive por extenso em PDF),
  `won_lawsuits`/`lost_lawsuits` dos relatórios (publicam `fees_value` na tela **e no
  export XLSX/PDF**) e `GET /ai/insights` ("Inadimplência relevante — R$ X"). São três
  módulos que esta spec não abre, e um deles (`app/domain/ai/`) está com outra spec em
  curso. Vira dívida, com a lista dos pontos.
- **Escrever** valor de causa e honorários sem acesso financeiro. Esta spec fecha a
  **leitura**; um COLABORADOR com NONE ainda pode informar um valor ao cadastrar o
  processo — e agora recebe `null` de volta. É incoerente, e é menos grave que o vazamento:
  fica anotado em §9.
- **Corrigir o DNS rebinding.** Ver §9, item G — é dívida por decisão, não por esquecimento.
- Achados 1, 2, 3, 7 e 9 da auditoria: cada um tem dono próprio.

## 5. Modelo de dados

Nenhuma migration. Nenhuma tabela, coluna ou índice muda — a correção é toda de
autorização, e autorização aqui não é dado persistido (`capabilities_for` é derivado,
regra 7 da spec 005).

## 6. Contratos de API

| Método | Rota | O que muda | Autorização |
|---|---|---|---|
| PUT | `/api/v1/users/{id}` | campos fora da lista do ator são ignorados (200, valor antigo na resposta) | COLABORADOR + self/ADMIN |
| GET/POST/PUT | `/api/v1/lawsuits[/{id}]` | 4 campos monetários vêm `null` sem acesso financeiro | COLABORADOR |
| POST | `/api/v1/lawsuits/{id}/move-stage` | idem, no processo devolvido | COLABORADOR |
| GET/POST | `/api/v1/attachments` | alvo `transaction` exige READ_ONLY (ler) / FULL (subir) | COLABORADOR + eixo financeiro |
| GET/DELETE | `/api/v1/attachments/{id}[/download]` | idem | COLABORADOR + eixo financeiro |
| POST | `/api/v1/documents/extract` | `attachment_id` passa pela visibilidade do anexo | COLABORADOR + a do anexo |
| GET | `/metrics` | comparação em tempo constante | bearer obrigatório em produção |

**Nenhum status novo, nenhum campo novo, nenhuma rota nova.** O anexo negado responde
`404`, não `403` — é o tratamento que a spec 035 já dava à tarefa privada, e o motivo é o
mesmo: um `403` confirmaria que o lançamento existe.

## 7. Front-end

Nada. Nenhum componente muda. Duas consequências visíveis, ambas corretas:

1. o card de valores da tela de processo aparece vazio para quem tem `financial_access=NONE`
   — exatamente como o card do CRM já aparecia desde a spec 060;
2. o formulário de perfil continua enviando o objeto inteiro; os campos que a pessoa não
   pode gravar voltam com o valor antigo na resposta, e a tela reflete o estado real.

## 8. Regras de negócio

1. **`PUT /users/{id}` grava só o que o ator pode gravar naquele alvo.** Três conjuntos:
   *pessoal* (nome, documento, telefone, OAB…) para quem edita a si mesmo; *vínculo*
   (perfil, acesso financeiro, cargo, jornada, admissão, `is_responsible`…) para
   ADMINISTRADOR+ editando **outra** pessoa; *RH* (`salary`) só com `financial_access=FULL`
   e nunca em si mesmo; `points_goal` só para GESTOR, como no endpoint dedicado. O que
   está fora da lista do ator é ignorado — a requisição segue, o campo não.
2. **Valor de causa, honorários, percentual e prognóstico vêm `null` sem
   `financial_access >= READ_ONLY`**, em toda resposta de processo (detalhe, criação,
   atualização, mudança de etapa). O campo some, a rota não.
3. **Anexo de lançamento exige o eixo financeiro em todo caminho**: READ_ONLY para listar e
   baixar, FULL para subir e remover — a mesma régua das rotas de `financial/router.py`.
   Sem acesso, o alvo responde 404.
4. **A extração de documento lê anexo pelo `AttachmentService`**, e portanto herda a regra 3
   e a regra 7 da spec 035 (tarefa privada).
5. **`METRICS_TOKEN` é obrigatória em produção.** Sem ela o processo **recusa subir**,
   listando o motivo junto com o resto do que falta.
6. **O token do `/metrics` é comparado com `secrets.compare_digest`.**
7. **`cors_allowed_origins` com a origem `*` recusa subir em produção.** A comparação é por
   origem inteira, não por substring.
8. **`public_url` vale 15 minutos** — o mesmo TTL do token de acesso.

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | tabela inteira de `has_financial_access` (7 pares) | `tests/unit/test_permissions.py` | ~0,05 s |
| unit | `editable_fields`: self, admin, RH, meta, colaborador em terceiro | `tests/unit/test_permissions.py` | ~0,05 s |
| unit | `METRICS_TOKEN` ausente/vazia recusa o boot | `tests/unit/test_bootstrap.py` | ~0,05 s |
| unit | CORS `*` sozinho e no meio da lista recusa; `*.dominio` **não** é coringa | `tests/unit/test_bootstrap.py` | ~0,05 s |
| integração | colaborador não reescreve o próprio salário nem com FULL | `tests/integration/test_users_update.py` | ~0,4 s |
| integração | salvar o perfil não zera a meta que o gestor definiu | `tests/integration/test_users_update.py` | ~0,4 s |
| integração | admin READ_ONLY não grava salário; gestor FULL continua gravando tudo | `tests/integration/test_users_update.py` | ~0,6 s |
| integração | detalhe do processo mascara os 4 campos para NONE e mostra para READ_ONLY | `tests/integration/test_financial_permission_sweep.py` | ~1,5 s |
| integração | a máscara vale também na resposta do POST e do PUT | `tests/integration/test_financial_permission_sweep.py` | ~0,8 s |
| integração | rota genérica de anexo: NONE não lista, não baixa, não sobe | `tests/integration/test_attachments_authz.py` | ~1,5 s |
| integração | READ_ONLY lê e não sobe | `tests/integration/test_attachments_authz.py` | ~0,6 s |
| integração | extração não lê anexo de lançamento sem acesso financeiro | `tests/integration/test_attachments_authz.py` | ~0,6 s |
| integração | extração não lê anexo de tarefa privada de outro | `tests/integration/test_attachments_authz.py` | ~0,6 s |
| integração | `/metrics` recusa 7 formas de `Authorization` quase certo | `tests/integration/test_metrics_token.py` | ~1,0 s |
| integração | a comparação do token é `compare_digest` (afirmação de fonte) | `tests/integration/test_metrics_token.py` | ~0,05 s |
| integração | `public_url` expira com o TTL da sessão, não em 7 dias | `tests/integration/test_file_storage.py` | ~0,05 s |

**Total medido:** +3 s serial (43 testes novos).
**Fixtures externas:** nenhuma. Nada aqui toca a rede — o `/metrics` roda em ASGI, o
storage é o MinIO local (infra, como Postgres).

**Um teste existente foi editado**, e a edição é mudança de comportamento declarada:
`test_salario_visivel_para_financial_access_read_only` gravava o salário com um
ADMINISTRADOR `READ_ONLY` e lia de volta. A regra 1 passou a exigir `FULL` para gravar
dinheiro — *um READ_ONLY que grava não é um READ_ONLY* —, então quem grava no teste virou
um GESTOR FULL. **O que o teste afirma não mudou**: quem LÊ o salário continua sendo o
administrador READ_ONLY, e é essa a asserção. Nenhum outro teste foi tocado.

## 10. Descobertas

- **A prova de que os testes mordem.** Antes de fechar, as duas guardas de anexo foram
  revertidas à mão no código (o gate financeiro trocado por `if False:` e a extração
  voltando a buscar pelo repositório) e a suíte nova rodou de novo: **5 dos 7 testes
  falharam**, e o caso da tarefa privada respondeu `422` em vez de `404` — 422 é o erro do
  extrator, o que significa que ele **leu o arquivo** antes de falhar. É a diferença entre
  "o teste passa" e "o teste afirma alguma coisa".
- **Ignorar em silêncio, e não 403, no `PUT /users/{id}`.** O corpo do PUT é o objeto
  inteiro: o formulário devolve `salary` e `points_goal` que acabou de receber, e responder
  403 por causa deles quebraria a edição do próprio nome para todo mundo. Como a resposta é
  montada a partir do estado real, quem tentou vê que não mudou. É proteção contra
  atribuição em massa, não uma acusação.
- **`points_goal` era apagado sem ninguém tentar nada.** O campo tem default `None` no
  schema; salvar o perfil sem enviá-lo zerava a meta que o GESTOR havia definido. Era a
  metade do achado 6 que não precisa de má-fé para acontecer — e a que, por isso, já devia
  ter acontecido em produção.
- **`_money_fields` já existia, e é o que tornou a regra 2 barata.** A spec 123 extraiu os
  quatro campos monetários numa função só para caber no teto de 30 linhas. Três specs
  depois, essa função era o único lugar onde a máscara precisava entrar. Agrupar por
  significado paga em lugares que não dá para prever.
- **`has_financial_access` fecha a regra dos 3 usos.** A comparação
  `financial_access != FinancialAccess.NONE` estava escrita à mão em quatro lugares (CRM em
  três, salário em um), e esta spec ia acrescentar mais dois. Virou função em
  `app/core/permissions.py`, e `require_financial` passou a usá-la — a forma de rota e a
  forma de predicado agora não podem discordar. As quatro cópias antigas ficam onde estão:
  são de módulos fora do escopo desta spec.
- **Recusar o boot, e não negar a rota, no `/metrics`.** As duas fecham o buraco. A
  diferença é o que acontece com quem configurou certo: negar a rota entrega um painel de
  observabilidade que para de funcionar sem dizer por quê, e o operador descobre no dia em
  que precisa dele; recusar o boot avisa no deploy, junto com tudo o mais que falta, no
  formato que a regra 5 da spec 099 já usa. O `SECRET_KEY` de exemplo abriu o precedente.
- **15 minutos, e não "algo menor que 7 dias".** O número não foi escolhido por conforto: é
  `access_token_ttl_minutes`. A afirmação que ele compra é dizível numa linha — *o link da
  imagem não sobrevive à sessão que o produziu* —, e o teste é escrito contra o TTL da
  sessão, não contra o número, para que os dois andem juntos se alguém mudar um.
- **O DNS rebinding do webhook virou dívida, com o motivo escrito.** A correção é conhecida:
  conectar ao IP já validado, preservando `Host` e `sni_hostname`. Ela não foi feita, e a
  razão não é tempo. É que substituir o host da URL pelo IP obriga a reintroduzir à mão o
  `Host` e o **nome usado na verificação do certificado**, em cada um dos quatro saltos de
  redirecionamento — e errar esse segundo desliga a verificação de certificado por nome em
  **todo** webhook do produto, um buraco maior que o que se fecharia. Some-se que o §3 do
  CLAUDE.md proíbe rede em teste: o que a suíte conseguiria afirmar é que o encanamento
  chama o transporte com os argumentos certos, não que a propriedade vale. Meia-correção
  com aparência de correção é pior que dívida escrita — a dívida pelo menos aparece no
  registro. O ataque exige um GESTOR mal-intencionado que já controle um domínio com TTL
  baixo, e rende SSRF de **leitura** pela resposta de `/webhook-endpoints/{id}/test`; os
  casos estáticos (IP privado, metadados de nuvem, redirect para rede interna) continuam
  barrados.
- **Escrever valor financeiro continua aberto.** Um COLABORADOR com NONE informa
  `case_value` ao cadastrar o processo e recebe `null` de volta. É incoerente, e é
  deliberadamente fora do escopo: fechar a escrita muda o cadastro de processo, que é fluxo
  de produto, não de segurança. Fica na dívida junto com templates, relatórios e insights.
- **Três gates de `tests/meta/` estavam vermelhos ao fechar**, e nenhum é desta spec:
  `test_tamanho_de_funcao` acusa `app/domain/lawsuits/listing.py::crm_stats`,
  `test_registro_de_gates` acusa uma regra de ESLint e `test_runner_gate` acusa o
  `run_tests.sh` — três arquivos que esta spec não toca, alterados em paralelo por outro
  trabalho em curso.

## 11. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as 8 regras com teste
- [x] Nenhuma tabela nova (nada de RLS a testar)
- [x] Suítes tocadas verdes: 43 testes novos, 0 regressões nos ~540 rodados ao redor
- [x] `ruff check` + `black --check` + `mypy` verdes nos arquivos da spec
- [x] Sem `Any`, `# type: ignore` ou `# noqa` novos
- [x] Um teste editado, com a justificativa no §9
- [x] Dívida do DNS rebinding registrada com o motivo
- [x] Commit `fix(135): autorização interna e as bordas da operação`
