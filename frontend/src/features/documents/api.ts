import type { AccountPlan, DocumentScopeType } from "@/lib/domainEnums.generated";

// Reexportado para quem já importava daqui: o nome é o mesmo, a FONTE é o arquivo
// gerado a partir dos `StrEnum` do backend (dívida 15).
export type { AccountPlan, DocumentScopeType };

import { apiRequest } from "@/lib/api";

export type DocumentSortField = "name" | "created_at" | "size_bytes" | "content_type";
export type DocumentSortOrder = "asc" | "desc";

export interface DocumentFolderData {
  id: string;
  scope_type: DocumentScopeType;
  scope_id: string;
  parent_folder_id: string | null;
  name: string;
  created_by: string;
  created_at: string;
}

export interface DocumentData {
  id: string;
  scope_type: DocumentScopeType;
  scope_id: string;
  folder_id: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by: string;
  created_at: string;
}

export interface DocumentListResult {
  folders: DocumentFolderData[];
  documents: DocumentData[];
}

export interface ListDocumentsParams {
  scope_type: DocumentScopeType;
  scope_id: string;
  folder_id?: string | null;
  sort?: DocumentSortField;
  order?: DocumentSortOrder;
}

export async function listDocuments(params: ListDocumentsParams): Promise<DocumentListResult> {
  const query = new URLSearchParams({ scope_type: params.scope_type, scope_id: params.scope_id });
  if (params.folder_id) query.set("folder_id", params.folder_id);
  if (params.sort) query.set("sort", params.sort);
  if (params.order) query.set("order", params.order);
  return apiRequest<DocumentListResult>(`/api/v1/documents?${query.toString()}`);
}

export async function searchDocuments(
  scopeType: DocumentScopeType,
  scopeId: string,
  q: string,
): Promise<DocumentData[]> {
  const query = new URLSearchParams({ scope_type: scopeType, scope_id: scopeId, q });
  const body = await apiRequest<{ documents: DocumentData[] }>(
    `/api/v1/documents/search?${query.toString()}`,
  );
  return body.documents;
}

export interface UploadResult {
  filename: string;
  status: "uploaded" | "error";
  document: DocumentData | null;
  error: string | null;
}

/** Regra 2: upload múltiplo — a resposta traz o status por arquivo, nunca aborta os
 * outros por causa de um só. */
export async function uploadDocuments(
  scopeType: DocumentScopeType,
  scopeId: string,
  folderId: string | null,
  files: File[],
): Promise<UploadResult[]> {
  const form = new FormData();
  form.append("scope_type", scopeType);
  form.append("scope_id", scopeId);
  if (folderId) form.append("folder_id", folderId);
  for (const file of files) form.append("files", file);
  return apiRequest<UploadResult[]>("/api/v1/documents", { method: "POST", body: form });
}

/** Regra 7: URL assinada de 10 min — pedida na hora do clique, nunca guardada. */
export async function getDocumentDownloadUrl(documentId: string): Promise<string> {
  const response = await apiRequest<{ url: string }>(`/api/v1/documents/${documentId}/download`);
  return response.url;
}

export async function deleteDocument(documentId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

export async function createDocumentFolder(values: {
  scope_type: DocumentScopeType;
  scope_id: string;
  parent_folder_id?: string | null;
  name: string;
}): Promise<DocumentFolderData> {
  return apiRequest<DocumentFolderData>("/api/v1/document-folders", {
    method: "POST",
    body: values,
  });
}

export async function deleteDocumentFolder(folderId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/document-folders/${folderId}`, { method: "DELETE" });
}

export interface AccountStorageData {
  used_bytes: number;
  quota_bytes: number;
  plan: AccountPlan;
}

export async function getAccountStorage(): Promise<AccountStorageData> {
  return apiRequest<AccountStorageData>("/api/v1/account/storage");
}
