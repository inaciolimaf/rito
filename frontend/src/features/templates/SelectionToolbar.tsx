import { Button } from "@/components/ui/button";
import { ToneSelect } from "@/features/templates/ToneSelect";
import type { EditorTone } from "@/features/templates/editorAi";

export interface SelectionToolbarProps {
  /** Quantidade de caracteres selecionados — zero esconde a barra. */
  selectionLength: number;
  /** Regra 11: sem IA configurada, a barra não aparece. */
  aiAvailable: boolean;
  isBusy?: boolean;
  onRewrite: () => void;
  onTone: (tone: EditorTone) => void;
  onGround: () => void;
}

/** Barra que aparece ao selecionar texto (spec 088 §6). */
export function SelectionToolbar({
  selectionLength,
  aiAvailable,
  isBusy = false,
  onRewrite,
  onTone,
  onGround,
}: SelectionToolbarProps): JSX.Element | null {
  if (!aiAvailable || selectionLength === 0) return null;
  return (
    <div
      data-testid="selection-toolbar"
      role="toolbar"
      aria-label="Ações de IA para a seleção"
      className="flex flex-wrap items-center gap-2 rounded border border-default bg-surface p-2"
    >
      <span className="text-xs text-muted">{selectionLength} caracteres selecionados</span>
      <Button type="button" size="sm" variant="ghost" disabled={isBusy} onClick={onRewrite}>
        Reescrever
      </Button>
      <ToneSelect onPick={onTone} disabled={isBusy} />
      <Button type="button" size="sm" variant="ghost" disabled={isBusy} onClick={onGround}>
        Sugerir fundamentação
      </Button>
    </div>
  );
}
