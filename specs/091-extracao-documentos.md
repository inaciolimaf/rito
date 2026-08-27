# 091 — Extração de documentos

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 084, 063 · **Status:** ✅ concluída

---

## 1. Objetivo

Eliminar digitação: sobe o RG, o contrato ou a procuração, e o sistema propõe o cadastro
preenchido. Sempre com revisão humana antes de gravar.

## 2. Escopo

- OCR de PDF e imagem
- Extração estruturada por LLM
- Tipos: documento pessoal, contrato social, procuração, petição inicial
- Preview com confiança por campo
- Cadastro após confirmação
- Vínculo do arquivo ao registro criado

## 3. Fora de escopo

- Assinatura digital · Validação em base oficial (fora do escopo)

## 4. Modelo de dados

```sql
CREATE TABLE document_extractions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  document_kind TEXT,                  -- 'rg' | 'cnh' | 'contrato_social' | 'procuracao' | 'peticao'
  ocr_text TEXT,
  extracted JSONB NOT NULL,            -- {campo: {value, confidence}}
  target_type TEXT,                    -- 'customer' | 'lawsuit'
  action_id UUID REFERENCES ai_actions(id),
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | reviewed | applied | discarded
  model TEXT, tokens_used INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_extractions_pending ON document_extractions (tenant_id, created_at DESC)
  WHERE status = 'pending';
```
RLS ligado. Migration `091_document_extractions.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/documents/extract` → `{attachment_id, expected_kind?}` |
| GET | `/api/v1/documents/extractions/{id}` |
| POST | `/api/v1/documents/extractions/{id}/apply` → `{target_type, corrections}` |
| POST | `/api/v1/documents/extractions/{id}/discard` |

## 6. Front-end

**Reutiliza:** `FileDropzone`, `AIActionPreview`, `FormModal`, `ConfirmDialog`
**Cria:** `ExtractDocumentDialog`, `ExtractionReview` (documento à esquerda, campos à direita,
com destaque de onde cada valor veio), `FieldConfidenceBadge`, `OcrTextViewer`
**Rota:** dentro de `/customers` e `/lawsuits`

## 7. Regras de negócio

1. OCR roda antes do LLM. PDF com texto embutido pula o OCR — não gaste processamento à toa.
2. O tipo do documento é detectado automaticamente; `expected_kind` restringe e melhora a precisão.
3. Cada campo extraído vem com confiança de 0 a 1. Abaixo de **0,7**, o campo é destacado e **não** é pré-preenchido.
4. CPF, CNPJ e CEP extraídos passam pelos validadores de 018. Inválido é marcado, não descartado — pode ser erro de OCR que o humano corrige.
5. Aplicar passa pelo fluxo de `ai_actions` (084): preview, confirmação, auditoria.
6. Correção humana é gravada, alimentando a métrica de qualidade.
7. O arquivo é vinculado ao registro criado, na pasta apropriada.
8. Duplicata detectada (CPF já cadastrado) avisa e oferece atualizar em vez de criar.
9. Limites: 20 MB, 20 páginas. Acima disso, pede recorte.
10. Documento ilegível devolve erro claro, com o texto do OCR disponível para conferência.
11. Extração custa tokens — a UI mostra a estimativa antes de processar lote.
12. Sem chave de IA, a funcionalidade aparece desabilitada com explicação.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | PDF com texto pula o OCR | ~0,4 s |
| integração | imagem passa pelo OCR | ~0,5 s |
| integração | extração de RG preenche os campos (fixture) | ~0,5 s |
| integração | extração de contrato social preenche PJ | ~0,4 s |
| integração | confiança < 0,7 não pré-preenche | ~0,3 s |
| integração | CPF inválido é marcado, não descartado | ~0,3 s |
| integração | **aplicar passa por `ai_actions`** | ~0,5 s |
| integração | correção humana é gravada | ~0,3 s |
| integração | arquivo vinculado ao registro criado | ~0,4 s |
| integração | duplicata oferece atualizar | ~0,4 s |
| integração | acima de 20 páginas → 422 | ~0,2 s |
| integração | ilegível devolve erro com o OCR | ~0,3 s |
| frontend | revisão mostra documento e campos lado a lado | ~0,5 s |

**Total:** ~5,0 s
OCR e LLM sempre mockados; fixtures com PDFs sintéticos anonimizados.

## 9. Descobertas

- **`attachment_id` não podia ser obrigatório.** O §4 desta spec pedia
  `attachment_id UUID NOT NULL`, e o caso principal da feature não cabe nisso: cadastrar
  um cliente a partir do RG acontece **antes** de existir a ficha à qual anexar o arquivo.
  A rota passou a aceitar as duas entradas — o anexo que já está no sistema, ou o upload
  direto — e o que a tabela guarda sempre é o `storage_key`. É ele que vai para a nuvem do
  registro quando o cadastro é confirmado (regra 7).
- **`FileStorage` não sabia ler.** A interface tinha `upload`, `delete`, `public_url` e
  `signed_url`: até aqui, todo consumidor só precisava devolver uma URL para o navegador
  buscar sozinho. Extrair campos exige o servidor LER os bytes, e `download` entrou no
  Protocol — três linhas na interface, e a primeira vez em seis specs de arquivo que o
  backend precisou do conteúdo.
- **A regra 1 vale nos dois sentidos.** "PDF com texto pula o OCR" é o caso óbvio; o que
  aparece na prática é o inverso — PDF digitalizado cujo "texto embutido" é numeração de
  página e marca d'água. Abaixo de 40 caracteres o texto é tratado como ruído de layout e
  o OCR roda. Sem esse piso, um PDF escaneado passaria direto para o modelo com três
  palavras de contexto e voltaria "não identificado".
- **`prefill` é decisão do servidor, não da tela.** A regra 3 podia ter virado
  `confidence < 0.7` no componente React. Duas telas lendo a mesma confiança e decidindo
  diferente é a pior forma de inconsistência — e o app tem tela de contato e tela de
  processo consumindo a mesma extração.
- **Confiança e validade são coisas diferentes, e a tela não pode fundi-las.** Confiança é
  sobre a LEITURA ("o OCR viu isso mesmo?"); validade é sobre o VALOR ("esse CPF existe?").
  Um CPF lido com nitidez perfeita e dígito verificador errado é 95% de confiança e
  inválido — exatamente o caso em que a pessoa precisa olhar. O badge mostra os dois.
- **A confirmação humana é a tela de revisão, não um segundo diálogo.** A regra 5 manda a
  gravação passar por `ai_actions`, e o CLAUDE.md §7 exige confirmação humana antes de
  qualquer escrita de IA. As duas coisas são atendidas por `apply`: a pessoa revisou campo
  a campo, com confiança e validação à vista, e corrigiu o que quis — pedir "confirma?"
  sobre o mesmo conteúdo não acrescentaria informação, só treinaria a clicar sem ler. O que
  fica registrado é o par completo: proposta com preview e execução com auditoria.
- **O limite de páginas é checado antes de chamar o modelo**, e o teste prova isso olhando
  `provider.prompts == []`. Um limite verificado depois é um limite que já custou dinheiro.
- **A extração usa o cache da 090** (`use_cache=True`), e o motivo é bem específico: o
  mesmo arquivo reenviado depois de um erro de rede é a repetição que acontece de verdade
  aqui, e ela não pode ser cobrada duas vezes. Diferente da reanálise de intimação, ninguém
  sobe o mesmo RG duas vezes esperando leitura diferente.
- **OCR entrou como integração, e o servidor pode não ter nenhuma.** `OcrProvider` é
  Protocol; a implementação chama o binário do Tesseract por subprocesso em vez de amarrar
  um binding Python — o binding continua exigindo o mesmo binário do sistema e ainda
  quebra no build quando a versão muda. Sem Tesseract instalado, o app sobe com
  `UnavailableOcr`, que falha com uma frase em português em vez de um `FileNotFoundError`
  de subprocesso. Este servidor de desenvolvimento é justamente um sem Tesseract, e o teste
  cobre esse caminho.
- **CPF inválido marcado, nunca descartado (regra 4), é o detalhe que decide se a feature
  serve.** Quase todo CPF que não fecha o dígito é erro de OCR num documento legítimo —
  jogar o campo fora obrigaria a digitar tudo de novo, que é exatamente o que a extração
  existe para evitar.

## 10. Definição de pronto

- [x] Checklist padrão
- [x] Nada gravado sem revisão — o cadastro só existe depois de `apply`, e ele passa por
      `ai_actions` com preview, execução pelo service do domínio e auditoria
- [x] Commit `feat(091): extração de documentos`
