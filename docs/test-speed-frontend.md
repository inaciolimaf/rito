# Velocidade dos testes do frontend (Vitest)

Playbook `test-speed`, parte frontend. Medições feitas numa máquina de 12 núcleos
**compartilhada com outros agentes**: a carga do sistema ficou entre 7 e 38 durante as
medições. Por isso o tempo de parede oscila muito (a mesma árvore deu 225 s e 414 s). O
tempo de CPU é mais estável e vem junto. Cada comparação foi feita com execuções
intercaladas, em pares. Nenhum número aqui é de runner de CI de 2 núcleos.

Suíte: 126 arquivos, 357 testes (conferido no mesmo base de `chore/project-standard`).

## Onde está o tempo (medido com `--maxWorkers=1`, o modo de `make test`)

| Fase do Vitest (soma entre arquivos) | Segundos (execução típica) |
|---|---|
| environment (jsdom por arquivo) | 45 a 62 |
| collect (importar os módulos) | 22 a 30 |
| setup | 19 a 28 |
| tests | 37 a 50 |

Os arquivos mais lentos ficam entre 1 e 3 s: `TemplateEditorPage`, `PartySelector`,
`FilterBar`, `GlobalSearch`, `StageForm` e os formulários em geral. Não há um arquivo que
domine a suíte.

## Medições

| Configuração | Execução | Parede | CPU (user+sys) |
|---|---|---|---|
| base: forks, 1 worker | 1 | 225 s | 258 s |
| base: forks, 1 worker | 2 | 414 s | 334 s |
| A/B intercalado: forks, 1 worker | 1 | 208 s | 235 s |
| A/B intercalado: threads, 1 worker | 1 | 153 s | 204 s |
| A/B intercalado: forks, 1 worker | 2 | 183 s | 237 s |
| A/B intercalado: threads, 1 worker | 2 | 171 s | 224 s |
| depois: threads, 1 worker (`pool: "threads"` no config) | 1 | 178 s | 235 s |

Threads ganhou nos dois pares, tanto em parede (-27 s e -12 s) quanto em CPU (-31 s e -13 s).
A última linha é uma execução isolada sob carga, sem par intercalado: serve para confirmar
que a suíte continua verde, não como medição de ganho.

## O que foi aplicado

- `frontend/vite.config.ts`: `pool: "threads"`. O comentário no próprio config registra a
  medição. Nenhum teste precisa de isolamento de processo (não há módulo nativo nem
  `process.chdir`).

## O que não foi aplicado, e por quê

- **`--maxWorkers=3` no CI (`npm run test:coverage`).** O playbook recomenda 3 workers num
  runner de 2 núcleos. Este host tem 12 núcleos disputados e não reproduz esse caso; ganho
  de CI não foi medido. `scripts/run-tests.sh` mantém `--maxWorkers=1` de propósito (disputa
  com o pytest em `make test`). Fica como medição pendente num run real do CI.
- **`css: false`.** Nenhum teste importa CSS: a única importação é `src/main.tsx`, que os
  testes não alcançam. Desligar o processamento não teria efeito mensurável, então o config
  ficou como estava.
- **Esperas reais por fake timers.** São cinco trechos (`ProcessNumberField` 400 ms,
  `TemplateEditorPage` 100 ms, `EntityPicker` 40 e 400 ms, `useAutosave` 50 ms): cerca de
  1 s somado de parede serial, perto de 3% da fase de testes. O `EntityPicker` tem uma corrida
  real entre respostas com atrasos de 300 ms e 10 ms, e trocá-la por fake timers mudaria o
  que o teste exercita. Não compensou para um ganho de 1 s.

## Lint

`tsc --noEmit`, `prettier --check .` e `eslint .` passam. O eslint tem 0 erros e 18 avisos,
todos já existentes (`react-refresh/only-export-components`). A configuração não mudou.
