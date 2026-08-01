# Dívida técnica consciente

> Entregável da spec 010 (refatoração da Fundação). Cada item tem uma **spec-alvo** —
> onde a dívida deve ser resolvida, não "algum dia". Se uma spec-alvo já passou e o item
> continua aqui, a próxima spec de refatoração precisa decidir: resolver agora ou
> re-atribuir com justificativa nova.

## 1. ~~`BaseRepository.list_paginated`/`build_keyset_query` não implementam o contrato de
   listagem do CLAUDE.md §6~~ — RESOLVIDO na spec 012

`GET /api/v1/users` foi o primeiro endpoint de listagem real (`account`, na 011, é 1:1 e
não precisou). `app/core/repository.py` ganhou `build_sorted_keyset_query` (ordena por uma
coluna escolhida + `id` como desempate, comparação de tupla `WHERE (col, id) > (v, id)`) e
`encode_cursor`/`decode_cursor` (base64). O `build_keyset_query`/`list_paginated` antigos
(só `id`, sem `sort_value`) foram mantidos como estão — ninguém os usa em produção, e
mexer neles quebraria `tests/unit/test_base_repository.py` sem necessidade; viram uma
função gêmea nova em vez de uma migração da antiga. `UserRepository.list_filtered` é quem
usa o keyset novo de verdade, com filtros de `role`/`is_active`/busca textual + `COUNT`
para o `total`.

## 2. Frontend sem ferramenta de cobertura instalada

`@vitest/coverage-v8` não está nas devDependencies — não dá para medir cobertura numérica
do frontend hoje. Os caminhos de erro mais críticos (`apiRequest`, `toApiError`) já têm
teste dedicado (revisado manualmente nesta spec), mas não há um número para acompanhar
regressão silenciosa de cobertura.

**Spec-alvo:** 020 (próxima refatoração). Decidir lá se vale a pena instalar (custo: mais
uma dependência de teste, tempo de instrumentação no orçamento de 90 s) ou manter revisão
manual enquanto o frontend for pequeno.

## 3. `AuthService.reset_password` tem um branch defensivo inalcançável

`service.py:121` (`if user is None: raise InvalidResetTokenError`) nunca dispara na prática
— `password_reset_tokens.user_id` tem `ON DELETE CASCADE` para `users.id`, então um token
não pode sobreviver ao usuário que apagou (e não há endpoint de exclusão de usuário ainda).
Mantido como defesa de invariante (barato, correto, documenta a intenção), mas sem teste
de integração porque forçá-lo exigiria violar a FK de propósito.

**Spec-alvo:** nenhuma — reavaliar só se um endpoint de exclusão de usuário mudar o
`ondelete` da FK (ex.: soft-delete em vez de CASCADE), o que tornaria o branch alcançável
de verdade.

## 4. `LoginPage` pede o UUID cru do tenant, não um identificador amigável

Não existe endpoint público que resolva um "código do escritório"/subdomínio para o UUID
de tenant — o contrato de `/auth/login` (spec 004) não carrega esse identificador no corpo,
só o header `X-Tenant-Id`. UX correta e honesta para o estado atual do backend, mas ruim
para um produto real.

**Spec-alvo:** 011 (Escritório/account) — já registrado como descoberta da spec 006.

## 5. Estado "offline" do frontend não implementado

A spec 006 lista "offline" como um dos estados de UI, mas não há regra de negócio nem
teste correspondente na seção 8 dela — não há detecção de `navigator.onLine`/banner de
rede hoje.

**Spec-alvo:** alguma spec de sincronização/fila offline futura (ainda sem número).

## 6. `enable_rls()` (wrapper de migration) não tem teste automatizado direto

A função pura que gera o SQL (`enable_rls_statements`) tem teste unitário
(`test_rls_helper.py`); o wrapper de 2 linhas que chama `op.execute()` por statement dentro
de uma migration do Alembic não — ele só roda como subprocesso do Alembic, fora do
processo instrumentado pelo `pytest-cov`. Na prática é exercitado (com sucesso) toda vez
que `alembic upgrade head` roda, inclusive nesta spec.

**Spec-alvo:** nenhuma — aceito como limite estrutural de cobertura via `coverage.py`
contra subprocessos externos, não uma lacuna de teste real.

## 7. Sem teste de mutação formal

O checklist "sem teste que passe por acidente" foi verificado por inspeção manual (as
asserções checam valores/mensagens exatas, não só status code genérico), não por uma
ferramenta de mutation testing (`mutmut`, `cosmic-ray`). Com 572 statements e 99% de
cobertura de linha, o retorno de instalar uma ferramenta dedicada ainda é baixo.

**Spec-alvo:** reavaliar na 020 ou quando a base de código crescer o suficiente para
inspeção manual deixar de ser confiável.

## 8. `S3FileStorage._ensure_bucket` não cobre o branch de corrida (`BucketAlreadyOwnedByYou`)

O `create_bucket` só roda quando `head_bucket` falha (bucket não existe) — testado com um
nome de bucket nunca visto (spec 011). O catch de `BucketAlreadyOwnedByYou`/
`BucketAlreadyExists` (dois workers de `pytest -n auto` tentando criar o mesmo bucket ao
mesmo tempo) exigiria forçar uma corrida de verdade entre processos, o que não é
determinístico o suficiente para um teste confiável.

**Spec-alvo:** nenhuma — aceito, mesma categoria do item 6 (código correto, caminho de
erro só exercitável por condição de corrida real).

## 9. Sem página de "aceitar convite" no frontend

`POST /api/v1/invitations/accept` existe e está testado (spec 012), mas a seção 6
("Front-end") da spec só lista `/settings/users` e `/settings/users/:id` — nenhuma rota
pública para quem recebeu o convite definir nome/senha. O fluxo é funcionalmente completo
no backend, mas ninguém consegue *usá-lo* pela UI ainda; o link do e-mail de convite (que
também não existe — sem infra de e-mail, ver regras 1-2) não tem para onde apontar.

**Spec-alvo:** a spec que trouxer a infraestrutura de e-mail (envio real de convites/reset
de senha) — as duas coisas (enviar o e-mail e ter uma página que recebe o clique)
precisam nascer juntas.

## 10. `/settings/users` não tem link de navegação — só acessível por URL direta

`/settings` continua sendo o placeholder genérico (nenhuma spec ainda construiu uma
"home" de Configurações com sub-navegação, diferente de "Conta e assinatura" na 011, que
tinha um único sub-item e pôde redirecionar direto). `/settings/users` e
`/settings/users/:id` existem e funcionam, mas exigem digitar a URL.

**Spec-alvo:** a spec que desenhar a página-índice de Configurações (ainda sem número no
roadmap) — ela precisa linkar para `/settings/users` e para os módulos de configuração
das specs 013+.
