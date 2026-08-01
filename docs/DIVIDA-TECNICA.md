# Dívida técnica consciente

> Entregável da spec 010 (refatoração da Fundação). Cada item tem uma **spec-alvo** —
> onde a dívida deve ser resolvida, não "algum dia". Se uma spec-alvo já passou e o item
> continua aqui, a próxima spec de refatoração precisa decidir: resolver agora ou
> re-atribuir com justificativa nova.

## 1. `BaseRepository.list_paginated`/`build_keyset_query` não implementam o contrato de
   listagem do CLAUDE.md §6 ainda

O contrato real (`cursor` em base64 codificando `(sort_value, id)`, `next_cursor`, `total`,
ordenação por campo escolhido) exige um consumidor real para ter forma — hoje
`list_paginated` só ordena por `id` e devolve uma lista crua, porque nenhum endpoint de
listagem existe até a 009. Implementá-lo agora, sem uso, seria design especulativo.

**Spec-alvo:** a primeira spec de listagem real (011 ou 012, o que vier primeiro com uma
tela `<DataTable>` de verdade). Nessa spec, `BaseRepository` ganha o keyset completo — não
antes.

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
