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

## 2. ~~Frontend sem ferramenta de cobertura instalada~~ — RESOLVIDO na spec 020

`@vitest/coverage-v8@3.2.7` (mesma major do `vitest` já usado — a versão `4.x` mais
recente do pacote exige `vitest@4`, que quebraria o resto do projeto) entrou como
devDependency, com um script `test:coverage` separado (`vitest run --coverage`) — não
plugado em `npm run test`/`make test` por padrão, mesmo padrão do backend (`pytest --cov`
também é opt-in via flag, não faz parte do `addopts` default). Overhead medido: ~4-5 s
sobre os ~18-19 s da suíte sem cobertura — cabe folgado no orçamento de 90 s da spec 020.
Estado inicial: 63% de statements/lines, 74% de branches, 57% de functions — número para
acompanhar regressão a partir de agora, não uma meta a bater nesta spec.

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

## 11. `squads` é a única das 5 taxonomias simples (013-019) com nome único sensível a
    maiúsculas/acento

`uq_squads_tenant_name` (spec 013) é `UNIQUE(tenant_id, name)` puro — as outras 4
(`action_groups`/`lawsuit_types` da 014, `stages` da 015, `customer_origins` da 016) usam
`UNIQUE(tenant_id, immutable_unaccent(lower(name)))`, convenção introduzida justamente na
014 (spec 013 é anterior a ela). Hoje "Time A" e "TIME A" coexistem como times distintos no
mesmo tenant, diferente de qualquer outra taxonomia do sistema. Não foi corrigido na spec
020 porque mudar o índice único MUDA COMPORTAMENTO observável (dois registros hoje válidos
passariam a colidir com 409) — proibido em spec de refatoração (CLAUDE.md §8).

**Spec-alvo:** nenhuma spec de feature ainda toca `squads` de novo; resolver na próxima
spec que mexer no CRUD de times, com uma migration de dado (decidir o que fazer com times
duplicados que já existem) além do índice.

## 12. Busca textual das 5 taxonomias simples (013-019) não ignora acento, diferente de
    `customers` (019)

`CustomerOriginRepository.list_filtered`, `ActionGroupRepository.list_filtered`,
`LawsuitTypeRepository.list_filtered`, `StageRepository.list_filtered` e
`SquadRepository.list_filtered` filtram o campo `q` com `Model.name.ilike(f"%{query}%")`
puro — a checagem de duplicidade (`get_by_name`) dessas mesmas entidades já usa
`func.unaccent(func.lower(...))` (regra 1 de cada spec), só a busca da listagem ficou de
fora. `CustomerRepository.list_filtered` (spec 019) é o único que unaccenta os dois lados
da comparação. Não unificado na spec 020: ampliar o que a busca encontra é, em espírito,
uma mudança de comportamento (mesmo não quebrando nenhum teste hoje — nenhum teste
existente depende da busca NÃO encontrar uma variante acentuada), e a extração de um
`unaccented_search_filter` só vale a pena junto da correção, não separada dela.

**Spec-alvo:** a próxima spec que tocar qualquer uma dessas 5 telas de listagem — aplicar
`func.unaccent(func.lower(Model.name)).ilike(func.concat("%", func.unaccent(func.lower(literal(query))), "%"))`
(mesmo padrão de `app/domain/customers/repository.py`) nas 5 de uma vez, com teste
dedicado por entidade.

## 13. `CustomerOriginService.transfer`/`delete` continuam sem lógica real, mesmo com
    `customers.origin_id` já existindo desde a spec 017

Documentado como no-op nas Descobertas da spec 016 ("nada referencia `origin_id` ainda —
`customers` só chega na spec 017"). A spec 017 chegou, `customers.origin_id` é uma FK real
desde então, e a 019 até consome origens no dashboard — mas `transfer()` continua sempre
retornando `0` (não reatribui `customers.origin_id` de verdade) e `delete()` continua sem
guarda de "em uso" (excluir uma origem referenciada por um `customer` hoje estoura
`IntegrityError` não tratado → 500, em vez de um 409 com a mensagem de "transfira antes").
Mesma razão dos itens 11/12 para não resolver na 020: implementar a reatribuição real e o
guard de "em uso" é a definição de "mudar comportamento" (o teste
`test_excluir_nao_bloqueia_ainda` documenta e prova o no-op atual) — cabe a uma spec de
feature, não a este pente-fino. Comparar com `LawsuitTypeService.transfer` (spec 014, real
desde o início porque `lawsuit_types` e `action_groups` nasceram juntos) e
`StageService.transfer` (spec 015, no-op igual a este, mas ainda genuinamente bloqueado —
`lawsuits.stage_id` só chega na spec 022).

**Spec-alvo:** a spec que criar o consumidor real de `origin_id` além de `customers` (já
existe) — ou uma spec de correção dedicada, já que a dependência que faltava (017) já
chegou. Renomear/atualizar o comentário e o teste
`test_excluir_nao_bloqueia_ainda`/`test_transferencia_com_ids_validos_retorna_200` junto.
