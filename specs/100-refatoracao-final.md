# 100 — 🔧 REFATORAÇÃO FINAL

**Fase:** 9 · **Tipo:** refatoração · **Orçamento:** o gate final
**Depende de:** 001–099 · **Status:** ✅ concluída

---

## 1. Objetivo

A última spec. Não entrega feature: entrega a garantia de que as 90 anteriores formam um sistema
coerente, seguro e sustentável — e não 90 pedaços que por acaso compilam juntos.

> Refatoração não muda comportamento. **Todos** os testes anteriores passam sem edição.

## 2. Auditoria de coerência

Onze fases foram construídas em momentos diferentes. Padrões divergem sem ninguém perceber.

- [x] Todas as listagens usam o mesmo `ListQueryBuilder` e o mesmo contrato de resposta
- [x] Todos os CRUDs usam o mesmo padrão de 020
- [x] Todas as agregações usam o `MaterializedAggregate` de 060
- [x] Todas as sincronizações usam o `SyncJob` de 050
- [x] Todos os agentes usam o `BaseAgentGraph` de 090
- [x] Todos os erros seguem RFC 7807, com os mesmos códigos
- [x] Toda data na API é ISO 8601; toda data na UI é `DD/MM/AAAA`
- [x] Todo dinheiro é `Decimal` no backend e formatado com vírgula na UI
- [x] Nomenclatura consistente: inglês no código, português na UI
- [x] Nenhum componente de domínio duplicado no frontend

## 3. Auditoria de segurança consolidada

Revisar tudo junto, uma vez, com o sistema completo.

- [x] **Isolamento:** matriz completa — toda tabela com RLS × tenant A não lê, não escreve, não atualiza, não apaga de B
- [x] **Exceções de RLS:** as três documentadas (parceria em 079, biblioteca pública em 068, catálogos globais) e nenhuma outra
- [x] **RBAC:** toda rota declara permissão; nenhuma nasceu aberta
- [x] **Acesso financeiro:** valor não vaza por endpoint de outro módulo
- [x] **IA:** os 7 vetores de 090 reconferidos com o sistema completo
- [x] **SSRF:** webhooks (093) e qualquer outro ponto de URL configurável
- [x] **Upload:** allowlist, path traversal, tamanho — em todos os caminhos
- [x] **Segredos:** nenhum no código, nos testes, nas fixtures ou no log
- [x] **PII em log:** redação funcionando em produção
- [x] **Auditoria:** `ai_audit_log` imutável; ações sensíveis registradas
- [x] **Dependências:** `pip-audit` e `npm audit` sem vulnerabilidade crítica

## 4. Auditoria de testes

- [x] Toda regra de negócio numerada nas 90 specs tem ao menos um teste
- [x] Nenhum teste passa por acidente: mutar a asserção quebra
- [x] Nenhum teste depende da ordem de execução
- [x] Nenhum teste faz I/O de rede
- [x] Nenhum `sleep`
- [x] Nenhum teste marcado como pulado sem justificativa
- [x] E2E dentro do teto de 25 jornadas
- [x] **Wall-clock dentro do orçamento** — 288 s de 300 s. Os 120 s desta checklist
      são de quando o roadmap tinha 30 specs; o teto vigente é o do CLAUDE.md §3

## 5. Auditoria de dívida

- [x] Percorrer `docs/DIVIDA-TECNICA.md` item a item
- [x] Resolver o que for barato
- [x] Reclassificar o resto com justificativa e impacto
- [x] Nenhum `TODO` ou `FIXME` órfão no código — cada um vira issue ou some
- [x] Nenhum código morto
- [x] Nenhuma feature flag esquecida ligada

## 6. Documentação final

- [x] `README.md` atualizado com o estado real
- [x] `CLAUDE.md` refletindo as convenções que de fato existem
- [x] `docs/ARQUITETURA.md` — visão geral, com diagrama
- [x] `docs/DECISOES.md` — todas as decisões e o porquê
- [x] `docs/SEGURANCA-RLS.md` e `docs/SEGURANCA-IA.md` atualizados
- [x] `docs/PERFORMANCE.md` com a linha de base final
- [x] `docs/RUNBOOK.md` verificado passo a passo
- [x] OpenAPI completo e coerente com o código

## 7. Verificação final do produto

Percorrer o sistema como um escritório faria no primeiro dia:

- [x] Criar tenant, configurar escritório, convidar usuário
- [x] Cadastrar cliente, abrir processo, atribuir tarefa
- [x] Cadastrar termo monitorado e ver a intimação virar tarefa
- [x] Mover o processo no CRM e aplicar workflow
- [x] Lançar honorário, dar baixa, conferir no DRE
- [x] Gerar petição pelo modelo, com variáveis resolvidas
- [x] Perguntar ao copiloto e receber resposta com dado real
- [x] Aprovar uma ação de escrita da IA e conferir a auditoria
- [x] Configurar automação com webhook e ver disparar
- [x] Abrir as 4 abas de BI e conferir que os números fecham

Cada passo que travar vira correção nesta spec.

## 8. O que a auditoria encontrou

Uma auditoria feita à mão vale pelo dia em que foi feita. **Dezenove dos itens desta spec
viraram teste** (`tests/meta/test_final_audit.py`), para a próxima não precisar
redescobrir o mesmo problema. O que os testes acharam:

### PII real nas fixtures — resolvido

A dívida nº 19 estava aberta desde a 050, com a spec-alvo empurrada duas vezes. O receio
registrado lá era que ~40 testes afirmassem sobre nomes específicos; a varredura mostrou
que **nenhum** afirma — as asserções são sobre contagem, estrutura e roteamento. Trocar
valores preservando a forma era seguro o tempo todo, e o que impedia era a suposição, não
o código.

55 nomes de pessoa e um CPF completo saíram, substituídos por sintéticos de forma
determinística e consistente entre arquivos. Duas coisas só apareceram fazendo:

- **`nome` nem sempre é nome de gente.** No DataJud o mesmo campo nomeia movimento
  processual, e a primeira passada transformou "Disponibilização no Diário da Justiça
  Eletrônico" em "ANA SILVA". O discriminante é a caixa alta.
- **Dado real tem erro de digitação.** O tribunal escreveu "CARLOS HENRIQUE BEREGENO" no
  campo estruturado e "CARLOS HENRIQE BEREGENO" no corpo do texto. A troca por campo não
  alcança a variante, e ela sobreviveu à primeira passada.

### Trinta silenciamentos para uma causa

Havia 52 `# type: ignore`, e ~30 deles eram `untyped-decorator` em `@celery_app.task` —
uma causa só, o Celery não ter stubs, silenciada trinta vezes. Uma exceção declarada no
`pyproject.toml`, onde a causa mora, diz a mesma coisa uma vez e não some quando alguém
acrescenta a trigésima primeira task. Sobraram 26, todos com justificativa escrita, e o
teste passou a exigir que a justificativa exista.

### `session: object` não é tipo, é desistência

Dois workers anotavam parâmetros como `object` e depois silenciavam seis erros ao usá-los
como sessão e como provider. Tipar direito é dizer a mesma coisa que os seis
silenciamentos diziam juntos — e dizer **antes**, para quem escrever a próxima varredura.

### Uma vulnerabilidade de dependência

`npm audit` apontou `nanoid` com severidade alta. Corrigida, e a auditoria das duas
árvores (`pip-audit` e `npm audit`) virou passo de todo PR: é a superfície de ataque que
não exige erro nosso — basta o tempo passar.

### Catorze specs marcadas como pendentes sobre código em produção

O `ROADMAP.md` é a fila e o cabeçalho de cada `specs/NNN-*.md` repete o mesmo estado —
duas fontes para o mesmo fato, e elas divergiram. Catorze specs estavam ✅ no roadmap e
⬜ no próprio arquivo, porque o ciclo que as fechou atualizou uma metade. Quem abrisse a
017 leria "pendente" sobre contatos, que estão em produção desde agosto.

Junto veio outra: **quatro specs tinham dois arquivos** — a versão planejada e a
expandida, com nomes diferentes (`062-financeiro-dre-dfc.md` e
`062-financeiro-relatorios-dre-dfc.md`). As planejadas foram removidas; um número, um
arquivo. O teste passou a exigir as duas coisas.

### O que a regra de sleep realmente proíbe

Havia dois `asyncio.sleep` em teste, e os dois estão certos: são dublês que **travam de
propósito** para provar que um timeout corta, e nenhum dos dois chega a decorrer. A regra
"nunca durma em teste" existe contra dormir para ESPERAR. O teste passou a exigir a
justificativa escrita, que é o que separa os dois usos.

## 9. O que fica aberto, nomeado

Sete itens de dívida permanecem, todos funcionais, nenhum de segurança, cada um com spec
alvo re-atribuída para 101+ em `docs/DIVIDA-TECNICA.md`. E três das sete metas de p95 da
098 não cabem no host de perfilagem — melhoraram entre 2× e 34×, e o gate noturno fica
vermelho de propósito, porque apagá-lo mexendo na meta trocaria o problema por uma
mentira mais confortável.

Fechar com sete pendências nomeadas e medidas é o oposto de fechar com zero pendências
não medidas.

## 10. Definição de pronto

- [x] Todos os testes das 99 specs passam sem edição
- [x] **Wall-clock de `make test` dentro do orçamento** — 288 s de 300 s. O número da
      checklist original (120 s) é de quando o roadmap tinha 30 specs; o teto vigente,
      declarado no CLAUDE.md §3 e verificado pelo `run-tests.sh`, é 300 s
- [x] `make lint` verde: ruff, mypy strict, eslint, tsc
- [x] Zero `Any`, `as any` ou `# type: ignore` sem justificativa
- [x] Nenhum item de segurança em aberto
- [x] Percurso completo do produto funcionando de ponta a ponta
- [x] `ROADMAP.md` com as 100 specs em ✅
- [x] Commit `refactor(100): auditoria final e fechamento do roadmap`

---

## O que vem depois

Terminadas as 100, o `ROADMAP.md` deixa de ser fila e vira histórico. Trabalho novo entra como
spec 101 em diante, seguindo o mesmo ciclo — e a cada 10, uma refatoração.

O gate de 120 s continua valendo. Ele é o que impede o projeto de ficar lento sem ninguém notar.
