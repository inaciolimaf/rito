import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";

/** PNG/JPG/SVG — a allowlist que o backend aceita para logotipo (011) e foto (012). */
const DEFAULT_IMAGE_TYPES = ["image/png", "image/jpeg", "image/svg+xml"];
const DEFAULT_MAX_IMAGE_BYTES = 2 * 1024 * 1024;

export interface ImageUploaderProps {
  /** Rótulo acima do bloco ("Logotipo", "Foto de perfil"). */
  label: string;
  imageUrl: string | null;
  /** `alt` da imagem já enviada. */
  alt: string;
  /** Texto do quadrado vazio ("Sem logo", "Sem foto"). */
  emptyLabel: string;
  /** Rótulo do botão quando ainda não há imagem. */
  uploadLabel: string;
  /** Rótulo do botão quando já existe imagem. */
  replaceLabel: string;
  /** Diálogo de substituição — só aparece quando já existe imagem. */
  replaceTitle: string;
  replaceDescription: string;
  /** Mensagem de arquivo grande demais ("Logotipo acima de 2 MB."). */
  oversizeError: string;
  /** Mensagem de falha no envio ("Não foi possível enviar o logotipo."). */
  uploadError: string;
  /** `square` recorta por `object-contain` (logotipo, que não pode ser cortado);
   * `circle` por `object-cover` (foto de perfil). */
  shape?: "square" | "circle";
  disabled?: boolean;
  acceptedTypes?: string[];
  maxSizeBytes?: number;
  onUpload: (file: File) => Promise<void>;
}

/** Envio de imagem única com preview, allowlist de formato, teto de tamanho e confirmação
 * de substituição (spec 119, achado B).
 *
 * Nasceu da fusão de `LogoUploader` (spec 011) com `AvatarUploader` (spec 012): 47 linhas
 * idênticas, o maior clone do projeto. A diferença entre os dois era só texto e o formato
 * do preview — nada de comportamento —, então tudo o que variava virou prop e o fluxo
 * ficou um só.
 */
export function ImageUploader({
  label,
  imageUrl,
  alt,
  emptyLabel,
  uploadLabel,
  replaceLabel,
  replaceTitle,
  replaceDescription,
  oversizeError,
  uploadError,
  shape = "square",
  disabled = false,
  acceptedTypes = DEFAULT_IMAGE_TYPES,
  maxSizeBytes = DEFAULT_MAX_IMAGE_BYTES,
  onUpload,
}: ImageUploaderProps): JSX.Element {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isUploading, setIsUploading] = React.useState(false);

  const rounded = shape === "circle" ? "rounded-full" : "rounded";
  const fit = shape === "circle" ? "object-cover" : "object-contain";

  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!acceptedTypes.includes(file.type)) {
      setError("Formato inválido — use PNG, JPG ou SVG.");
      return;
    }
    if (file.size > maxSizeBytes) {
      setError(oversizeError);
      return;
    }

    setError(null);
    if (imageUrl) {
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
      setError(uploadError);
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="space-y-2">
      <span className="text-sm font-medium text-primary">{label}</span>
      <div className="flex items-center gap-4">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={alt}
            className={`h-16 w-16 ${rounded} border border-default ${fit}`}
          />
        ) : (
          <div
            className={`flex h-16 w-16 items-center justify-center ${rounded} border border-dashed border-default text-xs text-muted`}
          >
            {emptyLabel}
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={acceptedTypes.join(",")}
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
          {isUploading ? "Enviando..." : imageUrl ? replaceLabel : uploadLabel}
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
        title={replaceTitle}
        description={replaceDescription}
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
