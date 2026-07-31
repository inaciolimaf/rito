# 067 — Modelos: geração e envio

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 066 · **Status:** ⬜ pendente

---

## 1. Objetivo

Fechar o ciclo do módulo: do modelo ao PDF assinado no processo, ou no e-mail do cliente.

## 2. Escopo

- Renderização para PDF com cabeçalho, rodapé, marca d'água e numeração
- Download
- Salvar na nuvem do processo
- Envio por e-mail com anexo
- Histórico de documentos gerados
- Geração em lote

## 3. Fora de escopo

- Assinatura digital (fora do escopo) · Protocolo em tribunal (fora do escopo)

## 4. Modelo de dados

```sql
CREATE TABLE generated_documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  template_id UUID REFERENCES document_templates(id) ON DELETE SET NULL,
  lawsuit_id UUID REFERENCES lawsuits(id) ON DELETE CASCADE,
  customer_id UUID REFERENCES customers(id),
  name TEXT NOT NULL,
  content JSONB NOT NULL,             -- snapshot renderizado
  attachment_id UUID REFERENCES attachments(id),
  missing_variables TEXT[] NOT NULL DEFAULT '{}',
  generated_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_gendoc_lawsuit ON generated_documents (lawsuit_id, created_at DESC);
```
RLS ligado. Migration `067_generated_documents.py`.

O `content` é snapshot: alterar o modelo depois não muda o documento já gerado.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/templates/{id}/generate` → `{lawsuit_id, customer_id?, save_to_cloud?, name?}` |
| GET | `/api/v1/generated-documents/{id}/pdf` |
| POST | `/api/v1/generated-documents/{id}/email` → `{to[], subject, body}` |
| GET | `/api/v1/lawsuits/{id}/generated-documents` |
| POST | `/api/v1/templates/{id}/generate-batch` → `{lawsuit_ids[]}` |

## 6. Front-end

**Reutiliza:** `FormModal`, `EntityPicker`, `ConfirmDialog`, `DataTable`
**Cria:** `GenerateDocumentDialog`, `PdfPreview`, `SendByEmailDialog`,
`GeneratedDocumentsList`, `BatchGenerateDialog`
**Rota:** dentro do editor e em `/lawsuits/:id`

## 7. Regras de negócio

1. PDF é gerado no backend a partir do JSON renderizado. Não confie no `window.print` do navegador — resultado varia por browser.
2. Cabeçalho e rodapé repetem em **todas** as páginas; a numeração resolve `{{page}}` e `{{pages}}`.
3. Marca d'água aparece em todas as páginas, atrás do conteúdo.
4. Quebra de página do editor é respeitada.
5. Documento com variável ausente é gerado, mas com aviso e com as ausências registradas.
6. `save_to_cloud` grava na pasta "Documentos gerados" do processo, criada se não existir.
7. Nome padrão: `<modelo> - <parte> - <AAAA-MM-DD>`, editável.
8. Envio por e-mail anexa o PDF e registra a tentativa; falha não perde o documento.
9. Geração em lote: máximo de 100 processos, processada em background com notificação ao final e ZIP para download.
10. Margens padrão ABNT (3 cm esquerda e superior, 2 cm direita e inferior), configuráveis no modelo.
11. Fonte embutida no PDF, para não depender do que existe na máquina.
12. Documento gerado é imutável — regerar cria um novo registro.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | PDF gerado com cabeçalho e rodapé em todas as páginas | ~0,6 s |
| integração | numeração `{{page}}`/`{{pages}}` correta em 3 páginas | ~0,4 s |
| integração | marca d'água em todas as páginas | ~0,3 s |
| integração | quebra de página respeitada | ~0,3 s |
| integração | variável ausente gera com aviso | ~0,3 s |
| integração | salvar na nuvem cria a pasta | ~0,4 s |
| integração | nome padrão bem formado | ~0,2 s |
| integração | envio por e-mail anexa e registra | ~0,4 s |
| integração | falha no e-mail preserva o documento | ~0,3 s |
| integração | lote acima de 100 → 422 | ~0,2 s |
| integração | lote gera ZIP e notifica | ~0,5 s |
| integração | snapshot imune a alteração do modelo | ~0,4 s |
| frontend | preview do PDF | ~0,4 s |

**Total:** ~4,7 s

> A verificação do PDF usa extração de texto (`pypdf`) para conferir conteúdo e contagem de
> páginas — não compare bytes, que variam por metadados.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · PDF verificado por extração de texto · Commit `feat(067): modelos — geração e envio`
