import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/svg+xml"];
const MAX_SIZE_BYTES = 2 * 1024 * 1024;

export interface AvatarUploaderProps {
  avatarUrl: string | null;
  disabled?: boolean;
  onUpload: (file: File) => Promise<void>;
}

/** Mesma regra de negócio do LogoUploader (spec 011, conta) — PNG/JPG/SVG, máx. 2 MB —
 * mas para foto de perfil de usuário (spec 012). Ainda é só a 2ª ocorrência desse
 * padrão; extrair para components/domain/ fica para quando aparecer a 3ª (CLAUDE.md §6). */
export function AvatarUploader({
  avatarUrl,
  disabled = false,
  onUpload,
}: AvatarUploaderProps): JSX.Element {
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
      setError("Foto acima de 2 MB.");
      return;
    }

    setError(null);
    if (avatarUrl) {
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
      setError("Não foi possível enviar a foto.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="space-y-2">
      <span className="text-sm font-medium text-primary">Foto de perfil</span>
      <div className="flex items-center gap-4">
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt="Foto de perfil"
            className="h-16 w-16 rounded-full border border-default object-cover"
          />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-full border border-dashed border-default text-xs text-muted">
            Sem foto
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
          {isUploading ? "Enviando..." : avatarUrl ? "Trocar foto" : "Enviar foto"}
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
        title="Substituir foto?"
        description="A foto atual será substituída pelo novo arquivo."
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
