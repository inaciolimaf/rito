# 138 — Estados, cache e contrato do frontend

**Fase:** 13 · **Tipo:** correção · **Orçamento:** +2 s no wall-clock (frontend)
**Depende de:** 006, 007, 011, 018, 031, 038, 049, 053, 087, 090, 102, 119
**Status:** ✅ concluída

---

## 1. Objetivo

Uma auditoria do frontend achou onze defeitos que têm a mesma assinatura: **a tela não
mente, ela cala**. O HTML que um modelo de linguagem escreveu era injetado na origem da
aplicação sem uma linha de sanitização; um `href` vindo do DJEN virava link sem ninguém
olhar o esquema; o cache do React Query sobrevivia ao logout e servia o escritório
anterior para o próximo usuário da mesma aba; sete telas de detalhe ficavam em
"Carregando…" para sempre quando a API falhava; o 422 do servidor chegava, era mapeado
para um campo que não existe e sumia — o usuário clicava em Salvar e nada acontecia. Esta
spec fecha os onze, e planta três guardas (`QueryStateGate`, `SandboxedHtml`,
`safeExternalHref`) mais duas regras de ESLint para que nenhum deles volte por descuido.

## 2. Escopo

- **XSS**: `dangerouslySetInnerHTML` sai do projeto; HTML de terceiro passa a ser
  renderizado em `<SandboxedHtml>` (iframe `sandbox=""`, sem `allow-scripts` e sem
  `allow-same-origin`), com a regra de lint `rito/no-dangerous-html` para trancar a porta.
- **Link externo**: `lib/urls.ts` (`safeExternalHref`/`openExternal`) valida o esquema
  antes de qualquer `href` ou `window.open` — publicação, WhatsApp do contato, download de
  documento e de anexo.
- **Cache por sessão**: `logout()` e o `SESSION_EXPIRED_EVENT` limpam o `QueryClient`; a
  chave de toda listagem passa a carregar o escritório.
- **Estados obrigatórios**: `<QueryStateGate>` em `components/domain/` (carregando · erro ·
  **sem permissão** · vazio), aplicado às sete telas do `isLoading || !data`, com a regra
  `rito/no-loading-without-error` proibindo a volta do padrão.
- **Erro de formulário**: `describeApiErrors` separa erro de campo de mensagem geral, e
  `<ServerErrorAlert>` mostra o que não tem campo — inclusive `errors` como lista de
  strings e `loc: ["body"]`.
- **`EntityPicker`**: número de sequência contra resposta atrasada, `catch`, estados de
  carregando/vazio/erro e `aria-activedescendant`.
- **Zod alinhado ao Pydantic** onde a divergência produzia 422 evitável.
- **`application_id`**: o tipo do CRM passa a expor o campo, e "Desfazer aplicação" — que
  existia no backend desde a 053 e em lugar nenhum da interface — vira botão.
- **Sem permissão por rota**: `requiredCapabilityFor` + estado no `AppLayout`.
- **Formatação e repetição**: `lib/format.ts` (`formatBrDate`, `formatBrDateTime`,
  `formatNumberPtBr`, `formatUsd`, `formatGb`) e `useClickOutside` (que também traz o Esc
  aos três menus do shell).

## 3. Fora de escopo

- **Backend.** Três correções desta auditoria moram lá e estão descritas na §9; nenhuma
  linha de `backend/` foi tocada aqui.
- **Teto de tamanho de função no frontend** — decisão registrada na dívida 38, respeitada.
- **PUT total + `toPayload` incompleto** (achado 1 da auditoria): a correção estrutural é
  no contrato de update do backend. §9.
- **Jornada nova de e2e**: o teto de 25 do `CLAUDE.md` §3 está cheio; tudo virou teste de
  componente.

## 4. Modelo de dados

Nenhum. Spec de frontend: sem migration, sem tabela, sem endpoint novo.

## 5. Contratos de API

Nenhum contrato novo. Dois contratos **existentes** passam a ser respeitados pelo cliente:

| Método | Rota | Mudança |
|---|---|---|
| POST | `/api/v1/lawsuits/{id}/apply-workflow` | o tipo TS passa a declarar `application_id`, que a resposta sempre trouxe |
| DELETE | `/api/v1/lawsuits/{id}/workflow-applications/{application_id}` | passa a ser chamada — janela de 1 h da spec 053, regra 5 |

## 6. Front-end

**Componentes reutilizados:** `EmptyState`, `FormModal`, `MoneyField`,
`MaskedDecimalField`, `DataTable`, `EntityPicker`.
**Componentes criados** (todos em `components/domain/`, todos com três usos ou mais):

| Novo | Por que não dava para reusar | Usos |
|---|---|---|
| `QueryStateGate` | não existia um lugar com os quatro estados de uma tela de detalhe | 7 |
| `SandboxedHtml` | não existia forma segura de mostrar HTML que não escrevemos | 1 (+ regra de lint que obriga) |
| `ServerErrorAlert` | o alerta geral estava copiado em `FormModal`, `UserForm` e `AccountForm` | 6 |
| `useClickOutside` | `handleClickOutside` estava copiado em 4 componentes | 4 |
| `lib/format.ts` | a conversão ISO → `DD/MM/AAAA` estava reescrita em 7 arquivos | 8 |
| `lib/urls.ts` | não havia validação de esquema em lugar nenhum | 4 |
| `lib/br-documents.ts` | espelho do `core/br_documents.py` | 1 |

**Rotas:** nenhuma nova. O `AppLayout` ganha o estado "sem permissão" por capability.
**Estados:** carregando, vazio, erro, **sem permissão** — os quatro do `CLAUDE.md` §6.

`SandboxedHtml` é a única exceção à regra dos 3 usos, e de propósito: ele existe para que
`dangerouslySetInnerHTML` possa ser proibido por lint. Um guarda com um uso e uma regra
que o torna obrigatório vale mais que três usos.

## 7. Regras de negócio

1. **HTML que não escrevemos nunca entra no documento da aplicação.** A minuta gerada por
   IA é renderizada em `<iframe sandbox="" srcdoc>`: sem `allow-scripts` nada executa —
   nem `<script>`, nem `onerror=`, nem `javascript:` —, e sem `allow-same-origin` o
   documento fica em origem opaca, sem acesso ao `localStorage` (onde mora o refresh token
   de 30 dias), aos cookies nem ao nosso DOM. `dangerouslySetInnerHTML` é erro de lint.
2. **Link externo só com esquema http/https** (mais `mailto:`/`tel:`). `safeExternalHref`
   devolve `undefined` para qualquer outro, e `href={undefined}` faz o React omitir o
   atributo: o `<a>` deixa de ser link para o mouse, para o teclado e para o leitor de
   tela. Vale para todo endereço vindo de fora, não só o do DJEN.
3. **Trocar de sessão limpa o cache.** `logout()` e o `SESSION_EXPIRED_EVENT` chamam
   `queryClient.clear()` (não `invalidateQueries`: invalidar mantém o dado antigo em
   memória e continua servindo-o). Toda chave de `useListPage` carrega o escritório.
4. **Erro primeiro, carregando depois.** Nenhuma tela decide o que renderizar com
   `isLoading || !data`: com a API falhando, `isLoading` volta a `false` e `data` fica
   `undefined`, e a condição continua verdadeira para sempre. `QueryStateGate` testa erro,
   depois carregando, depois vazio. É gate de lint (`rito/no-loading-without-error`).
5. **Todo 422 aparece.** O que casa com um campo vai para o campo; o que não casa — lista
   de strings, `loc: ["body"]` de `model_validator`, `loc` terminando em índice — vira
   mensagem geral, sempre exibida. Um 422 sem nenhum erro de campo mostra ao menos o
   `detail`. Nenhum caminho leva a "clicar em Salvar e nada acontecer".
6. **A busca do `EntityPicker` só aceita a resposta da busca mais recente**, tem `catch`,
   e diz "Buscando…", "Nenhum resultado." e "Não foi possível buscar." em vez de não abrir.
   A opção ativa é anunciada por `aria-activedescendant`.
7. **O Zod não é mais frouxo que o Pydantic** onde a divergência gera 422 evitável: CPF e
   CNPJ com dígito verificador (espelho de `core/br_documents.py`), `reward` obrigatório na
   **edição** de tipo de tarefa (assimetria real entre `TaskTypeCreateRequest` e
   `TaskTypeUpdateRequest`), nome de workflow com teto de 200, instruções de minuta com
   teto de 4000, e os mínimos da decisão por IA (`automations/decision.py`). Nenhuma regra
   nova foi inventada — só espelhada.
8. **`ApplyResult` deixa de valer para dois endpoints diferentes.** O do CRM devolve
   `application_id`, e com ele a aplicação pode ser desfeita dentro da janela de 1 h; fora
   dela o backend recusa com o motivo, que é o que aparece na tela.
9. **"Sem permissão" é um estado, não um menu escondido.** As `capabilities` passam a
   guardar a rota, não só o item do menu, e o estado é renderizado **dentro do shell** —
   quem não pode ver aquela tela precisa continuar com o menu ao lado para ir a outro
   lugar. O 403 de qualquer consulta também tem texto próprio, no `QueryStateGate` e na
   faixa de erro do `DataTable`.
10. **Data e número seguem o `CLAUDE.md` §9 em um lugar só.** `formatBrDate` fatia a
    string em vez de passar por `new Date()` — `new Date("2026-01-01")` é meia-noite UTC e
    num fuso a oeste volta um dia. `toFixed()` não aparece mais em texto para o usuário.
11. **Menu que anuncia `role="menu"` fecha com Esc.** `useClickOutside` trata clique fora e
    Esc juntos, porque quem separou os dois entregou três menus dos quais o teclado não
    consegue sair.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| frontend | esquema recusado (`javascript:`, `data:`, `vbscript:`), aceito e relativo | `src/lib/urls.test.ts` | ~0,02 s |
| frontend | `DD/MM/AAAA` sem erro de fuso; vírgula decimal em US$/GB | `src/lib/format.test.ts` | ~0,02 s |
| frontend | CPF/CNPJ: dígito verificador, repetição, comprimento | `src/lib/br-documents.test.ts` | ~0,02 s |
| frontend | erro não vira carregando; 403 sem "tentar de novo"; 404; vazio | `QueryStateGate.test.tsx` | ~0,12 s |
| frontend | HTML hostil fica no iframe `sandbox=""`, fora do nosso DOM | `SandboxedHtml.test.tsx` | ~0,05 s |
| frontend | resposta antiga descartada; vazio; erro; `aria-activedescendant` | `EntityPicker.test.tsx` | ~0,75 s |
| frontend | `errors` como strings; `loc:["body"]`; erro de campo sem alerta redundante | `FormModal.test.tsx` | ~0,22 s |
| frontend | logout limpa o cache; o login seguinte não vê o escritório anterior | `providers/AuthProvider.test.tsx` | ~0,11 s |
| frontend | API 500 mostra erro, não "Carregando…" | `TermHealthCard.test.tsx` | ~0,13 s |
| frontend | `javascript:` não vira link; `https:` continua virando | `PublicationDetailDrawer.test.tsx` | ~0,23 s |
| frontend | minuta com `<img onerror>` não monta `<img>` no documento | `GeneratedBriefPreview.test.tsx` | ~0,09 s |
| frontend | CPF com DV errado não submete; CPF válido submete | `MonitoredTermForm.test.tsx` | ~0,50 s |
| frontend | `reward` vazio: válido na criação, recusado na edição, zero vale | `TaskTypeForm.test.tsx` | ~0,25 s |
| frontend | salário com máscara pt-BR; erro de `model_validator` visível | `UserForm.test.tsx` | ~0,05 s |
| frontend | rota sem capability mostra "sem permissão" com o menu ao lado | `AppLayout.test.tsx` | ~0,27 s |
| frontend | Esc fecha o menu do shell | `QuickAddMenu.test.tsx` | ~0,15 s |
| gate | `dangerouslySetInnerHTML` é erro de lint | `eslint-rules/no-dangerous-html.js` | 0 s |
| gate | `isLoading \|\| !data` é erro de lint | `eslint-rules/no-loading-without-error.js` | 0 s |

**Total estimado:** +2 s. Suíte inteira do frontend: **126 arquivos, 357 testes, 29 s**.
**Fixtures externas:** nenhuma. MSW para HTTP; nenhuma chamada de rede real.

## 9. Descobertas

- **Sandbox em vez de sanitizador, e por quê.** O projeto não tem biblioteca de
  sanitização (conferido em `package.json` e `pyproject.toml`), e escrever uma lista de
  tags permitida à mão é o falso conforto clássico: ela erra silenciosamente e ninguém
  descobre. O `<iframe sandbox="">` transfere a garantia para o navegador — é o mesmo tipo
  de raciocínio do RLS no §4 do `CLAUDE.md`: quem garante não é o código de aplicação. O
  preço é honesto e está no comentário do componente: **origem opaca não deixa o pai medir
  a altura do conteúdo**, então o quadro tem altura fixa e o conteúdo rola dentro dele.
  Quem quiser editar de verdade abre no editor de modelos, que é o botão ao lado. Se um dia
  o preview precisar de altura elástica, aí sim entra `dompurify` — o texto exato da
  dependência está no relatório desta spec, e nada mais no código muda: só o corpo do
  `SandboxedHtml`.
- **A regra de lint é metade da correção.** Corrigir sete telas e não proibir o padrão é
  esperar a oitava. `rito/no-loading-without-error` pegou exatamente as sete que a
  auditoria tinha achado à mão, e mais nenhuma — o que é a melhor evidência de que a regra
  está calibrada: nem falso positivo, nem furo.
- **`clear()` e não `invalidateQueries()`.** Invalidar marca como velho e **continua
  servindo** o dado antigo enquanto o refetch não volta. Entre dois escritórios, "continua
  servindo por 300 ms" é exatamente o vazamento.
- **A chave escopada é cinto, não solução.** Limpar no logout resolve o caminho normal; o
  escritório na `queryKey` do `useListPage` cobre qualquer caminho futuro que troque de
  sessão sem passar por `logout()`. Nenhum dos dois sozinho me deixaria tranquilo.
- **O 403 não pode oferecer "tentar de novo".** Tentar de novo dá 403 de novo, e um botão
  que não resolve é pior que nenhum: ele diz que o problema é transitório quando não é.
- **O estado "sem permissão" fica dentro do shell.** Guardar no `ProtectedRoute` era mais
  simples e deixava a pessoa numa página sem menu — sem explicação e sem saída.
- **`aria-activedescendant` estava documentado e não existia.** A §9 da spec 007 afirma que
  o `EntityPicker` o implementa "via índice ativo"; o índice existia, o atributo não, e as
  `<li role="option">` nem tinham `id`. Documentação que descreve o que se pretendia é uma
  forma de dívida — passou a ter teste.
- **Dígito verificador só onde o formulário já validava.** O cabeçalho de `lib/br-masks.ts`
  registra a decisão da spec 018: máscara é UX, a validação real mora no backend. Ela
  continua valendo para o cadastro de pessoas. Em `monitored-terms` a situação era outra: o
  formulário **já** validava — só que o critério errado ("11 dígitos") — e contradizia o
  servidor. Alinhar ali não desfaz a decisão da 018; desfaz uma contradição.
- **`toFixed(0)` ficou.** `StatCard` e o tamanho em KB do anexo não têm casa decimal, e
  trocá-los seria mexer no que não estava quebrado.

### Dívidas nomeadas (não entram nesta spec)

1. **PUT total + `toPayload` incompleto** (achado 1 da auditoria, três casos confirmados:
   editar um processo arquivado o desarquiva; editar uma etapa apaga o `suggested_workflow_id`
   da 053; editar um lançamento rouba o responsável). A correção pontual é frontend, mas a
   estrutural é do contrato de update do backend — e o backend estava sendo editado por
   outro ciclo enquanto esta spec rodava. **Alvo:** própria.
2. **Sanitização com dependência**, caso o preview precise de altura elástica (acima).
3. **`severity` de `integration_alerts`** é `str` livre no backend contra união fechada
   `"warning" | "critical"` no TS — nada quebra hoje, e o domínio irmão (`ai/analytics.py`)
   já tem um terceiro valor no mesmo padrão. **Alvo:** própria.
4. **`listMonitoredTerms` tipado como `ListResponse<T>`** (com `next_cursor` obrigatório)
   contra um `MonitoredTermListResponse` que não tem o campo. Impacto atual nulo — a tela
   não lê —, contrato mentiroso mesmo assim. **Alvo:** própria.
5. **Decisão por IA valida na tela, não no submit.** Os mínimos de `decision.py` agora
   aparecem como pendências enquanto o usuário preenche, mas o `AutomationBuilder` ainda
   não bloqueia o salvamento por eles. **Alvo:** própria.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Nenhuma tabela nova (spec de frontend)
- [x] `npx vitest run` verde: 126 arquivos, 357 testes, 29 s
- [x] `npx tsc --noEmit -p tsconfig.app.json` limpo
- [x] `npx eslint .` sem erros (18 avisos `react-refresh`, anteriores a esta spec)
- [x] `npx prettier --check .` limpo
- [x] Duplicação abaixo do teto: tsx 1,01% (era 1,21%) contra teto de 1,30%
- [x] Sem `any`, `as any` ou `@ts-expect-error` novos
- [x] Componentes extraídos onde bateu 3 usos (`ServerErrorAlert`, `useClickOutside`,
      `lib/format`, `QueryStateGate`)
- [ ] `ROADMAP.md` atualizado para ✅ *(texto no relatório: arquivo compartilhado, editado fora do ciclo)*
- [ ] `docs/DIVIDA-TECNICA.md` atualizado *(idem)*
- [ ] Commit `fix(138): estados, cache e contrato do frontend`
