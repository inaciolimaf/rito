import * as React from "react";

import {
  deleteAttachment,
  getAttachmentDownloadUrl,
  type AttachmentData,
} from "@/features/attachments/api";

export interface AttachmentListProps {
  attachments: AttachmentData[];
  /** Chamado depois de remover — o pai invalida a query. Sem ele, não há botão. */
  onRemoved?: (attachmentId: string) => void;
}

/** Lista de anexos (spec 035 §6): nome clicável baixa por URL assinada pedida na hora
 * (regra 6 — ela expira em 5 min, não vale guardar). */
export function AttachmentList({
  attachments,
  onRemoved,
}: AttachmentListProps): JSX.Element | null {
  const [busyId, setBusyId] = React.useState<string | null>(null);

  if (attachments.length === 0) {
    return null;
  }

  async function handleDownload(attachment: AttachmentData): Promise<void> {
    setBusyId(attachment.id);
    try {
      const url = await getAttachmentDownloadUrl(attachment.id);
      window.open(url, "_blank", "noopener");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(attachment: AttachmentData): Promise<void> {
    setBusyId(attachment.id);
    try {
      await deleteAttachment(attachment.id);
      onRemoved?.(attachment.id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <ul className="space-y-1">
      {attachments.map((attachment) => (
        <li key={attachment.id} className="flex items-center gap-2 text-sm">
          <button
            type="button"
            disabled={busyId === attachment.id}
            onClick={() => void handleDownload(attachment)}
            className="truncate text-accent underline"
          >
            {attachment.filename}
          </button>
          <span className="text-xs text-muted">{(attachment.size_bytes / 1024).toFixed(0)} KB</span>
          {onRemoved && (
            <button
              type="button"
              aria-label={`Remover ${attachment.filename}`}
              disabled={busyId === attachment.id}
              onClick={() => void handleRemove(attachment)}
              className="text-xs text-danger hover:underline"
            >
              Remover
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
