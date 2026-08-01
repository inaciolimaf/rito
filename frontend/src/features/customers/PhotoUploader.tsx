import * as React from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/errors";

export interface PhotoUploaderProps {
  photoUrl: string | null;
  onUpload: (file: File) => Promise<void>;
}

/** Regra 6: PNG/JPG, máx. 5 MB — validação real é do backend; aqui só mostra o erro
 * devolvido. */
export function PhotoUploader({ photoUrl, onUpload }: PhotoUploaderProps): JSX.Element {
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [isUploading, setIsUploading] = React.useState(false);
  const inputId = React.useId();

  async function handleUpload(): Promise<void> {
    if (!file) return;
    setError(null);
    setIsUploading(true);
    try {
      await onUpload(file);
      setFile(null);
    } catch (uploadError) {
      setError(uploadError instanceof ApiError ? uploadError : null);
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={inputId}>Foto do cliente</Label>
      {photoUrl && (
        <img
          src={photoUrl}
          alt="Foto do cliente"
          className="h-20 w-20 rounded-full border border-default object-cover"
        />
      )}
      <div className="flex items-center gap-2">
        <input
          id={inputId}
          type="file"
          accept="image/png,image/jpeg"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Button type="button" disabled={!file || isUploading} onClick={() => void handleUpload()}>
          Enviar foto
        </Button>
      </div>
      {error && <p className="text-sm text-danger">{error.message}</p>}
    </div>
  );
}
