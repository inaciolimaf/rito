# Velocidade do e2e (Playwright): medições e decisões

Medido no branch `worktree-agent-a7c48f672fbae1d34`, rebaseado sobre `chore/project-standard`
(9f34ebb). Máquina de 12 núcleos compartilhada com outros agentes rodando vitest e pytest ao
mesmo tempo, então os tempos oscilam. Comparações feitas back-to-back, com o banco de e2e já
semeado.

## Números

Banco de e2e próprio (`rito_e2e_speed`), backend uvicorn, frontend `vite` em modo dev.

| Execução | Configuração | Wall-clock | Resultado |
|---|---|---|---|
| A (linha de base, banco recém-migrado) | dev, 3 workers | 77,8 s | 4 passa, 7 falham |
| B (linha de base, quente) | dev, 3 workers | 57,3 s | 10 passa, 1 falha (navegação) |
| C (linha de base, repetida) | dev, 3 workers | 50,3 s | 10 passa, 1 falha (navegação) |
| D | build + `vite preview`, 3 workers | 62,0 s | 10 passa, 1 falha (navegação) |
| E | dev, 6 workers | 32,0 s | 10 passa, 1 falha (navegação) |
| F (repetida) | dev, 6 workers | 25,8 s | 8 passa, 3 falham (navegação, financeiro, agenda) |

Medidas soltas:

- Seed do e2e (`scripts/seed_e2e.py`): 1,2 s.
- `vite build` sozinho: cerca de 14 s. `npm run build` (com `tsc -b`): cerca de 50 s.
- Login na API (`POST /api/v1/auth/login`): 0,09 a 0,35 s por chamada.

A falha da jornada 2 (navegação: `/posts` redireciona para `/home` e o teste espera a URL de
origem) já existia antes e continua. O teste não foi alterado.

## Decisões

**Mantido: `vite` em modo dev.** O build de produção não ganhou tempo. Ele custa cerca de 14 s
no arranque e as jornadas ficaram mais lentas (cada uma 2 a 4 s a mais). Então o servidor
de dev continua. O `webServer` do frontend não mudou.

**Mantido: teto de 3 workers.** Seis workers cortaram o wall-clock quase pela metade (50 s para
26 a 32 s), mas a execução F reprovou três jornadas com `expect` de 5 s estourando em
`getByText` esperando dado que a API acabou de gravar. É o sintoma de inanição de CPU que o
comentário de `playwright.config.ts` descreve (dívida 33). Com a máquina disputada, seis não é
seguro. Três continua sendo o teto.

**Não feito: login compartilhado (`storageState`).** Não há projeto somente-leitura. As nove
jornadas que usam a API já logam por API uma vez cada (0,1 a 0,35 s), e as jornadas de UI logam
pelo formulário, que faz parte do que elas testam. O único candidato, a navegação, faz login
pelo formulário e é justamente a jornada que falha. Economia estimada: menos de 1 s por
execução, com risco de mexer no teste que quebra.

**Não feito: shards.** São 11 jornadas. O setup (seed, backend, vite) é uma fração pequena do
wall-clock, e cada shard repetiria esse setup. No runner do CI, com 2 núcleos, o teto calculado
é 1 worker de qualquer forma, então o paralelismo de workers não vale lá.

**Não feito: servidores reaproveitados.** Já é o comportamento local (`reuseExistingServer`
ligado fora do CI).

**Não feito: setup por API.** Já é o caso: as jornadas criam dados pela API e só a parte a
testar vai pela UI.

## Achados

- O boot do backend com `RUN_MIGRATIONS_ON_BOOT` ligado sai com código 3 e sem mensagem no
  log do Playwright quando falta uma variável, como `S3_ENDPOINT_URL`. A causa só aparece
  rodando `uvicorn` direto. Para rodar o e2e localmente é preciso exportar as variáveis do job
  `e2e` do `.github/workflows/ci.yml` (incluindo `S3_*`), e apontar `DATABASE_URL` para um
  banco próprio.
- `e2e/` não tem `tsconfig.json` nem `@types/node`. `tsc --noEmit` do frontend acusa
  `node:fs`, `node:path` e `process` nos specs. Não é gate de nada hoje; fica como dívida.
- Entre a execução A e a B o único que mudou foi o banco. Na primeira execução sobre um banco
  recém-migrado, sete jornadas falharam. Por isso a linha de base quente é a B/C.
