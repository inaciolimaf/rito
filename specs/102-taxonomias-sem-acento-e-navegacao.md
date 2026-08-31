# 102 — Taxonomias sem acento e navegação que existe (Blocos B + C da 101)

**Fase:** 10 · **Tipo:** correção · **Orçamento:** +6 s no wall-clock
**Depende de:** 101 (e, por herança, 013-019, 004, 012, 079) · **Status:** ✅ concluída

---

## 1. Objetivo

Executar os **Blocos B e C** da spec 101, na divisão que a Nota de execução dela já
desenhava. São duas coisas com a mesma assinatura da 101 — algo combinado numa spec e
nunca cobrado depois — mas em superfícies diferentes: a unicidade/busca das taxonomias
(banco) e a navegação com o e-mail transacional (produto).

Depois desta spec: "Time A", "TIME A" e "Timé A" não convivem mais; procurar "etica" acha
"Ética" nas cinco taxonomias; "Configurações" abre em vez de cair no `NotFoundPage`; quem
esquece a senha recebe o e-mail; e o convite chega para quem foi convidado, em vez de o
segredo ser mostrado para quem convidou.

## 2. Escopo

### Bloco B — as duas divergências de taxonomia

- **Dívida nº 11:** `uq_squads_tenant_name` vira índice único normalizado
  (`immutable_unaccent(lower(name))`), como as outras quatro taxonomias desde a 014, com
  migration de dado desempatando os duplicados que hoje são válidos.
- **Dívida nº 12:** a busca `q` das 5 taxonomias passa a ignorar acento, como
  `CustomerRepository.list_filtered` já faz desde a 019.

### Bloco C — navegação e e-mail transacional

- **Rota `/settings`** (dívida nº 24): hub das telas de configuração, agrupadas por
  assunto, com cada grupo respeitando a `capability` que já filtra o item na sidebar.
- **Rota `/accept-invite`** (dívida nº 9): recebe `?token=` e `?tenant=`, pede nome e
  senha, chama o aceite que já existia no backend e manda para o `/login`.
- **E-mail transacional**: recuperação de senha (004), convite de usuário (012) e convite
  de parceria (079) passam a enviar de verdade. Os dois convites param de expor o token.
- **O meta-teste de rotas**: toda entrada de `NAV_ITEMS` com `path` resolve para uma rota
  declarada em `App.tsx`, e a jornada e2e da sidebar passa a ser **derivada** da lista em
  vez de uma cópia manual.

## 3. Fora de escopo

- **A listagem de "Atividades"** (`/posts`). O meta-teste desta spec descobriu que o item
  também apontava para o vazio, mas ali não falta a rota: falta a **tela**. Vira a dívida
  **nº 26** com contorno declarado (redirect), não trabalho desta spec.
- **Migrar os 36 unions TS** para o arquivo gerado na 101 — o alarme já existe.
- **Índice único normalizado em qualquer outra tabela** além de `squads`.
- **Preferência de notificação por evento** e qualquer canal além de e-mail: o Bloco C liga
  o SMTP que já existe aos três fluxos de autenticação, nada mais.
- **Prazo fatal** (dívida 18) e **feriados de 2031+**: seguem na 122.

## 4. Modelo de dados

Nenhuma tabela nova. Uma migration, `alembic/versions/102_squads_unaccent_unique.py`
(`down_revision = "099_migration_lock"`): desempata os nomes duplicados **antes** de trocar
a constraint literal pelo índice funcional. O desempate é determinístico (`created_at`,
`id`) e conservador: o mais antigo mantém o nome, os demais ganham sufixo ` (2)`, ` (3)`…
Renomear, nunca apagar — `squad_members` tem FK para `squads`.

`downgrade()` refaz o índice→constraint e **não** desfaz o rename: seria preciso saber
qual sufixo foi nosso e qual o usuário já tinha. Um downgrade que adivinha apagaria um
nome legítimo.

## 5. Contratos de API

Nenhuma rota nova. Três mudam de comportamento:

| Método | Rota | O que muda |
|---|---|---|
| POST | `/api/v1/squads` · PUT `/api/v1/squads/{id}` | **409** quando o nome só difere por caixa ou acento |
| GET | `/api/v1/{squads,action-groups,lawsuit-types,stages,customer-origins}?q=` | busca ignora acento nos dois sentidos |
| POST | `/api/v1/auth/forgot-password` | continua `202` sem corpo — o que muda é que o e-mail **sai** |
| POST | `/api/v1/users/invite` | dispara o e-mail (a resposta já não tinha o token) |
| POST | `/api/v1/partnerships/invite` | **para de devolver `token`** no corpo; o link vai por e-mail |

`PartnershipInviteResponse` perde o campo `token` e mantém `account_exists`, que é o que
distingue convite de parceria de convite de cadastro (regra 2 da 079).

## 6. Front-end

**Componentes reutilizados:** `EmptyState`, `Button`, `Input`, `Label`.
**Componentes criados:** nenhum — o hub é uma grade de links, não um componente de domínio.

**Rotas novas:** `/settings` (hub, dentro do `AppLayout`) e `/accept-invite` (pública, ao
lado do `/login` — quem aceita ainda não tem sessão). As duas entram **lazy**, como toda
página de feature (spec 098, regra 7).

**Fonte única:** `settingsSections.ts` descreve os grupos e links do hub; o teste cruza essa
lista com as rotas `/settings/*` declaradas em `App.tsx`, para uma tela nova não ficar
alcançável só por URL direta (que era a dívida nº 10).

## 7. Regras de negócio

13. Criar/renomear time cujo nome só difere por caixa ou acento devolve `409`.
14. A migration renomeia os duplicados pré-existentes mantendo o mais antigo intacto, sem
    apagar nenhum time e sem tocar em `squad_members`.
15. A busca `q` das 5 taxonomias encontra o registro independentemente de acento e caixa,
    **nos dois sentidos**.
16. `/settings` responde com o hub, e cada grupo esconde o que a `capability` não permite.
17. Toda entrada de `NAV_ITEMS` com `path` corresponde a uma rota declarada em `App.tsx`.
18. `forgot-password` envia o link por e-mail e continua respondendo `202` mesmo para
    e-mail inexistente — a rota não pode virar oráculo de quais contas existem.
19. Convite de usuário e de parceria enviam o link por e-mail e **não** devolvem o token.
20. Sem SMTP configurado, o envio levanta `ChannelNotConfiguredError`, vira log e **não**
    derruba a operação: o token já foi criado e é válido; o que falhou foi a entrega.

## 8. Plano de testes

| Tipo | Caso | Arquivo |
|---|---|---|
| integração | nome de time colidindo por caixa/acento → 409, no POST e no PUT (13) | `test_squads.py` |
| migration | duplicados renomeados, nenhum time perdido, membros intactos (14) | `test_migration_102.py` |
| integração | busca sem acento nas 5 taxonomias, nos dois sentidos (15) | `test_taxonomy_search.py` |
| integração | forgot-password envia; e-mail inexistente também dá 202 (18) | `test_transactional_email.py` |
| integração | convites enviam e não devolvem token; sem SMTP a operação segue (19-20) | `test_transactional_email.py` |
| meta | toda rota de `NAV_ITEMS` existe em `App.tsx` (17) | `tests/meta/test_final_audit.py` |
| frontend | hub lista os grupos, esconde por capability e cobre todas as rotas `/settings/*` (16) | `SettingsHubPage.test.tsx` |
| frontend | `/accept-invite` envia, redireciona, e trata link incompleto e token inválido | `AcceptInvitePage.test.tsx` |
| e2e | jornada 2/25 passa a ser derivada de `navItems.ts` (13 itens, era cópia de 10) | `e2e/tests/navigation.spec.ts` |

## 9. Descobertas

### 1. O meta-teste de rotas achou um segundo item quebrado no mesmo ciclo

Escrito para o `/settings`, ele apontou também o **`/posts`** ("Atividades"): mesma
doença, nunca mapeada em 100 specs. Só que ali não faltava a rota — falta a tela. A
listagem de atividades nunca foi especificada; só existe `PostDetailPage`.

Três saídas possíveis, e a escolha importa: construir a tela (feature fora do escopo),
silenciar o teste com uma lista de exceções, ou dar ao item um destino honesto. A segunda
está descartada por princípio — um gate que aceita exceção por arquivo deixa de morder, que
é exatamente o alerta que a spec 110 registra. Ficou a terceira: `/posts` redireciona para
o painel de tarefas, mesmo padrão do atalho `/goals` da spec 028, e a tela vira a **dívida
nº 26** com alvo 124.

### 2. `/accept-invite` não serve os dois convites — o backend não os distingue

A 101 descrevia a tela como servindo convite de usuário **e** de parceria, "o backend
distingue pelo token". Ele não distingue: são dois endpoints com autenticação diferente.
`POST /invitations/accept` é pré-autenticação (quem aceita ainda não tem conta);
`POST /partnerships/accept` passa por `require_role(GESTOR)` — quem aceita uma parceria já
é dono de um escritório e já está logado.

Então o e-mail de parceria aponta para `/partners?invite=<token>`, e a `PartnersPage` (que
já tinha o campo de colar o código) passa a preenchê-lo pelo parâmetro. Uma tela pré-login
pedindo "nome e senha" a quem já tem conta estaria errada.

### 3. O tenant viaja no link do convite

`POST /invitations/accept` exige `X-Tenant-Id`: é pré-autenticação, e o RLS não acha a
linha certa sem saber o tenant antes da query (regra da 004). Quem recebe o convite não tem
como saber esse id — então ele vai no link, ao lado do token. Sem isso a tela existiria e
não funcionaria.

### 4. Tirar o token da resposta quebrou os testes que dependiam dele

`test_partnerships.py` aceitava a parceria lendo `invite["token"]` da resposta HTTP. Com a
regra 19 o campo sumiu, e o raw token não fica no banco (só o hash) — não havia de onde
lê-lo.

A correção foi fazer o helper pegar o token **do e-mail**, via um canal de captura
(`tests/integration/email_capture.py`), que é o caminho do usuário real. O helper ainda
afirma que o token não voltou no corpo, então o próprio teste que consome o token também
protege a regra 19.

### 5. As duas páginas novas precisaram entrar lazy

Importá-las estaticamente em `App.tsx` quebrou `App.bundle.test.ts` (spec 098, regra 7) na
hora. O teste fez o trabalho dele: bastaria um import distraído para o bundle inicial
crescer sem ninguém medir.

### 6. `unaccented_contains` nasceu de 5 usos

A expressão de busca sem acento aparecia em 5 repositórios; virou `unaccented_contains` em
`app/core/listing.py` (regra dos 3 usos). Categorias financeiras, centros de custo e
instituições **continuam** com `ilike` puro de propósito: não são as 5 taxonomias da dívida
nº 12, e ampliar o alvo seria mudar comportamento fora do escopo declarado.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Regras 13-20 com teste
- [x] Migration com teste do desempate, exercitando o SQL real (importado, não copiado)
- [x] O terceiro meta-teste da 101 entregue e verificado falhando antes da correção
- [x] Jornada e2e da sidebar derivada da fonte, não copiada
- [x] `make test` verde e wall-clock < 300 s — 153 s
- [x] `make lint` verde
- [x] `docs/DIVIDA-TECNICA.md` fecha 9, 10, 11, 12 e 24; registra a 26
- [x] `ROADMAP.md` com a linha da 102 em ✅
- [x] Commit `fix(102): taxonomias sem acento e navegação que existe`
