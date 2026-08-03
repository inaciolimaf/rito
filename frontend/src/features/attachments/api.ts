import { apiRequest } from "@/lib/api";

export interface AttachmentData {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  attached_to_type: string;
  attached_to_id: string;
  uploaded_by: string;
  created_at: string;
}

export async function uploadAttachment(
  targetType: "post" | "comment",
  targetId: string,
  file: File,
): Promise<AttachmentData> {
  const form = new FormData();
  form.append("file", file);
  form.append("attached_to_type", targetType);
  form.append("attached_to_id", targetId);
  return apiRequest<AttachmentData>("/api/v1/attachments", { method: "POST", body: form });
}

/** Regra 6: URL assinada com validade de 5 min — pedida na hora do clique, nunca
 * guardada (ela expira). */
export async function getAttachmentDownloadUrl(attachmentId: string): Promise<string> {
  const response = await apiRequest<{ url: string }>(
    `/api/v1/attachments/${attachmentId}/download`,
  );
  return response.url;
}

export async function deleteAttachment(attachmentId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/attachments/${attachmentId}`, { method: "DELETE" });
}
