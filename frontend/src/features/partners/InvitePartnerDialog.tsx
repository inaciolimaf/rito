import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PartnershipInviteResult } from "@/features/partners/api";

export interface InvitePartnerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInvite: (email: string) => Promise<PartnershipInviteResult>;
}

/** Convite por e-mail (regra 2): se o e-mail ainda não tem conta no Rito, o diálogo
 * avisa que o convite é de cadastro e a parceria fica pendente até o aceite. */
export function InvitePartnerDialog({
  open,
  onOpenChange,
  onInvite,
}: InvitePartnerDialogProps): JSX.Element {
  const [email, setEmail] = React.useState("");
  const [result, setResult] = React.useState<PartnershipInviteResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setEmail("");
      setResult(null);
      setError(null);
    }
  }, [open]);

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setSending(true);
    setError(null);
    try {
      setResult(await onInvite(email));
    } catch {
      setError("Não foi possível enviar o convite. Verifique o e-mail e tente de novo.");
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Convidar escritório parceiro</DialogTitle>
        <DialogDescription>
          A parceria é bilateral: aceita uma vez, vale para os dois lados. Compartilhar processos
          continua sendo uma decisão por processo.
        </DialogDescription>

        {result === null ? (
          <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
            <div className="space-y-1">
              <Label htmlFor="partner-email">E-mail do escritório</Label>
              <Input
                id="partner-email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="off"
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={sending}>
                Enviar convite
              </Button>
            </div>
          </form>
        ) : (
          <div className="mt-4 space-y-3" data-testid="invite-result">
            <p className="text-sm text-primary">
              {result.account_exists
                ? "Convite enviado. A parceria fica pendente até o outro escritório aceitar."
                : "Esse e-mail ainda não tem conta no Rito — enviamos um convite de cadastro. A parceria fica pendente."}
            </p>
            {/* Spec 102, regra 19: o código não é mais exibido aqui. Ele vai por e-mail
                para quem foi convidado — mostrar o segredo para quem CRIOU o convite é o
                contorno de não haver envio, não o contrato. */}
            <p className="text-sm text-secondary">
              O link de aceite foi enviado para o e-mail informado.
            </p>
            <div className="flex justify-end">
              <Button type="button" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
