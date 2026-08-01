import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/svg+xml"];
const MAX_SIZE_BYTES = 2 * 1024 * 1024;

export interface LogoUploaderProps {
  logoUrl: string | null;
  disabled?: boolean;
  onUpload: (file: File) => Promise<void>;
}

export function LogoUploader({
  logoUrl,
  disabled = false,
  onUpload,
}: LogoUploaderProps): JSX.Element {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isUploading, setIsUploading] = React.useState(false);

  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Formato inválido — use PNG, JPG ou SVG.");
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setError("Logotipo acima de 2 MB.");
      return;
    }

    setError(null);
    if (logoUrl) {
      setPendingFile(file);
      return;
    }
    void doUpload(file);
  }

  async function doUpload(file: File): Promise<void> {
    setIsUploading(true);
    setError(null);
    try {
      await onUpload(file);
    } catch {
      setError("Não foi possível enviar o logotipo.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="space-y-2">
      <span className="text-sm font-medium text-primary">Logotipo</span>
      <div className="flex items-center gap-4">
        {logoUrl ? (
          <img
            src={logoUrl}
            alt="Logotipo do escritório"
            className="h-16 w-16 rounded border border-default object-contain"
          />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded border border-dashed border-default text-xs text-muted">
            Sem logo
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          className="hidden"
          onChange={handleFileSelected}
          disabled={disabled || isUploading}
        />
        <Button
          type="button"
          variant="outline"
          disabled={disabled || isUploading}
          onClick={() => inputRef.current?.click()}
        >
          {isUploading ? "Enviando..." : logoUrl ? "Trocar logotipo" : "Enviar logotipo"}
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <ConfirmDialog
        open={pendingFile !== null}
        onOpenChange={(open) => {
          if (!open) setPendingFile(null);
        }}
        title="Substituir logotipo?"
        description="O logotipo atual será substituído pelo novo arquivo."
        confirmLabel="Substituir"
        onConfirm={() => {
          const file = pendingFile;
          setPendingFile(null);
          if (file) void doUpload(file);
        }}
      />
    </div>
  );
}
