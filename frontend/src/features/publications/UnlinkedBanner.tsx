import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface UnlinkedBannerProps {
  count: number;
  onFilterUnlinked: () => void;
}

/** Regras 1/2 (spec 048): não vinculadas ganham destaque no topo da tela, com
 * contador e uma ação de um clique só para entrar no modo de trabalho da
 * controladoria (`linked=false`). */
export function UnlinkedBanner({
  count,
  onFilterUnlinked,
}: UnlinkedBannerProps): JSX.Element | null {
  if (count === 0) {
    return null;
  }
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 rounded border border-warning bg-warning/10 px-4 py-3"
    >
      <div className="flex items-center gap-2 text-sm text-primary">
        <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />
        <span>
          <strong>{count}</strong>{" "}
          {count === 1 ? "intimação não vinculada" : "intimações não vinculadas"} a um processo.
        </span>
      </div>
      <Button variant="outline" onClick={onFilterUnlinked}>
        Ver não vinculadas
      </Button>
    </div>
  );
}
