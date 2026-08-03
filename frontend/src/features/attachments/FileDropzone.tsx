import * as React from "react";

import { attachmentErrorMessage, validateAttachment } from "@/features/attachments/rules";

export interface FileDropzoneProps {
  /** Chamado só com os arquivos VÁLIDOS (regra 5); os recusados viram mensagem. */
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

/** Seleção de anexos (spec 035 §6): valida tipo e tamanho no cliente (regra 5) antes
 * de subir — o servidor repete a checagem. Input de arquivo nativo + botão (o drop
 * visual fica para a 063, com o storage definitivo). */
export function FileDropzone({ onFiles, disabled = false }: FileDropzoneProps): JSX.Element {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [error, setError] = React.useState<string | null>(null);

  function handleSelection(fileList: FileList | null): void {
    if (!fileList || fileList.length === 0) {
      return;
    }
    const accepted: File[] = [];
    const rejected: string[] = [];
    for (const file of Array.from(fileList)) {
      const reason = validateAttachment(file);
      if (reason) {
        rejected.push(`${file.name}: ${attachmentErrorMessage(reason)}`);
      } else {
        accepted.push(file);
      }
    }
    setError(rejected.length > 0 ? rejected.join(" ") : null);
    if (accepted.length > 0) {
      onFiles(accepted);
    }
  }

  return (
    <div className="space-y-1">
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        aria-label="Selecionar anexos"
        onChange={(event) => {
          handleSelection(event.target.files);
          event.target.value = ""; // re-selecionar o mesmo arquivo dispara change de novo
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="rounded border border-dashed border-default px-3 py-2 text-sm text-muted hover:bg-surface-muted disabled:opacity-50"
      >
        Anexar arquivo (máx. 50 MB)
      </button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
