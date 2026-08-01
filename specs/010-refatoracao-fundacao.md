# 010 — 🔧 REFATORAÇÃO — Fundação

**Fase:** 0 · **Tipo:** refatoração · **Orçamento:** reduzir, nunca aumentar
**Depende de:** 001–009 · **Status:** ✅ concluída

---

## 1. Objetivo

Pente fino em tudo que foi construído em 001–009, **antes** que 90 specs sejam empilhadas em
cima. Erro de fundação corrigido aqui custa horas; corrigido na spec 070 custa semanas.

> Refatoração **não muda comportamento**. Todo teste existente continua passando **sem edição**.
> Se um teste precisou mudar, ou era teste ruim (justifique) ou você mudou comportamento (não faça).

## 2. Checklist

### Cobertura
- [x] Todo caminho de erro tem teste (não só o caminho feliz) — cobertura de `app/` foi de
      96% para 99%; 14 testes novos de caminho de erro (ver Descobertas)
- [x] Toda regra de negócio numerada nas specs 001–009 tem teste correspondente
- [x] Todo modelo com `tenant_id` tem teste de isolamento — `refresh_tokens` e
      `password_reset_tokens` ganharam teste direto (só tinham prova indireta via `users`)
- [x] Sem teste que passe por acidente — inspeção manual (assertivas checam
      valor/mensagem exata, não status genérico); sem ferramenta de mutation testing
      formal ainda (dívida registrada)

### SOLID
- [x] Nenhum `router` executa query — só chama `service`
- [x] Nenhum `service` importa cliente HTTP ou SDK direto — só interface injetada
- [x] Nenhum `repository` contém regra de negócio
- [x] Interfaces pequenas e focadas
- [x] Dependências vêm por `Depends`, não por import de módulo concreto

### Duplicação
- [x] Regra dos 3 usos aplicada — nenhuma estrutura repetida 3× ainda no tamanho atual
      do projeto (auditado, nada a extrair)
- [x] Nenhuma validação duplicada entre Pydantic e Zod sem fonte única
- [x] Nenhuma constante mágica repetida

### Tipos
- [x] Zero `Any` sem justificativa em comentário — 6 usos, todos comentados nesta spec
- [x] Zero `# type: ignore` sem justificativa — 2 usos, ambos comentados
- [x] Zero `as any` / `as unknown` no frontend sem justificativa — 1 uso (`test/setup.ts`,
      polyfill de `matchMedia`), comentado
- [x] `mypy --strict` e `tsc --noEmit` verdes

### Banco
- [x] Toda FK tem índice — migration 006 adiciona os 3 que faltavam
      (`refresh_tokens.user_id`, `refresh_tokens.family_id`, `password_reset_tokens.user_id`)
- [x] Todo filtro frequente tem índice — `family_id` (filtrado em `revoke_family`) incluído
- [x] Nenhuma migration editada após commit — correção via migration nova (006)
- [x] `enable_rls` aplicado em 100% das tabelas de domínio (`users`, `refresh_tokens`,
      `password_reset_tokens`; `tenants` não é tabela de domínio tenant-scoped)

### Performance dos testes
- [x] Wall-clock **< 90 s** — medido em 27 s (ver `test-timing.json`)
- [x] Nenhum `sleep` em teste
- [x] Fixtures caras em escopo de sessão
- [x] E2E com no máximo 2 jornadas até aqui (inalterado)

### Segurança
- [x] Nenhum segredo no código ou nos testes
- [x] Nenhum stack trace vazando em resposta
- [x] Rate limit ativo no login
- [x] Nenhuma rota `/api/v1` sem declaração de permissão (guarda-corpo automatizado desde
      a spec 005, `test_permission_coverage.py`)

## 3. Entregáveis

1. Correções aplicadas
2. `docs/DECISOES.md` com as decisões arquiteturais tomadas até aqui e o porquê
3. `CLAUDE.md` atualizado se alguma convenção mudou
4. `test-timing.json` atualizado
5. Dívidas conscientes registradas em `docs/DIVIDA-TECNICA.md`, cada uma com a spec-alvo

## 4. Definição de pronto

- [x] Checklist inteiro percorrido (itens não aplicáveis marcados como tal)
- [x] Todos os testes anteriores passam **sem edição** — 59 testes pré-010 inalterados,
      14 novos adicionados
- [x] Wall-clock < 90 s — 27 s medido
- [x] `make lint` verde (ruff, black, mypy --strict, eslint, tsc, prettier)
- [x] `ROADMAP.md` → ✅
- [x] Commit `refactor(010): pente fino da fundação`
