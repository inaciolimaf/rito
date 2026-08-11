import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { SeriesScope } from "@/features/financial/api";

export interface SeriesScopeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  destructive?: boolean;
  onConfirm: (scope: SeriesScope) => Promise<void>;
}

/** Regra 7/8 (spec 057): editar/excluir série pede o escopo — "esta e as futuras" ou
 * "todas" — antes de agir; parcela/ocorrência já paga nunca é afetada em nenhum dos
 * dois (garantido no backend, não aqui). */
export function SeriesScopeDialog({
  open,
  onOpenChange,
  title,
  description,
  destructive = false,
  onConfirm,
}: SeriesScopeDialogProps): JSX.Element {
  const [scope, setScope] = React.useState<SeriesScope>("future");
  const [isConfirming, setIsConfirming] = React.useState(false);

  React.useEffect(() => {
    if (open) setScope("future");
  }, [open]);

  async function handleConfirm(): Promise<void> {
    setIsConfirming(true);
    try {
      await onConfirm(scope);
      onOpenChange(false);
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>

        <div className="mt-4 space-y-2">
          <label className="flex items-center gap-2 text-sm text-primary">
            <input
              type="radio"
              name="series-scope"
              checked={scope === "future"}
              onChange={() => setScope("future")}
            />
            Esta e as futuras (não pagas)
          </label>
          <label className="flex items-center gap-2 text-sm text-primary">
            <input
              type="radio"
              name="series-scope"
              checked={scope === "all"}
              onChange={() => setScope("all")}
            />
            Todas (não pagas)
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant={destructive ? "danger" : "default"}
            disabled={isConfirming}
            onClick={() => void handleConfirm()}
          >
            Confirmar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
