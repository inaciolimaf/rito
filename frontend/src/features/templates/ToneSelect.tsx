import type { EditorTone } from "@/features/templates/editorAi";

const TONES: { value: EditorTone; label: string }[] = [
  { value: "formal", label: "Formal" },
  { value: "objetivo", label: "Objetivo" },
  { value: "tecnico", label: "Mais técnico" },
  { value: "simples", label: "Mais simples" },
];

export interface ToneSelectProps {
  onPick: (tone: EditorTone) => void;
  disabled?: boolean;
}

/** Os quatro tons da regra 4 (spec 088). */
export function ToneSelect({ onPick, disabled = false }: ToneSelectProps): JSX.Element {
  return (
    <select
      aria-label="Ajustar o tom"
      disabled={disabled}
      defaultValue=""
      className="rounded border border-default bg-surface p-1 text-xs"
      onChange={(event) => {
        if (event.target.value) onPick(event.target.value as EditorTone);
      }}
    >
      <option value="">Ajustar tom…</option>
      {TONES.map((tone) => (
        <option key={tone.value} value={tone.value}>
          {tone.label}
        </option>
      ))}
    </select>
  );
}
