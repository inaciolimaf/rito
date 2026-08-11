import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface PayTransactionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (paymentDate: string) => Promise<void>;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Baixa (regra 8, spec 056): pede a data de pagamento, default hoje — o backend rejeita
 * data futura (regra 7), então o campo já nasce limitado a `max=hoje`. */
export function PayTransactionDialog({
  open,
  onOpenChange,
  onConfirm,
}: PayTransactionDialogProps): JSX.Element {
  const [paymentDate, setPaymentDate] = React.useState(today());
  const [isConfirming, setIsConfirming] = React.useState(false);

  React.useEffect(() => {
    if (open) setPaymentDate(today());
  }, [open]);

  async function handleConfirm(): Promise<void> {
    setIsConfirming(true);
    try {
      await onConfirm(paymentDate);
      onOpenChange(false);
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Registrar pagamento</DialogTitle>
        <DialogDescription>Informe a data em que o pagamento foi efetuado.</DialogDescription>

        <div className="mt-4 space-y-1">
          <Label htmlFor="pay-transaction-date">Data de pagamento</Label>
          <Input
            id="pay-transaction-date"
            type="date"
            max={today()}
            value={paymentDate}
            onChange={(event) => setPaymentDate(event.target.value)}
          />
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            type="button"
            disabled={isConfirming || !paymentDate}
            onClick={() => void handleConfirm()}
          >
            Confirmar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
