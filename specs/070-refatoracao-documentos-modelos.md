# 070 — 🔧 REFATORAÇÃO — Documentos e Modelos

**Fase:** 6 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 061–069 · **Status:** ⬜ pendente

---

## 1. Objetivo

Setenta por cento do caminho. O produto está funcionalmente completo do ponto de vista
operacional — falta gestão, BI e IA. Esta refatoração prepara o terreno: a camada de IA
(081–090) vai consumir quase tudo que existe hoje via tool calling, e ferramenta que chama
service mal desenhado herda o problema.

> Refatoração não muda comportamento. Testes de 061–069 passam **sem edição**.

## 2. Alvo 1 — preparar os services para virarem ferramentas de IA

A spec 083 vai expor os services como tools tipadas. Para isso funcionar sem gambiarra:

- [ ] Todo service público tem assinatura tipada com Pydantic na entrada e na saída — nada de `dict`
- [ ] Nenhum service depende de objeto de request do FastAPI
- [ ] Nenhum service assume usuário implícito — o ator vem sempre como parâmetro
- [ ] Erros de domínio são exceções tipadas, não `HTTPException` (a tradução para HTTP é do router)
- [ ] Operações de escrita são idempotentes ou expõem chave de idempotência

Sem isso, cada tool vira um wrapper com lógica duplicada.

## 3. Alvo 2 — consolidar arquivos e anexos

Três specs mexeram em arquivo: 035 (anexo em tarefa), 058 (anexo em lançamento), 063 (nuvem).

- [ ] `FileService` único: upload, download, mover, excluir, quota
- [ ] `attachments` como tabela única, com todos os donos possíveis
- [ ] `FileStorage` como a única porta de saída para o S3
- [ ] Limpeza de órfãos cobrindo todos os tipos de dono
- [ ] Quota contabilizada uma vez só, sem dupla contagem

## 4. Alvo 3 — o editor é o maior custo de teste do projeto

- [ ] Medir quanto 065 e 067 custam na suíte
- [ ] Testes de editor que testam o TipTap (biblioteca de terceiro) devem ser removidos — teste o **seu** código
- [ ] Geração de PDF: um teste completo e o resto com renderer falso
- [ ] Jornada e2e do editor: manter só uma
- [ ] Se a fase 6 sozinha passar de 25 s, corte

## 5. Checklist

### Cobertura
- [ ] Toda regra numerada de 061–069 com teste
- [ ] Extenso de dinheiro e data com as tabelas completas
- [ ] Identidade contábil do DRE
- [ ] Path traversal do ZIP
- [ ] RLS com exceção pública (068) nos dois sentidos
- [ ] Isolamento entre tenants nas tabelas novas

### SOLID
- [ ] Services prontos para virar tool (alvo 1)
- [ ] Renderização de PDF atrás de interface (`DocumentRenderer`)
- [ ] Canais de notificação atrás de interface, todos
- [ ] Engine de variáveis pura, sem banco

### Duplicação
- [ ] `FileService` consolidado (alvo 2)
- [ ] Uma só implementação de busca full-text
- [ ] Uma só forma de montar endereço completo (usada por variáveis, PDF e UI)

### Segurança
- [ ] URL assinada com expiração curta em todos os caminhos
- [ ] Allowlist de tipo aplicada em upload direto ao S3 também
- [ ] Modelo público não vaza dado de tenant nenhum
- [ ] E-mail de envio não permite injeção de cabeçalho

### Performance dos testes
- [ ] Wall-clock **< 90 s**
- [ ] E2E com no máximo 10 jornadas até aqui
- [ ] Testes de PDF e editor otimizados (alvo 3)

## 6. Entregáveis

1. Services com contrato tipado, prontos para 083
2. `FileService` e `FileStorage` consolidados
3. Custo dos testes de editor e PDF reduzido, com o antes e depois no `test-timing.json`
4. `docs/DECISOES.md` com o contrato de service que a camada de IA vai consumir
5. Dívidas em `docs/DIVIDA-TECNICA.md`

## 7. Definição de pronto

- [ ] Testes de 061–069 passam sem edição
- [ ] Wall-clock < 90 s
- [ ] Um service qualquer pode virar tool sem código de cola (demonstre com um)
- [ ] Commit `refactor(070): contratos de service e consolidação de arquivos`
