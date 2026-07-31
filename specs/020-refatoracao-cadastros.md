# 020 — 🔧 REFATORAÇÃO — Cadastros

**Fase:** 1 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 011–019 · **Status:** ⬜ pendente

---

## 1. Objetivo

Primeira refatoração sobre código de domínio. Aqui aparece o padrão que vai se repetir 70 vezes:
entidade + CRUD + listagem + filtro + transferência antes de excluir. Se esse padrão não for
extraído agora, ele será copiado e colado dezenas de vezes.

> Refatoração não muda comportamento. Testes de 011–019 passam **sem edição**.

## 2. Alvo principal: extrair o padrão CRUD

Cinco entidades já repetiram a mesma estrutura (grupos, tipos de ação, etapas, origens, times):

- [ ] `CrudRouter` genérico: monta GET lista, GET id, POST, PUT, DELETE a partir de service + schemas
- [ ] `TransferableMixin`: comportamento de "transferir antes de excluir", hoje duplicado em 3 lugares
- [ ] `ActivatableMixin`: `is_active` + filtro por status
- [ ] `useCrudResource` no frontend: query, mutation, invalidação e toast em um hook
- [ ] `SettingsListPage` genérica: recebe schema e endpoint, monta a tela inteira

Se a extração ficar boa, uma taxonomia nova passa a custar ~30 linhas.

## 3. Checklist

### Cobertura
- [ ] Toda regra numerada das specs 011–019 tem teste
- [ ] Caminhos de erro cobertos, não só o feliz
- [ ] Todas as 8 tabelas novas com teste de isolamento entre tenants
- [ ] Constraints do banco testadas (não só a validação da aplicação)

### SOLID
- [ ] Nenhum router com query
- [ ] Nenhum service importando `httpx` direto (ViaCEP atrás de `AddressLookup`)
- [ ] Validadores de CPF/CNPJ/telefone em módulo próprio, sem dependência de framework
- [ ] Repositórios herdando de `BaseRepository`, sem SQL solto

### Duplicação
- [ ] Padrão CRUD extraído (item 2)
- [ ] Validação duplicada entre Pydantic e Zod com fonte única
- [ ] Máscaras de formatação em um único lugar
- [ ] `TransferBeforeDeleteDialog` usado pelos 3 consumidores

### Banco
- [ ] Toda FK com índice
- [ ] Índices de 019 realmente usados (`EXPLAIN` nas 5 queries principais)
- [ ] Nenhuma query de listagem acima de 5 statements (N+1)
- [ ] Seeds idempotentes e rápidos

### Tipos
- [ ] `mypy --strict` e `tsc --noEmit` verdes
- [ ] Zero `Any` / `as any` sem justificativa

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] Seeds de teste em escopo de sessão
- [ ] E2E com no máximo 3 jornadas até aqui

## 4. Entregáveis

1. Padrão CRUD extraído e as 5 entidades migradas para ele
2. `docs/DECISOES.md` atualizado
3. `CLAUDE.md` documentando `CrudRouter` e `useCrudResource`
4. `test-timing.json` atualizado
5. Dívidas em `docs/DIVIDA-TECNICA.md`

## 5. Definição de pronto

- [ ] Testes de 011–019 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Uma taxonomia nova custa < 50 linhas (demonstre)
- [ ] Commit `refactor(020): extração do padrão CRUD e pente fino dos cadastros`
