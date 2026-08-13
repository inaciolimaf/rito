# 067 — Modelos: geração e envio

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 066 · **Status:** ✅ concluída

---

## 1. Objetivo

O modelo resolvido (spec 066) ainda é só HTML em memória. Esta spec fecha o ciclo:
gera PDF de verdade, com cabeçalho/rodapé/marca d'água, pra baixar, mandar por e-mail
ou guardar na nuvem do processo (spec 063).

## 2. Escopo

- Render HTML → PDF (`xhtml2pdf`, pura Python, sem dependência de sistema) com
  cabeçalho no topo, rodapé no fim, marca d'água como rótulo de destaque.
- Download do PDF gerado.
- Envio por e-mail com o PDF como anexo (reaproveita `SMTP_*` já configurado, spec 061).
- Salvar o PDF gerado na nuvem do processo (spec 063 — exige `lawsuit_id`, é "a nuvem
  **do processo**", não do contato).

## 3. Fora de escopo

- Marca d'água diagonal semitransparente sobreposta ao texto — `xhtml2pdf` não
  suporta `position: fixed` + rotação de forma confiável; a marca sai como um rótulo
  de destaque no topo do documento, não sobreposta. Cumpre o requisito (documento
  sinalizado), não a estética exata do Word/Google Docs.
- Cabeçalho/rodapé **repetidos em toda página** (running header/footer típico de
  editor de texto) — saem uma vez (topo/fim do documento), não por página; suporte
  completo a paginação do `xhtml2pdf` é frágil o bastante para não valer o risco
  dentro do orçamento desta spec.
- "Fazer cópia" de documento já gerado, editor integrado ao processo — fora do
  levantamento desta spec especificamente.

## 4. Modelo de dados

Nenhuma tabela nova. O PDF gerado por "salvar na nuvem" vira uma linha em `documents`
(spec 063) — `scope_type='LAWSUIT'`, sem pasta (`folder_id=NULL`).

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| POST | `/api/v1/templates/{id}/generate-pdf` | `{customer_id?, lawsuit_id?}` | `200` PDF binário | autenticado |
| POST | `/api/v1/templates/{id}/save-to-cloud` | `{customer_id?, lawsuit_id}` (`lawsuit_id` obrigatório) | `201 document` (schema da spec 063) | autenticado |
| POST | `/api/v1/templates/{id}/send-email` | `{customer_id?, lawsuit_id?, to, subject?}` | `204` | autenticado |

Erros: `404` (modelo/cliente/processo), `422` (e-mail sem SMTP configurado — regra 4).

## 6. Front-end

**Componentes reutilizados:** `EntityPicker` (escolher cliente/processo antes de
gerar).
**Componentes criados:** `GenerateDocumentDialog` — escolhe cliente/processo, mostra
preview das variáveis ausentes (spec 066) antes de confirmar, e as 3 ações (baixar,
enviar, salvar na nuvem).
**Rotas:** nenhuma nova — o diálogo abre a partir de `/library/:id` (botão "Gerar
documento").
**Estados:** gerando, erro de geração, variável ausente (aviso, não bloqueia — regra 5).

## 7. Regras de negócio

1. As 3 ações (baixar/enviar/salvar) partem do mesmo PDF: resolve variáveis (spec
   066) → monta HTML com cabeçalho/corpo/rodapé/marca d'água → renderiza.
2. "Salvar na nuvem" sempre exige `lawsuit_id` — é a nuvem do processo (spec 063),
   diferente de gerar/baixar/enviar, que aceitam cliente OU processo OU nenhum dos
   dois (documento sem variável de escopo nenhuma ainda gera, só com mais `<mark>`).
3. O arquivo salvo/enviado usa o nome do modelo (`{nome}.pdf`) — sem timestamp nem
   sufixo, mesmo padrão de nome previsível de qualquer exportação do sistema.
4. E-mail sem `SMTP_HOST` configurado retorna `422` explícito — diferente da régua de
   cobrança (spec 061, regra 9, que nunca quebra o fluxo em lote), aqui é uma ação
   síncrona de um usuário só, o erro tem que aparecer na hora.
5. Variável ausente (spec 066, regra 4) não bloqueia nenhuma das 3 ações — o PDF sai
   com o `<mark>` visível; quem gera decide se serve assim ou edita o modelo antes.
6. "Salvar na nuvem" respeita a mesma quota de armazenamento da spec 063 (regra 5
   daquela spec) — PDF que estouraria a quota do plano é bloqueado antes do upload,
   mesmo comportamento de qualquer outro documento.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | `render_pdf` produz PDF válido (assinatura `%PDF`) com cabeçalho/corpo/rodapé | `tests/unit/test_template_pdf.py` | ~0,1 s |
| integração | `generate-pdf` devolve `application/pdf` não vazio | `tests/integration/test_template_generate.py` | ~0,3 s |
| integração | `save-to-cloud` sem `lawsuit_id` → 422; com `lawsuit_id` cria documento na nuvem do processo | idem | ~0,4 s |
| integração | `save-to-cloud` respeita quota (reaproveita o padrão de monkeypatch da spec 063) | idem | ~0,3 s |
| serviço direto | envio de e-mail com mailer fake (mesmo padrão de `test_dunning.py`): anexo é o PDF, nome é `{modelo}.pdf` | idem | ~0,2 s |
| serviço direto | mailer não configurado → erro explícito (regra 4) | idem | ~0,1 s |

**Total estimado:** ~1,4 s
**Fixtures externas:** nenhuma chamada real de SMTP — mailer sempre injetado/fake
nos testes (mesmo padrão de `FakeEmailChannel`, spec 061).

## 9. Descobertas

- `xhtml2pdf` (pura Python, sem libs de sistema como cairo/pango) renderiza em ~8 ms
  por documento — o custo de teste é desprezível; a folga apertada do orçamento (ver
  abaixo) não vem da geração de PDF em si.
- `DocumentMailer` (anexo) ficou como interface própria, separada de `MessagingChannel`
  (spec 061, só texto) — ISP: forçar as duas na mesma interface obrigaria SMS/WhatsApp
  a implementar um `send` com parâmetros de anexo que nunca usam.
- "Salvar na nuvem" reaproveitou `DocumentService.upload_many` (spec 063) sem nenhuma
  mudança lá — a validação de tipo/tamanho e a quota já cobriam PDF de saída.
- **Orçamento no limite:** wall-clock da suíte cheia fechou em **300 s exatos** — o
  teto inteiro, zero folga (o script só falha em `> 300`, então passou, mas por um
  triz). A fase 6 esgotou o orçamento que tinha: **a spec 068 (Biblioteca pública de
  modelos) não deve começar sem antes rodar a refatoração 070** (ou uma otimização
  equivalente) para abrir espaço de novo — continuar empilhando teste novo em cima
  disto vai estourar o gate na próxima spec, não eventualmente.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock < 300 s (300 s exatos — sem folga, ver Descobertas)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(067): modelos — geração e envio`
