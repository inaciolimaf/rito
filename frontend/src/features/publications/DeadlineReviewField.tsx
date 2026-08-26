import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfidenceBadge } from "@/features/publications/ConfidenceBadge";

export interface DeadlineReviewFieldProps {
  /** Data calculada pelo backend a partir dos dias que a IA leu. */
  suggested: string | null;
  confidence: number | null;
  /** Como a IA chegou ao prazo (regra 7) — fica ao lado, não escondido. */
  reasoning: string | null;
  shouldPrefill: boolean;
  value: string;
  onChange: (value: string) => void;
}

/** O campo de prazo da revisão (spec 086, regras 1, 4 e 7).
 *
 * O rótulo diz "sugerido pela IA — confirme" porque é literalmente o que está
 * acontecendo: até alguém salvar, o escritório não tem esse prazo. */
export function DeadlineReviewField({
  suggested,
  confidence,
  reasoning,
  shouldPrefill,
  value,
  onChange,
}: DeadlineReviewFieldProps): JSX.Element {
  React.useEffect(() => {
    if (shouldPrefill && suggested && !value) {
      onChange(suggested);
    }
    // Só na primeira vez que a sugestão chega: reaplicar sobrescreveria o que a
    // pessoa digitou.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggested, shouldPrefill]);

  return (
    <div className="space-y-1" data-testid="deadline-review">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor="deadline-review-input">Prazo sugerido pela IA — confirme</Label>
        <ConfidenceBadge confidence={confidence} />
      </div>
      <Input
        id="deadline-review-input"
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {suggested && !shouldPrefill && (
        <p className="text-xs text-warning" role="alert">
          A IA sugeriu {new Date(`${suggested}T12:00:00`).toLocaleDateString("pt-BR")}, mas a
          confiança está baixa — o campo ficou vazio de propósito.
        </p>
      )}
      {reasoning && (
        <p className="text-xs text-muted" data-testid="deadline-reasoning">
          Como a IA chegou nisso: {reasoning}
        </p>
      )}
    </div>
  );
}
