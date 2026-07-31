# 091 — Extração de documentos

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 084, 063 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Nada gravado sem revisão · Commit `feat(091): extração de documentos`
