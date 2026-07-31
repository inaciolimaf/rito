# 063 — Documentos e nuvem

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 002 · **Status:** ⬜ pendente

---

## 1. Objetivo

Armazenamento de arquivos de verdade: S3-compatible atrás de interface, com pastas, URL
assinada e controle de quota. Substitui a implementação local provisória de 035.

## 2. Escopo

- Interface `FileStorage` com implementação S3 (MinIO em dev)
- Estrutura de pastas por processo e por contato
- Upload múltiplo com progresso
- URL assinada temporária para download
- Quota por tenant
- Busca por nome
- Extração de ZIP

## 3. Fora de escopo

- Editor de documentos → 065 · OCR → 091 · Versionamento (fora do escopo)

## 4. Modelo de dados

```sql
CREATE TABLE folders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  parent_id UUID REFERENCES folders(id) ON DELETE CASCADE,
  owner_type TEXT NOT NULL,          -- 'lawsuit' | 'customer' | 'tenant'
  owner_id UUID,
  name TEXT NOT NULL,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, owner_type, owner_id, parent_id, name)
);
CREATE INDEX ix_folders_owner ON folders (tenant_id, owner_type, owner_id);

ALTER TABLE attachments
  ADD COLUMN folder_id UUID REFERENCES folders(id) ON DELETE SET NULL,
  ADD COLUMN checksum TEXT;
CREATE INDEX ix_attachments_folder ON attachments (folder_id) WHERE folder_id IS NOT NULL;
CREATE INDEX ix_attachments_name_trgm ON attachments USING gin (filename gin_trgm_ops);

CREATE TABLE storage_quotas (
  tenant_id UUID PRIMARY KEY REFERENCES tenants(id),
  limit_bytes BIGINT NOT NULL DEFAULT 53687091200,   -- 50 GB
  used_bytes BIGINT NOT NULL DEFAULT 0,
  file_count INTEGER NOT NULL DEFAULT 0
);
```
RLS ligado. Migration `063_storage.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/files/upload-url` → URL pré-assinada de upload direto ao S3 |
| POST | `/api/v1/files/confirm` → registra após o upload |
| GET | `/api/v1/files/{id}/download-url` → URL assinada, 5 min |
| GET/POST | `/api/v1/folders?owner_type=&owner_id=` |
| PUT/DELETE | `/api/v1/folders/{id}` |
| POST | `/api/v1/files/{id}/move` → `{folder_id}` |
| POST | `/api/v1/files/{id}/extract` — ZIP |
| GET | `/api/v1/files/search?q=&owner_type=&owner_id=` |
| GET | `/api/v1/storage/quota` |

## 6. Front-end

**Reutiliza:** `FileDropzone`, `AttachmentList`, `ConfirmDialog`, `EmptyState`
**Cria:** `FileBrowser` (árvore + grade), `FolderBreadcrumb`, `UploadProgressList`,
`StorageQuotaBar`, `FilePreview` (pdf e imagem inline)
**Rotas:** aba nuvem em `/lawsuits/:id` e `/customers/:id`

## 7. Regras de negócio

1. Upload é **direto para o S3** por URL pré-assinada — o arquivo não passa pelo backend.
2. `confirm` valida tamanho e checksum antes de registrar; upload não confirmado é limpo por job após 24 h.
3. URL de download expira em **5 minutos**.
4. Quota por tenant: padrão 50 GB. Excedeu → 413 com a mensagem de quanto falta.
5. `used_bytes` é atualizado por trigger em insert e delete de `attachments`.
6. Pasta é hierárquica, com profundidade máxima de 5 níveis.
7. Nome único entre irmãs, na mesma pasta e mesmo dono.
8. Excluir pasta move o conteúdo para a pasta pai; excluir com `force=true` apaga em cascata, com confirmação.
9. Allowlist de tipos; executáveis e scripts bloqueados por extensão **e** por content-type.
10. Extração de ZIP: máximo de 100 arquivos, 200 MB descompactados, e **rejeita path traversal** (`../`).
11. Busca por nome é parcial, sem acento, mínimo 3 caracteres.
12. Arquivo órfão (dono excluído) é removido por job semanal.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | fluxo upload-url → S3 → confirm | ~0,5 s |
| integração | confirm com checksum errado → 422 | ~0,3 s |
| integração | URL de download expira | ~0,3 s |
| integração | quota excedida → 413 | ~0,3 s |
| integração | trigger atualiza `used_bytes` em insert e delete | ~0,4 s |
| integração | 6º nível de pasta → 422 | ~0,2 s |
| integração | nome duplicado entre irmãs → 409 | ~0,2 s |
| integração | excluir pasta move conteúdo para a pai | ~0,4 s |
| integração | tipo bloqueado por extensão e por content-type | ~0,3 s |
| integração | **ZIP com `../` é rejeitado** | ~0,3 s |
| integração | ZIP acima do limite → 422 | ~0,3 s |
| integração | busca por nome sem acento | ~0,3 s |
| integração | RLS: arquivo não vaza entre tenants | ~0,4 s |
| frontend | navegação por pastas com breadcrumb | ~0,5 s |
| frontend | barra de quota | ~0,3 s |

**Total:** ~5,0 s
MinIO em container nos testes de integração; `FileStorage` fake nos unitários.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Path traversal bloqueado · Upload não passa pelo backend · Commit `feat(063): documentos e nuvem`
