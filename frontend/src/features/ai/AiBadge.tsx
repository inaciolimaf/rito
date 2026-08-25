import { Sparkles } from "lucide-react";

export interface AiBadgeProps {
  /** Quando veio da IA, o badge fica — permanentemente (spec 084, regra 9). */
  createdByAi: boolean;
  title?: string;
}

/** Marca um registro criado ou alterado pela IA. É permanente de propósito: quem lê o
 * cadastro seis meses depois precisa saber de onde ele veio. */
export function AiBadge({ createdByAi, title }: AiBadgeProps): JSX.Element | null {
  if (!createdByAi) return null;
  return (
    <span
      data-testid="ai-badge"
      title={title ?? "Registro criado ou alterado pela IA, com confirmação humana."}
      className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent"
    >
      <Sparkles aria-hidden className="size-3" />
      IA
    </span>
  );
}
