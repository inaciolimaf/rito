/** Validação de anexos (spec 035, regra 5) — espelha app/domain/attachments/rules.py
 * para o FileDropzone rejeitar antes do upload. O servidor repete a validação (a
 * checagem do cliente é UX, a do servidor é segurança).
 */

export const MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024; // 50 MB

export const ALLOWED_CONTENT_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "text/plain",
  "text/csv",
  "application/json",
  "application/zip",
  "application/x-zip-compressed",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.oasis.opendocument.text",
  "application/vnd.oasis.opendocument.spreadsheet",
]);

const EXECUTABLE_EXTENSIONS = new Set([
  ".exe",
  ".bat",
  ".cmd",
  ".com",
  ".msi",
  ".scr",
  ".ps1",
  ".sh",
  ".bash",
  ".vbs",
  ".js",
  ".jar",
  ".apk",
  ".dll",
]);

const EXECUTABLE_CONTENT_TYPES = new Set([
  "application/x-msdownload",
  "application/x-msdos-program",
  "application/x-executable",
  "application/x-sh",
  "application/java-archive",
]);

export type AttachmentValidationError = "too_large" | "type_blocked";

/** Devolve o motivo da recusa ou null se o arquivo passa na regra 5. */
export function validateAttachment(file: {
  name: string;
  type: string;
  size: number;
}): AttachmentValidationError | null {
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return "too_large";
  }
  const dotIndex = file.name.lastIndexOf(".");
  const extension = dotIndex >= 0 ? file.name.slice(dotIndex).toLowerCase() : "";
  if (
    EXECUTABLE_EXTENSIONS.has(extension) ||
    EXECUTABLE_CONTENT_TYPES.has(file.type) ||
    !ALLOWED_CONTENT_TYPES.has(file.type)
  ) {
    return "type_blocked";
  }
  return null;
}

export function attachmentErrorMessage(reason: AttachmentValidationError): string {
  return reason === "too_large" ? "Anexo acima de 50 MB." : "Tipo de arquivo não permitido.";
}
