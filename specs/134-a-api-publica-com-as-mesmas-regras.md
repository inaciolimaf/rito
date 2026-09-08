# 134 — A API pública com as mesmas regras

**Fase:** 12 · **Tipo:** correção · **Orçamento:** +5 s
**Depende de:** 005, 033, 056, 095 · **Status:** ✅ concluída

---

## 1. Objetivo

A API pública deixa de ser uma porta com regras próprias. Os seis buracos que a
separavam da API interna — privacidade de tarefa, acesso financeiro na emissão do token,
acesso financeiro na chamada, escrita fora do service, token que sobrevive ao
desligamento do dono e falha de autenticação sem contador nem registro — passam a
responder como a tela responde, com um gate para cada um.

A frase que a spec 095 já dizia e que ninguém conferia é a regra 10 dela: *"escrita pela
API pública passa pelas MESMAS validações dos services — sem atalho"*. Ela não passava.

## 2. O defeito de fundo, e por que ele produziu seis sintomas

A 095 desenhou a API pública como um **adaptador de entrega**: o tenant vem do token em
vez do JWT, e daí para dentro é o mesmo RLS, os mesmos services, o mesmo banco. O
isolamento entre escritórios ficou correto porque o RLS não é opcional — ele está no
banco, e esquecê-lo não é possível.

Tudo o que **não** está no banco ficou de fora. Permissão intra-tenant (`require_role`,
`require_financial`), visibilidade de tarefa privada (`visible_to`) e regra de negócio
(`FuturePaymentDateError`) são código de aplicação, e o caminho público não passava por
nenhum deles. O sintoma varia — tarefa alheia, financeiro aberto, data no futuro
aceita —, a causa é uma: **o que protege por convenção não atravessa uma segunda porta.**

Daí a forma da correção: sempre que possível, a regra foi para um lugar onde a porta
nova a herda em vez de precisar lembrar dela. O gate financeiro mora em `require_scope`,
que toda rota já usa; a visibilidade é o predicado da API interna importado, não
copiado; a escrita entra pelo service, que é onde as regras já estão.

## 3. Escopo

**A. Privacidade de tarefa (achado 7 da auditoria de segurança).** `GET /posts` aplica
`posts.listing.visible_to(viewer)` — importado da API interna, não reescrito.

**B. Acesso financeiro na emissão.** `ApiTokenService.create` confere os escopos pedidos
contra as capacidades de quem emite. Escopo financeiro além do emissor → `403`.

**C. Acesso financeiro na chamada.** `require_scope` confere a capacidade exigida pelo
escopo contra as capacidades do DONO do token, resolvidas a cada requisição.
`GET /settings` devolve as referências financeiras vazias para quem não tem
`financial.read`.

**D. Escrita pelos services.** `PUT /lawsuits/{id}` passa por `LawsuitService.update` e
`PUT /transactions/{id}` por `TransactionService.update`. Módulo novo `app/public/writes.py`
traduz o corpo parcial do contrato público na requisição completa que o service espera.

**E. Token e ciclo de vida do dono.** A autenticação carrega o usuário que emitiu o
token; inativo, o token não vale mais.

**F. Falha de autenticação instrumentada.** Contador por origem no Redis (o
`app/core/rate_limit.py` que já existe), log `WARNING` em `rito.public_api` e — quando o
token existe — a linha em `api_requests` que a regra 9 da 095 já prometia.

**G. Três gates.** A cobertura de permissão e a varredura financeira passam a enxergar
`/api/public/v1`; o contrato público passa a reprovar escrita direta no modelo.

## 4. Modelo de dados

Nenhuma migration. Todo o material já existe: `api_tokens.created_by` aponta para
`users`, e `users` já tem `role` e `financial_access`.

## 5. Contratos de API

| Método | Rota | O que muda | Antes |
|---|---|---|---|
| GET | `/api/public/v1/posts` | tarefa privada de terceiro some da página | vinha, com `comments` |
| GET | `/api/public/v1/settings` | referências financeiras vazias sem `financial.read` | vinham sempre |
| GET/PUT | `/api/public/v1/transactions*` | `403` sem acesso financeiro do dono | só escopo |
| PUT | `/api/public/v1/lawsuits/{id}` | `422` das validações do service | `setattr` no modelo |
| PUT | `/api/public/v1/transactions/{id}` | `422`/`409` das validações do service | `setattr` no modelo |
| — | toda rota pública | `401` se o dono do token foi desativado | seguia valendo |
| — | toda rota pública | `429` após 20 falhas de autenticação por minuto e origem | sem teto |
| POST | `/api/v1/api-tokens` | `403` ao pedir escopo financeiro além do emissor | `201` |

Erros em RFC 7807, como o resto (regra 7 da 095). Os 22 endpoints continuam 22: esta
spec não acrescenta nem remove superfície.

## 6. Front-end

Nada. A tela de tokens (`/settings/api`) já trata `403` como qualquer outra recusa de
permissão, e a mensagem do 403 novo diz o que fazer ("peça acesso financeiro antes").

## 7. Regras de negócio

1. **`GET /posts` enxerga o que o EMISSOR do token enxerga.** O predicado é
   `visible_to(token.created_by)`, o mesmo da tela.
2. **Token não delega o que o emissor não tem.** Emitir com escopo financeiro exige a
   capacidade correspondente: `read:transactions` exige `financial.read`,
   `write:transactions` exige `financial.write`.
3. **A permissão vale no momento do ato.** As capacidades do dono são resolvidas a cada
   requisição, e o gate roda dentro de `require_scope`. Quem perdeu o acesso financeiro
   às 14h perde o token financeiro às 14h01.
4. **Token de usuário inativo não autentica** — `401`, com o texto dizendo por quê.
5. **Falha de autenticação conta e registra.** Vinte por minuto por origem; passou,
   `429` com `Retry-After`. Toda falha vira log `WARNING`; a de token conhecido vira
   também linha em `api_requests`.
6. **Escrita pública passa pelo service** — regra 10 da 095, agora com gate. Nenhum
   `setattr`, `session.add` ou `session.flush` em `app/public/router.py`.
7. **Rota pública sem `require_scope` reprova o CI**, como rota interna sem
   `require_role` já reprovava.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | privada de terceiro fora; a do emissor e a pública dentro | `test_public_api.py` | ~0,9 s |
| integração | dono desativado → `401` na leitura e na escrita | `test_public_api.py` | ~0,5 s |
| integração | token revogado vira linha 401 em `api_requests`; 21ª falha → `429` | `test_public_api.py` | ~0,7 s |
| integração | `PUT` de lançamento: data futura `422`, descrição normalizada pelo service | `test_public_api.py` | ~0,3 s |
| integração | `PUT` de processo: valor negativo `422`, etapa inexistente `422`, histórico gravado | `test_public_api.py` | ~0,3 s |
| integração | emissão × `financial_access` (6 combinações) | `test_financial_permission_sweep.py` | ~1,3 s |
| integração | dono rebaixado → `403` em leitura, escrita e nas referências de `/settings` | `test_financial_permission_sweep.py` | ~0,7 s |
| gate | toda rota de `/api/public/v1` declara escopo, e o scanner acha 22 | `test_permission_coverage.py` | ~0,1 s |
| gate | o scanner público morde a rota sem escopo | `test_permission_coverage.py` | ~0,1 s |
| meta | nenhuma escrita direta no modelo dentro do router público | `test_public_api_contract.py` | ~0,0 s |
| meta | `GET /posts` importa `visible_to` da API interna | `test_public_api_contract.py` | ~0,0 s |

**Total estimado:** +5 s
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

## 9. Descobertas

- **A decisão que a spec existe para tomar: de quem é a visão que o token enxerga.**
  A API pública é autenticada por TOKEN, e token não é sujeito — não tem tarefa privada,
  não tem responsável, não tem perfil. Havia três respostas possíveis e as outras duas
  são piores:

  - *o escritório inteiro* (o de hoje) transforma um controle desenhado para ser
    inviolável até por GESTOR em algo que qualquer token derruba, e derruba **sem
    rastro**: a tarefa privada não some do lugar, ela só passa a ser lida por outra porta;
  - *nada de privado* (esconder toda `is_private`) seria seguro e mentiroso — o dono da
    tarefa deixaria de ver a própria tarefa na integração que ele mesmo montou, e o
    sintoma seria "a API pública perde tarefas", que é o pior tipo de defeito para
    diagnosticar;
  - *a visão de quem emitiu o token* é a escolhida. O token já carrega `created_by`, e
    ele já é o autor de tudo o que a API pública ESCREVE (`_acting_user`, desde a 095).
    Fazer a leitura seguir o mesmo sujeito é o que torna a frase inteira verdadeira: **o
    token faz o que o dono dele faria, nada mais.** É também a única resposta que dá ao
    escritório um controle real — quem não quer expor a própria tarefa privada não emite
    o token com o próprio usuário.

  A consequência a saber: dois tokens do mesmo escritório podem devolver páginas
  diferentes de `/posts`. Isso é correto e é o ponto — a alternativa é a página igual
  para todos, que é a que vaza.

- **O gate financeiro mora em `require_scope`, e não nas rotas.** Foi a diferença entre
  corrigir quatro linhas e corrigir a classe: a exigência é derivada do próprio escopo
  (`read:transactions` → `financial.read`), então uma rota financeira nova **não tem como
  esquecer** o gate — ela o herda de pedir o escopo. Pôr `Depends(require_financial(...))`
  em cada rota pública teria funcionado hoje e falhado na primeira rota nova, que é
  exatamente como este defeito nasceu na 095.

- **Capacidade, não perfil.** O `ApiCaller` guarda `capabilities` — a saída de
  `capabilities_for(role, financial_access)`, a matriz que já existe em
  `app/core/permissions.py` — e não o par perfil/acesso. Guardar o par obrigaria a repetir
  aqui a ordem `NONE < READ_ONLY < FULL`, e duas tabelas de ordenação divergem na primeira
  mudança. Com capacidade, um eixo de permissão novo entra na matriz de lá e vale aqui.

- **Emissão e chamada, as duas — e o motivo de nenhuma bastar sozinha.** Só a emissão
  deixaria vivo todo token já emitido (e token não expira sozinho: os da base ficariam
  para sempre). Só a chamada deixaria o Gestor sem acesso financeiro emitir alegremente um
  `write:transactions` que só falha no primeiro uso, seis meses depois, no script de outra
  pessoa. A emissão dá a recusa cedo e com a mensagem certa; a chamada é a que garante.

- **A tradução do PUT parcial foi o trabalho de verdade do achado da escrita.** O
  contrato público aceita atualização parcial e os services recebem a requisição inteira,
  porque é o que a tela envia — e essa incompatibilidade de forma é, quase certamente, o
  motivo de a 095 ter escrito `setattr` no modelo e seguido em frente. `app/public/writes.py`
  preenche a requisição com o estado atual da entidade e sobrescreve com o que veio;
  `exclude_unset` é o que separa "não mandou" de "mandou nulo" — a diferença entre não
  mexer na baixa e estornar o lançamento.

- **O schema público é mais frouxo que o interno, e isso vira 500 se ninguém traduzir.**
  `PublicLawsuitUpdate.case_value` não tem `ge=0`; `LawsuitUpdateRequest.case_value` tem.
  Passar o valor negativo adiante levanta um `ValidationError` **cru** do Pydantic, que
  não é `RequestValidationError` — e o único handler registrado é para o segundo. Sem a
  tradução para 422 em `writes.py`, o conserto do achado 3 teria trocado um 200 errado por
  um 500. É o tipo de detalhe que só aparece escrevendo o teste do valor negativo.

- **Limite de falha por ORIGEM bloqueia até quem tem token bom, e é deliberado.** O
  contador existe para o pedido **não chegar ao banco** — escolher pelo token exigiria
  consultar o token primeiro, que é justamente o custo que se quer evitar. Então, dentro
  da janela de um minuto, aquela origem está fora. Mitiga-se por construção: o contador
  conta só FALHA, e o integrador com credencial válida nunca o alimenta. É o mesmo
  desenho do limitador de login (`auth/service.py`), e o teste afirma o comportamento em
  vez de escondê-lo.

- **`allowed_ips` continua respondendo 401.** O 429 novo entra ANTES da busca do token, e
  o 401 de origem recusada continua depois — a ordem preserva o que a 095 comprou: o IP
  recusado não pode aprender que o token é válido.

- **Uma consulta a mais por requisição pública, medida e aceita.** Ler o dono do token é
  o preço da regra 3, e ela vai na MESMA transação do `api_token_lookup`: a função é
  `SECURITY DEFINER` e devolve o `tenant_id`, então o `set_tenant_context` acontece logo
  em seguida e o usuário já vem pelo RLS. A API pública não está no orçamento de queries
  do §11 do `CLAUDE.md` — e a alternativa (cachear a permissão do dono) é a mesma
  fotografia que produziu o achado 4.

- **`last_used_at` de token revogado passa a ser atualizado.** Efeito de registrar a
  tentativa: o middleware grava a linha e o carimbo junto. É melhor assim — "quando este
  token revogado foi tentado pela última vez" é exatamente a pergunta de quem investiga
  credencial vazada.

- **Mudança de comportamento em teste anterior, nominalmente.** Um único ponto:
  `tests/integration/test_public_api.py` criava o emissor com
  `make_user(role=UserRole.GESTOR)`, que nasce com `financial_access=NONE`, e pedia
  `TODOS_OS_ESCOPOS` — inclusive os dois financeiros. Com a regra 2, essa emissão passou a
  ser `403`. Os 19 pontos viraram uma chamada a `_gestor(make_user)`, que é o mesmo
  GESTOR com `financial_access=FULL`, e a docstring dela explica por quê. **Nenhuma
  asserção foi alterada**: os 22 testes anteriores do arquivo continuam afirmando o que
  afirmavam.

- **O que ficou fora, e é dívida nomeada.** `app/public/router.py` continua montando 9
  consultas de LEITURA com `select()`, que é a dívida que `tests/meta/test_camadas.py`
  registra por extenso (`_RAIZ` cobre `app/domain`, não `app/public`). Esta spec fecha o
  lado da ESCRITA — que era o que produzia comportamento divergente — e não abre o de
  leitura: reproduzir 22 contratos públicos com service e repositório próprios é uma spec
  inteira, e misturá-la aqui esconderia as seis correções no meio de um refactor.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] As 7 regras com teste, e as duas de gate provadas mordendo
- [x] Nenhuma tabela nova (nada de RLS a testar); o isolamento por tenant da 095 continua verde
- [x] Testes anteriores passando — a única edição é o helper `_gestor`, justificado no §9
- [x] `ruff`, `format` e `mypy` verdes nos arquivos da spec
- [x] Sem `Any`, `# type: ignore` ou `# noqa` sem justificativa
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `fix(134): a API pública com as mesmas regras`
