import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import type { EntityOption } from "@/components/domain/types";

export interface TransferBeforeDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** Destinos possíveis — quem está sendo excluído já vem fora desta lista. */
  options: EntityOption[];
  onTransfer: (destinationId: string) => Promise<void>;
}

/** Regra 3/7 (spec 014): excluir um registro "em uso" exige escolher um destino que recebe
 * tudo antes da exclusão — transferência tudo-ou-nada. Reutilizado por specs 015/016 para o
 * mesmo padrão em outras taxonomias hierárquicas. */
export function TransferBeforeDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  options,
  onTransfer,
}: TransferBeforeDeleteDialogProps): JSX.Element {
  const [destinationId, setDestinationId] = React.useState("");
  const [isTransferring, setIsTransferring] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setDestinationId("");
      setIsTransferring(false);
    }
  }, [open]);

  async function handleConfirm(): Promise<void> {
    if (!destinationId) return;
    setIsTransferring(true);
    try {
      await onTransfer(destinationId);
      onOpenChange(false);
    } finally {
      setIsTransferring(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        {description && <DialogDescription>{description}</DialogDescription>}

        <div className="mt-4 space-y-1">
          <Label htmlFor="transfer-destination">Transferir para</Label>
          <select
            id="transfer-destination"
            className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            value={destinationId}
            onChange={(event) => setDestinationId(event.target.value)}
          >
            <option value="">Selecione um destino</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            type="button"
            disabled={!destinationId || isTransferring}
            onClick={() => void handleConfirm()}
          >
            Transferir e excluir
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
