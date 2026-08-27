import { useMutation } from "@tanstack/react-query";
import * as React from "react";

import { FileDropzone } from "@/features/attachments/FileDropzone";
import { ExtractionReview } from "@/features/extractions/ExtractionReview";
import {
  applyExtraction,
  discardExtraction,
  extractDocument,
  type ExtractionData,
} from "@/features/extractions/api";
import { ApiError } from "@/lib/errors";

const TIPOS = [
  { value: "", label: "Detectar automaticamente" },
  { value: "rg", label: "RG" },
  { value: "cnh", label: "CNH" },
  { value: "contrato_social", label: "Contrato social" },
  { value: "procuracao", label: "Procuração" },
  { value: "peticao", label: "Petição inicial" },
];

export interface ExtractDocumentDialogProps {
  /** Origem do contato — obrigatória no cadastro (spec 017), a IA não escapa disso. */
  originId: string;
  onCreated?: (customerId: string) => void;
}

/** Cadastro a partir de um documento (spec 091 §6).
 *
 * Duas etapas, nunca uma: subir o arquivo NÃO cadastra nada. O que volta é uma proposta
 * para revisar — e é a revisão que vira cadastro, pelo fluxo auditado da 084. */
export function ExtractDocumentDialog({
  originId,
  onCreated,
}: ExtractDocumentDialogProps): JSX.Element {
  const [tipo, setTipo] = React.useState("");
  const [extraction, setExtraction] = React.useState<ExtractionData | null>(null);
  const [erro, setErro] = React.useState<string | null>(null);

  const enviar = useMutation({
    mutationFn: (file: File) => extractDocument(file, tipo || undefined),
    onSuccess: (dados) => {
      setExtraction(dados);
      setErro(null);
    },
    onError: (error: unknown) => {
      setErro(error instanceof ApiError ? error.message : "Não foi possível ler este documento.");
    },
  });

  const aplicar = useMutation({
    mutationFn: (valores: Record<string, string>) => {
      if (!extraction) throw new Error("Nenhuma extração para aplicar.");
      return applyExtraction(extraction.id, {
        target_type: "customer",
        arguments: {
          name: valores.name,
          origin_id: originId,
          type: valores.identification && valores.identification.length > 11 ? "PJ" : "PF",
          identification: valores.identification || undefined,
          city: valores.city || undefined,
          state: valores.state || undefined,
        },
        corrections: valores,
      });
    },
    onSuccess: (dados) => {
      setExtraction(dados);
      if (dados.applied_id) onCreated?.(dados.applied_id);
    },
    onError: (error: unknown) => {
      setErro(error instanceof ApiError ? error.message : "O cadastro foi recusado.");
    },
  });

  if (extraction && extraction.status === "applied") {
    return (
      <p role="status" className="rounded border border-success bg-success/10 p-3 text-sm">
        Cadastro criado a partir de {extraction.filename}. O arquivo foi guardado na pasta do
        contato.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {!extraction && (
        <>
          <label className="flex flex-col text-xs text-muted">
            Tipo do documento
            <select
              className="mt-1 rounded border border-default bg-surface p-1 text-sm"
              value={tipo}
              onChange={(event) => setTipo(event.target.value)}
            >
              {TIPOS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <FileDropzone
            onFiles={(files) => files[0] && enviar.mutate(files[0])}
            disabled={enviar.isPending}
          />
          {enviar.isPending && <p className="text-sm text-muted">Lendo o documento…</p>}
        </>
      )}

      {erro && (
        <p role="alert" className="rounded border border-danger bg-danger/10 p-2 text-sm">
          {erro}
        </p>
      )}

      {extraction && extraction.status !== "discarded" && (
        <ExtractionReview
          extraction={extraction}
          isSaving={aplicar.isPending}
          onApply={(valores) => aplicar.mutate(valores)}
          onDiscard={() => {
            void discardExtraction(extraction.id).then(() => setExtraction(null));
          }}
        />
      )}
    </div>
  );
}
