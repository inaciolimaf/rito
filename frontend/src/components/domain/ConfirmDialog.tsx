import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  requireTypedConfirmation?: string;
  onConfirm: () => void | Promise<void>;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  destructive = false,
  requireTypedConfirmation,
  onConfirm,
}: ConfirmDialogProps): JSX.Element {
  const [typedValue, setTypedValue] = React.useState("");
  const [isConfirming, setIsConfirming] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setTypedValue("");
      setIsConfirming(false);
    }
  }, [open]);

  const canConfirm = !requireTypedConfirmation || typedValue === requireTypedConfirmation;

  async function handleConfirm(): Promise<void> {
    setIsConfirming(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        {description && <DialogDescription>{description}</DialogDescription>}

        {requireTypedConfirmation && (
          <div className="mt-4 space-y-1">
            <Label htmlFor="confirm-dialog-typed">
              Digite &ldquo;{requireTypedConfirmation}&rdquo; para confirmar
            </Label>
            <Input
              id="confirm-dialog-typed"
              value={typedValue}
              onChange={(event) => setTypedValue(event.target.value)}
              autoComplete="off"
            />
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={destructive ? "danger" : "default"}
            disabled={!canConfirm || isConfirming}
            onClick={() => void handleConfirm()}
          >
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
