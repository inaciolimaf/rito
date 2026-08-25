import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import type { PartnershipData, ShareLawsuitPayload } from "@/features/partners/api";

export interface ShareLawsuitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Parcerias ATIVAS — só com elas dá para compartilhar. */
  partnerships: PartnershipData[];
  lawsuitLabel: string;
  onShare: (payload: ShareLawsuitPayload) => Promise<unknown>;
}

/** Compartilhar um processo (regra 3) com o escopo na cara do usuário: o diálogo diz o
 * que o parceiro passa a ver e o que continua invisível (regra 4), e o financeiro só
 * abre com marcação explícita (regra 9). */
export function ShareLawsuitDialog({
  open,
  onOpenChange,
  partnerships,
  lawsuitLabel,
  onShare,
}: ShareLawsuitDialogProps): JSX.Element {
  const [partnershipId, setPartnershipId] = React.useState("");
  const [canViewFinancial, setCanViewFinancial] = React.useState(false);
  const [canCreateTasks, setCanCreateTasks] = React.useState(true);
  const [sharing, setSharing] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setPartnershipId("");
      setCanViewFinancial(false);
      setCanCreateTasks(true);
    }
  }, [open]);

  async function handleShare(): Promise<void> {
    setSharing(true);
    try {
      await onShare({
        partnership_id: partnershipId,
        can_view_financial: canViewFinancial,
        can_create_tasks: canCreateTasks,
      });
      onOpenChange(false);
    } finally {
      setSharing(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Compartilhar processo</DialogTitle>
        <DialogDescription>{lawsuitLabel}</DialogDescription>

        <div className="mt-4 space-y-4">
          <div className="space-y-1">
            <Label htmlFor="share-partnership">Parceiro</Label>
            <select
              id="share-partnership"
              className="w-full rounded border border-default bg-surface p-2 text-sm"
              value={partnershipId}
              onChange={(event) => setPartnershipId(event.target.value)}
            >
              <option value="">Selecione o escritório</option>
              {partnerships.map((partnership) => (
                <option key={partnership.id} value={partnership.id}>
                  {partnership.partner_name ?? partnership.invited_email}
                </option>
              ))}
            </select>
          </div>

          <section
            data-testid="share-scope"
            className="space-y-2 rounded border border-default bg-surface p-3 text-sm"
          >
            <p className="font-medium text-primary">O parceiro passa a ver</p>
            <ul className="list-disc pl-5 text-muted">
              <li>Dados deste processo, partes e timeline</li>
              <li>Tarefas deste processo</li>
            </ul>
            <p className="font-medium text-primary">O parceiro continua sem ver</p>
            <ul className="list-disc pl-5 text-muted">
              <li>Seus outros processos e sua carteira de contatos</li>
              <li>Financeiro, configurações, relatórios e BI do escritório</li>
            </ul>
          </section>

          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="block font-medium text-primary">Ver valores do processo</span>
              <span className="block text-sm text-muted">
                Valor da causa e honorários. Desligado, o parceiro não vê valor nenhum.
              </span>
            </span>
            <Checkbox
              aria-label="Ver valores do processo"
              checked={canViewFinancial}
              onCheckedChange={(checked) => setCanViewFinancial(checked === true)}
            />
          </label>

          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="block font-medium text-primary">Criar tarefas no processo</span>
              <span className="block text-sm text-muted">
                Desligado, o compartilhamento é somente leitura.
              </span>
            </span>
            <Checkbox
              aria-label="Criar tarefas no processo"
              checked={canCreateTasks}
              onCheckedChange={(checked) => setCanCreateTasks(checked === true)}
            />
          </label>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="button" disabled={!partnershipId || sharing} onClick={handleShare}>
              Compartilhar
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
