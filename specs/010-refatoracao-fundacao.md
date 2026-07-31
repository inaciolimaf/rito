# 010 — 🔧 REFATORAÇÃO — Fundação

**Fase:** 0 · **Tipo:** refatoração · **Orçamento:** reduzir, nunca aumentar
**Depende de:** 001–009 · **Status:** ⬜ pendente

---

## 1. Objetivo

Pente fino em tudo que foi construído em 001–009, **antes** que 90 specs sejam empilhadas em
cima. Erro de fundação corrigido aqui custa horas; corrigido na spec 070 custa semanas.

> Refatoração **não muda comportamento**. Todo teste existente continua passando **sem edição**.
> Se um teste precisou mudar, ou era teste ruim (justifique) ou você mudou comportamento (não faça).

## 2. Checklist

### Cobertura
- [ ] Todo caminho de erro tem teste (não só o caminho feliz)
- [ ] Toda regra de negócio numerada nas specs 001–009 tem teste correspondente
- [ ] Todo modelo com `tenant_id` tem teste de isolamento
- [ ] Sem teste que passe por acidente (mutar a asserção deve quebrá-lo)

### SOLID
- [ ] Nenhum `router` executa query — só chama `service`
- [ ] Nenhum `service` importa cliente HTTP ou SDK direto — só interface injetada
- [ ] Nenhum `repository` contém regra de negócio
- [ ] Interfaces pequenas e focadas
- [ ] Dependências vêm por `Depends`, não por import de módulo concreto

### Duplicação
- [ ] Regra dos 3 usos aplicada: o que repetiu 3× virou componente ou helper
- [ ] Nenhuma validação duplicada entre Pydantic e Zod sem fonte única
- [ ] Nenhuma constante mágica repetida

### Tipos
- [ ] Zero `Any` sem justificativa em comentário
- [ ] Zero `# type: ignore` sem justificativa
- [ ] Zero `as any` / `as unknown` no frontend
- [ ] `mypy --strict` e `tsc --noEmit` verdes

### Banco
- [ ] Toda FK tem índice
- [ ] Todo filtro frequente tem índice
- [ ] Nenhuma migration editada após commit
- [ ] `enable_rls` aplicado em 100% das tabelas de domínio

### Performance dos testes
- [ ] Wall-clock **< 90 s** (folga para a fase 1)
- [ ] Nenhum `sleep` em teste
- [ ] Fixtures caras em escopo de sessão
- [ ] E2E com no máximo 2 jornadas até aqui

### Segurança
- [ ] Nenhum segredo no código ou nos testes
- [ ] Nenhum stack trace vazando em resposta
- [ ] Rate limit ativo no login
- [ ] Nenhuma rota `/api/v1` sem declaração de permissão

## 3. Entregáveis

1. Correções aplicadas
2. `docs/DECISOES.md` com as decisões arquiteturais tomadas até aqui e o porquê
3. `CLAUDE.md` atualizado se alguma convenção mudou
4. `test-timing.json` atualizado
5. Dívidas conscientes registradas em `docs/DIVIDA-TECNICA.md`, cada uma com a spec-alvo

## 4. Definição de pronto

- [ ] Checklist inteiro percorrido (itens não aplicáveis marcados como tal)
- [ ] Todos os testes anteriores passam **sem edição**
- [ ] Wall-clock < 90 s
- [ ] `make lint` verde
- [ ] `ROADMAP.md` → ✅
- [ ] Commit `refactor(010): pente fino da fundação`
