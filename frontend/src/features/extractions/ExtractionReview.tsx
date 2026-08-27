import * as React from "react";

import { FieldConfidenceBadge } from "@/features/extractions/FieldConfidenceBadge";
import { OcrTextViewer } from "@/features/extractions/OcrTextViewer";
import type { ExtractionData } from "@/features/extractions/api";

const ROTULOS: Record<string, string> = {
  name: "Nome",
  identification: "CPF/CNPJ",
  birth_date: "Nascimento",
  rg_number: "RG",
  issuer: "Órgão emissor",
  mother_name: "Nome da mãe",
  father_name: "Nome do pai",
  trade_name: "Nome fantasia",
  postal_code: "CEP",
  address: "Endereço",
  city: "Cidade",
  state: "UF",
  partners: "Sócios",
  grantee: "Outorgado",
  process_number: "Número do processo",
  court: "Tribunal",
  case_value: "Valor da causa",
};

export interface ExtractionReviewProps {
  extraction: ExtractionData;
  onApply: (values: Record<string, string>) => void;
  onDiscard: () => void;
  isSaving?: boolean;
}

/** Revisão da extração (spec 091 §6): documento à esquerda, campos à direita.
 *
 * O que a tela precisa deixar óbvio é ONDE olhar. Campo com leitura confiável já vem
 * preenchido; campo incerto (regra 3) vem vazio e destacado, com o valor lido escrito ao
 * lado para copiar — a pessoa confere no documento e decide, que é mais rápido do que
 * apagar um palpite errado. */
export function ExtractionReview({
  extraction,
  onApply,
  onDiscard,
  isSaving = false,
}: ExtractionReviewProps): JSX.Element {
  const [valores, setValores] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(extraction.fields).map(([campo, dados]) => [
        campo,
        dados.prefill ? dados.value : "",
      ]),
    ),
  );

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section aria-label="Documento" className="space-y-2">
        <h3 className="text-sm font-semibold text-primary">{extraction.filename}</h3>
        <p className="text-xs text-muted">
          {extraction.document_kind ? `Tipo: ${extraction.document_kind}` : "Tipo não identificado"}
          {extraction.page_count ? ` · ${extraction.page_count} página(s)` : ""}
          {extraction.used_ocr ? " · lido por OCR" : " · texto do próprio arquivo"}
        </p>
        <OcrTextViewer text={extraction.ocr_text} usedOcr={extraction.used_ocr} />
      </section>

      <section aria-label="Campos extraídos" className="space-y-3">
        {extraction.duplicate && (
          <p role="alert" className="rounded border border-warning bg-warning/10 p-2 text-sm">
            Já existe um cadastro com este documento: <strong>{extraction.duplicate.name}</strong>.
            Atualize o cadastro existente em vez de criar um segundo.
          </p>
        )}

        {Object.entries(extraction.fields).map(([campo, dados]) => (
          <div key={campo} className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs text-muted" htmlFor={`campo-${campo}`}>
                {ROTULOS[campo] ?? campo}
              </label>
              <FieldConfidenceBadge confidence={dados.confidence} isValid={dados.is_valid} />
            </div>
            <input
              id={`campo-${campo}`}
              className={`w-full rounded border bg-surface p-1 text-sm ${
                dados.prefill ? "border-default" : "border-warning"
              }`}
              value={valores[campo] ?? ""}
              onChange={(event) =>
                setValores((atual) => ({ ...atual, [campo]: event.target.value }))
              }
            />
            {!dados.prefill && (
              <p className="text-[11px] text-warning">
                Leitura incerta — o documento parece dizer &ldquo;{dados.value}&rdquo;.
              </p>
            )}
          </div>
        ))}

        <div className="flex gap-2">
          <button
            type="button"
            className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
            disabled={isSaving}
            onClick={() => onApply(valores)}
          >
            Cadastrar
          </button>
          <button
            type="button"
            className="rounded border border-default px-3 py-1 text-sm"
            onClick={onDiscard}
          >
            Descartar
          </button>
        </div>
      </section>
    </div>
  );
}
