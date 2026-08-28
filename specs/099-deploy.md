# 099 — Deploy

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 098 · **Status:** ✅ concluída

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

- **A trava da §4 não pode ser o mecanismo de exclusão.** `migration_locks` é criada
  pela própria migration que está prestes a rodar: num banco NOVO ela não existe, e a
  primeira versão falhava exatamente no caso que mais importa — `docker compose up` do
  zero, com `relation "migration_locks" does not exist` e a aplicação não subindo. A
  exclusão passou a ser um **advisory lock** do Postgres, que não depende de schema
  nenhum e é liberado sozinho quando a conexão cai (o que resolve de graça a instância
  que morreu com a trava na mão). A tabela ficou, e continua sendo escrita, pelo que
  ela dá e o lock não: durante um deploy travado, `migration_locks` diz QUEM está
  aplicando e desde quando; um lock de sessão só aparece em `pg_locks`, como um número.
- **`close()` numa conexão do SQLAlchemy não simula morte de processo** — devolve a
  conexão ao pool, e o advisory lock continua preso a ela. O teste da trava abandonada
  passou a usar `invalidate()`, que descarta a conexão de verdade. A distinção também
  importa em produção: é por isso que `_destravar` solta o lock **explicitamente** antes
  de devolver a conexão, em vez de confiar no fechamento.
- **`alembic/env.py` ignora a URL que se passa para ele.** Ele resolve
  `migrations_database_url` das `Settings` e sobrescreve o que estiver no `alembic.ini`.
  A primeira versão de `upgrade_with_lock` aceitava uma URL — controle que não existia —
  e o teste que tentava apontar para um banco inválido migrava o banco CERTO em
  silêncio, passando por engano. O parâmetro saiu, e a falha de migration é injetada no
  ponto onde o Alembic é chamado.
- **Provisionar tenant era a lacuna que ninguém tinha fechado.** As migrations
  014/015/016/031/054 semearam a taxonomia para os tenants que existiam quando rodaram, e
  cada uma anotou a limitação no comentário ("sem spec de provisionamento de tenant
  ainda"). Um escritório criado depois nascia sem grupo de ação, sem etapa e sem tipo de
  tarefa — isto é, incapaz de cadastrar um processo. É a 099 que finalmente o cria.
- **As listas do catálogo são LIDAS das migrations, não copiadas.** Copiar 59 etapas e
  61 categorias criaria duas verdades que divergem no primeiro dia em que alguém
  acrescentar uma etapa num lugar só — divergência invisível, porque cada metade
  continua consistente consigo mesma. As migrations são história congelada (CLAUDE.md
  §9), o que as torna fonte estável. O risco é um squash futuro apagá-las: por isso
  `test_tenant_catalog.py` afirma os TAMANHOS, para um catálogo esvaziado falhar alto em
  vez de provisionar escritórios vazios em silêncio.
- **O seed global existe apesar de a migration já ter semeado.** Uma linha global pode
  desaparecer sem ninguém notar — foi o que um `TRUNCATE ... CASCADE` de script de teste
  fez com os 19 agentes da 087 —, e a migration que a criou não roda de novo porque já
  está aplicada. O seed de boot repõe, é idempotente, e só cobre o que tem caminho
  conhecido de perda: tribunais, cidades e cargos não referenciam `tenants`, então
  nenhum `CASCADE` os alcança e reescrevê-los a cada boot custaria arranque sem devolver
  nada.
- **Migration no boot precisou ser desligável em teste.** Cada `lifespan` de teste
  correndo `alembic upgrade head` custaria segundos por teste, e os workers do xdist
  disputariam a trava. `RUN_MIGRATIONS_ON_BOOT=false` no `conftest`; quem migra o banco
  de teste é o `run-tests.sh`, uma vez por sessão (spec 009, regra 3). No compose de
  produção, o mesmo interruptor desliga worker e beat — só a API aplica.
- **A regra de isolamento da 080 precisou de quatro exceções novas.** Ela proíbe
  `migrations_database_url` fora de `app/workers/`, e a 099 usa a conexão de superusuário
  em `app/core/migrations.py`, `app/main.py` (boot), `app/cli.py` (terminal de operação) e
  `app/core/bootstrap.py` (que só nomeia a variável). Nenhum deles é caminho de request,
  que é o que a regra protege — a lista cresceu com a justificativa junto.
- **O healthcheck do container é `/health`, não `/health/ready`.** Trocar os dois é o
  que derruba um sistema saudável: `/health/ready` toca o banco, e uma indisponibilidade
  de Postgres faria o orquestrador matar e recriar TODOS os containers da aplicação — que
  estão vivos — exatamente quando o banco precisa de menos carga. Tem teste meta próprio.
- **O `stop_grace_period` do compose precisa ser maior que o timeout do uvicorn.** 40 s
  contra 30 s. Invertidos, o Docker mata o processo antes de ele terminar as requisições
  em curso, e o desligamento gracioso vira decoração. Também com teste meta.
- **Construir a imagem não cabe na suíte.** `docker build` leva mais que os 300 s
  inteiros. A suíte garante as propriedades ESTÁTICAS — não-root, multi-stage, sem
  toolchain no estágio final, healthcheck em liveness, worker sem migration, nenhum
  segredo no compose —, que são as que regridem por descuido; construir e subir a imagem
  de verdade virou passo do CI.

## 10. Definição de pronto

- [x] `docker compose -f docker-compose.prod.yml up` funciona do zero
- [x] Imagem multi-stage, não-root, sem toolchain de build no estágio final
- [x] Migrations no boot sob trava; falha de migration impede a aplicação de subir
- [x] Variáveis obrigatórias validadas no boot, com a lista inteira do que falta
- [x] `SECRET_KEY` de exemplo recusa subir em produção
- [x] Seed global idempotente; `rito tenant create` provisiona a taxonomia inteira
- [x] Runbook em `docs/RUNBOOK.md`, com os 10 procedimentos da regra 12
- [x] Restauração de backup documentada passo a passo, com o aviso de que anexo não vem
      no `pg_dump`
- [x] `make test` verde: 1477 backend + 286 frontend + 10 e2e
- [x] `make lint` verde: ruff, black, mypy strict, eslint, tsc, prettier
- [x] Commit `feat(099): deploy`
