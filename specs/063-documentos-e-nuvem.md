# 063 — Documentos e nuvem

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 002 · **Status:** ✅ concluída

---

## 1. Objetivo

Cliente e processo precisam de um lugar para guardar arquivo — organizado em pasta, com
busca, sem depender de anexo solto em tarefa. Esta spec entrega a nuvem de documentos
por contato e por processo (docs §4.5/§4.6), com quota de armazenamento por plano do
escritório.

## 2. Escopo

- Pastas (com subpasta) por contato ou por processo.
- Upload múltiplo, download por URL assinada temporária, exclusão.
- Busca por nome de arquivo em todas as pastas de um contato/processo.
- Ordenação por nome, data, tamanho e tipo.
- Quota de armazenamento por plano do escritório (50/70/90/100 GB), bloqueando upload
  acima do limite.
- Painel de armazenamento (usado × quota) na tela de Conta e assinatura.

## 3. Fora de escopo

- Extrair ZIP no navegador (docs §4.5) — cabe numa spec de UI de documentos futura, não
  muda modelo de dados nem contrato de API.
- Cobrança de excedente (R$ 0,50/GB/mês, docs §4.13) — o Rito não tem billing; acima da
  quota o upload é **bloqueado**, não cobrado.
- Nuvem "geral" do escritório fora de contato/processo — os dois escopos do
  levantamento (§4.5/§4.6) são os únicos; um terceiro escopo pode vir com necessidade
  real, não especulativo.
- Certificado digital A1 (docs §9.5) — armazenamento de certificado é outra spec.

## 4. Modelo de dados

```sql
-- accounts ganha o plano do escritório (spec 011) — de onde vem a quota.
ALTER TABLE accounts ADD COLUMN plan TEXT NOT NULL DEFAULT 'ESSENCIAL';
-- 'ESSENCIAL' | 'BANCA_JURIDICA' | 'BANCA_MAX' | 'ELITE' (docs §4.13) → 50/70/90/100 GB.

CREATE TABLE document_folders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  scope_type TEXT NOT NULL,           -- 'CUSTOMER' | 'LAWSUIT'
  scope_id UUID NOT NULL,             -- sem FK — validado no service (mesmo padrão de attachments, spec 035)
  parent_folder_id UUID REFERENCES document_folders(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, scope_type, scope_id, parent_folder_id, name)
);

CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  scope_type TEXT NOT NULL,
  scope_id UUID NOT NULL,
  folder_id UUID REFERENCES document_folders(id) ON DELETE CASCADE,  -- NULL = raiz do escopo
  storage_key TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0 AND size_bytes <= 52428800),
  uploaded_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_documents_scope ON documents (tenant_id, scope_type, scope_id, folder_id);
```
RLS nas duas tabelas novas. Migration `063_documents.py`.

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/documents?scope_type=&scope_id=&folder_id=&sort=&order=` | query | `200 {folders[], documents[]}` | autenticado |
| GET | `/api/v1/documents/search?scope_type=&scope_id=&q=` | query | `200 {documents[]}` | autenticado |
| POST | `/api/v1/documents` | multipart: `scope_type,scope_id,folder_id?,files[]` | `201 [{filename,status,document?,error?}]` | autenticado |
| GET | `/api/v1/documents/{id}/download` | — | `200 {url}` | autenticado |
| DELETE | `/api/v1/documents/{id}` | — | `204` | autenticado |
| POST | `/api/v1/document-folders` | `{scope_type,scope_id,parent_folder_id?,name}` | `201 folder` | autenticado |
| DELETE | `/api/v1/document-folders/{id}` | — | `204` | autenticado |
| GET | `/api/v1/account/storage` | — | `200 {used_bytes,quota_bytes,plan}` | autenticado |
| PUT | `/api/v1/account/plan` | `{plan}` | `200 account` | Gestor |

Erros: `404` (escopo/pasta/documento inexistente), `409` (nome de pasta duplicado),
`422` (tipo bloqueado, arquivo grande, quota excedida).

## 6. Front-end

**Componentes reutilizados:** `ConfirmDialog`, `EmptyState`, `StatCard` (painel de
armazenamento)
**Componentes criados:** `DocumentBrowser` (navegação por pasta, upload, busca,
ordenação — misto pasta/documento não cabe no contrato de listagem do `DataTable`,
que espera uma linha homogênea), `CustomerDocumentsDialog` (usa `DocumentBrowser` num
`Dialog` a partir da listagem de contatos, que não tem tela de detalhe própria)
**Rotas:** aba "Documentos" em `/lawsuits/:id`; ação "Nuvem" na listagem de contatos
(`/customers`, abre `DocumentBrowser` num diálogo); seção de armazenamento em
`/subscription/account`
**Estados:** loading, pasta vazia, erro, quota estourada (mensagem específica no upload)

## 7. Regras de negócio

1. Upload sempre dentro de um escopo (`CUSTOMER` ou `LAWSUIT`) que precisa existir no
   tenant — escopo inexistente ou de outro tenant é `404`.
2. Upload múltiplo processa cada arquivo independentemente — a falha de um (tipo
   bloqueado, tamanho, quota) nunca impede os outros; a resposta traz o status por
   arquivo.
3. Nome de pasta é único dentro do mesmo nível do mesmo escopo (`UNIQUE`) — criar outra
   com o mesmo nome no mesmo lugar é `409`.
4. Excluir pasta remove em cascata as subpastas e os documentos dela, inclusive os
   objetos no storage (mesmo padrão best-effort de attachments, spec 035).
5. Quota é a soma de `size_bytes` de todos os documentos do tenant (todo escopo) —
   comparada à quota do plano antes do IO de storage: upload que ultrapassaria é
   bloqueado com `422`, nada sobe.
6. Quota por plano (docs §4.13): ESSENCIAL 50 GB, BANCA_JURIDICA 70 GB, BANCA_MAX
   90 GB, ELITE 100 GB. Conta sem plano definido usa ESSENCIAL (default da coluna).
7. Download gera URL assinada com validade de 10 minutos — mais generosa que a de
   anexo (5 min, spec 035) porque documento tende a ser maior/revisitado.
8. Busca por nome do arquivo é case-insensitive e cobre todas as pastas do escopo, não
   só a pasta atual.
9. Ordenação aceita `name`, `created_at`, `size_bytes`, `content_type`, cada uma
   `asc`/`desc`.
10. Tamanho e tipo de arquivo seguem a mesma política de anexos (`validate_attachment`,
    spec 035) — reuso direto, sem duplicar a allowlist/blocklist.
11. Excluir documento remove o objeto do storage (best-effort, mesmo padrão de
    attachments).
12. Trocar o plano do escritório é ação de Gestor; não afeta documentos já enviados,
    só o teto de novos uploads.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | upload cria documento na raiz e dentro de pasta | `tests/integration/test_documents.py` | ~0,4 s |
| integração | upload múltiplo: um arquivo inválido não impede os outros | idem | ~0,4 s |
| integração | pasta duplicada no mesmo nível → 409 | idem | ~0,3 s |
| integração | excluir pasta remove subpastas e documentos (cascata) | idem | ~0,4 s |
| integração | quota bloqueia upload acima do limite do plano | idem | ~0,4 s |
| integração | quota soma todos os escopos do tenant | idem | ~0,3 s |
| integração | download gera URL assinada | idem | ~0,3 s |
| integração | busca cobre todas as pastas do escopo | idem | ~0,3 s |
| integração | ordenação por nome/data/tamanho/tipo | idem | ~0,3 s |
| integração | escopo de outro tenant → 404 | idem | ~0,3 s |
| RLS | tenant A não vê documento/pasta de tenant B | idem | ~0,3 s |
| integração | troca de plano por Gestor reflete na quota | `tests/integration/test_account.py` | ~0,3 s |
| frontend | navega por pasta, faz upload, mostra erro de quota | `src/features/documents/*.test.tsx` | ~0,3 s |

**Total estimado:** ~4,4 s
**Fixtures externas:** nenhuma chamada de rede — MinIO local (mesmo padrão de
`tests/integration/test_file_storage.py`, spec 035).

## 9. Descobertas

- `app/integrations/storage/` (interface `FileStorage` + implementação MinIO/S3) já
  existia desde a spec 035 (anexos) — esta spec só reusa, não recria.
- `ON DELETE CASCADE` em `parent_folder_id` e `documents.folder_id` faz o banco cuidar
  da cascata de linhas (regra 4); o service só precisa coletar os `storage_key` da
  subárvore *antes* de apagar, pra limpar os objetos do bucket (que o banco não sabe
  fazer).
- O endpoint `GET /account/storage` mora no router de `documents`, não no de
  `account` — a quota é conceito do domínio de documentos, e `documents` já depende
  de `account` (para ler o plano); o inverso criaria import circular.
- Sem tela de detalhe de contato, a nuvem por contato virou um diálogo a partir da
  listagem (`CustomerDocumentsDialog`) em vez de aba — mesmo padrão de
  `DunningHistoryDrawer` (spec 061).

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Teste de isolamento por tenant
- [x] `make test` verde e wall-clock < 300 s (272 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(063): documentos e nuvem`
