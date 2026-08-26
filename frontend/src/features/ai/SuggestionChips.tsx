export interface SuggestionChipsProps {
  suggestions: string[];
  onPick: (suggestion: string) => void;
  disabled?: boolean;
}

/** Sugestões da tela (spec 085, regra 5): o que costuma ser útil perguntar ali. */
export function SuggestionChips({
  suggestions,
  onPick,
  disabled = false,
}: SuggestionChipsProps): JSX.Element | null {
  if (suggestions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2" data-testid="suggestion-chips">
      {suggestions.map((suggestion) => (
        <button
          key={suggestion}
          type="button"
          disabled={disabled}
          onClick={() => onPick(suggestion)}
          className="rounded-full border border-default px-3 py-1 text-xs text-muted hover:text-primary disabled:opacity-50"
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
