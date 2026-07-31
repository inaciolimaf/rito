# 099 — Deploy

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 098 · **Status:** ⬜ pendente

---

## 1. Objetivo

Tornar o Rito instalável e operável por alguém que não participou do desenvolvimento.

## 2. Escopo

- Dockerfile multi-stage de produção (backend e frontend)
- Docker Compose de produção
- Migrations no boot, com trava
- Seed opcional de taxonomias
- Variáveis documentadas e validadas
- Runbook de operação
- Backup e restauração
- Provisionamento do primeiro tenant

## 3. Fora de escopo

- Kubernetes, Terraform e CI/CD de deploy (é do time de infra)

## 4. Modelo de dados

```sql
CREATE TABLE migration_locks (
  id SMALLINT PRIMARY KEY DEFAULT 1,
  locked_by TEXT, locked_at TIMESTAMPTZ,
  CHECK (id = 1)
);
```
Migration `099_migration_lock.py`. Impede que duas instâncias subindo ao mesmo tempo apliquem migration em paralelo.

## 5. Comandos operacionais

```bash
rito db upgrade              # aplica migrations com trava
rito db seed --taxonomies    # semeia catálogos globais
rito tenant create --name --slug --admin-email
rito tenant seed-defaults --slug        # taxonomias padrão do tenant
rito health                  # verifica dependências
rito backup create|restore
```

## 6. Front-end

Build estático servido por nginx, com cache imutável para assets versionados e `no-cache` para
o `index.html`.

## 7. Regras de negócio

1. Imagem multi-stage: build separado de runtime. Imagem final **sem** toolchain de build.
2. Container roda como usuário **não-root**.
3. Migrations aplicadas no boot, protegidas por trava com timeout de 5 min. Segunda instância espera.
4. Falha de migration **impede** a aplicação de subir — nunca sobe com schema inconsistente.
5. Todas as variáveis obrigatórias são validadas no boot; faltando alguma, falha rápido com mensagem clara listando quais.
6. `SECRET_KEY` com valor de exemplo em produção → recusa subir.
7. Seed de taxonomias globais (tribunais, sistemas, cargos, instituições, grupos DRE, feriados) é idempotente e roda no boot.
8. Seed de tenant (grupos de ação, etapas, tarefas, categorias, origens) roda na criação do tenant.
9. Healthcheck do container usa `/health`; o orquestrador usa `/health/ready`.
10. Desligamento gracioso: para de aceitar requisição, termina as em andamento, fecha conexões. Celery termina a task corrente.
11. Backup: `pg_dump` do banco e sincronização do bucket. Restauração documentada e **testada**.
12. Runbook cobre: subir, atualizar, reverter, restaurar backup, rotacionar segredo, criar tenant, diagnosticar sincronização parada.
13. Log em stdout, formato JSON — quem coleta é o orquestrador.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | imagem sobe e serve com Postgres externo | ~0,8 s |
| integração | variável obrigatória faltando → falha com mensagem | ~0,3 s |
| integração | `SECRET_KEY` de exemplo → recusa subir | ~0,2 s |
| integração | migration falha → aplicação não sobe | ~0,3 s |
| integração | **trava impede migration concorrente** | ~0,4 s |
| integração | seed global é idempotente | ~0,3 s |
| integração | `tenant create` provisiona com taxonomias | ~0,5 s |
| integração | desligamento gracioso termina as requisições | ~0,4 s |
| **meta** | container não roda como root | ~0,2 s |
| **meta** | imagem final sem toolchain de build | ~0,2 s |

**Total:** ~3,6 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] `docker compose -f docker-compose.prod.yml up` funciona do zero
- [ ] Runbook em `docs/RUNBOOK.md`, completo
- [ ] Restauração de backup testada de verdade
- [ ] Commit `feat(099): deploy`
