export interface BranchEditorProps {
  /** Nomes dos ramos declarados na decisão. */
  branches: string[];
  /** Ramo → posições das ações que pertencem a ele. */
  assignment: Record<string, number[]>;
  /** Posições disponíveis (as ações que vêm DEPOIS da decisão), com rótulo. */
  candidates: { position: number; label: string }[];
  onChange: (assignment: Record<string, number[]>) => void;
}

/** Quais ações pertencem a cada ramo (spec 094 §7).
 *
 * A ação continua na sequência única do editor — o ramo só diz quando ela roda. Foi a
 * forma de ramificar sem transformar o editor num fluxograma: a pessoa continua lendo a
 * automação de cima para baixo, e o que muda é a marcação de "isto só acontece se o
 * ramo for X".
 *
 * Uma posição pertence a no máximo um ramo. Marcar em dois ramos significaria "roda nos
 * dois", que é o mesmo que não estar em ramo nenhum — e essa ambiguidade só apareceria
 * na execução. */
export function BranchEditor({
  branches,
  assignment,
  candidates,
  onChange,
}: BranchEditorProps): JSX.Element {
  function toggle(branch: string, position: number): void {
    const atual = assignment[branch] ?? [];
    const marcado = atual.includes(position);
    const proximo: Record<string, number[]> = {};
    for (const nome of branches) {
      const lista = (assignment[nome] ?? []).filter((item) => item !== position);
      proximo[nome] = nome === branch && !marcado ? [...lista, position].sort() : lista;
    }
    onChange(proximo);
  }

  if (candidates.length === 0) {
    return (
      <p className="text-xs text-muted">
        Adicione ações depois da decisão para distribuí-las entre os ramos.
      </p>
    );
  }

  return (
    <div className="space-y-2" aria-label="Ações por ramo">
      {branches.map((branch) => (
        <fieldset key={branch} className="rounded border border-default p-2">
          <legend className="px-1 text-xs text-muted">Ramo &ldquo;{branch}&rdquo;</legend>
          <div className="flex flex-wrap gap-3">
            {candidates.map((candidate) => (
              <label key={candidate.position} className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  aria-label={`${candidate.label} no ramo ${branch}`}
                  checked={(assignment[branch] ?? []).includes(candidate.position)}
                  onChange={() => toggle(branch, candidate.position)}
                />
                {candidate.label}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
