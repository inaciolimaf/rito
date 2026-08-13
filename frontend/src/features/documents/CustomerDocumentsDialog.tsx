import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { DocumentBrowser } from "@/features/documents/DocumentBrowser";

export interface CustomerDocumentsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string | null;
  customerName?: string | null;
}

/** Nuvem de documentos por contato (spec 063, docs §4.5) num diálogo — a listagem de
 * contatos não tem tela de detalhe própria, então não há aba onde encaixar isso. */
export function CustomerDocumentsDialog({
  open,
  onOpenChange,
  customerId,
  customerName,
}: CustomerDocumentsDialogProps): JSX.Element {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogTitle>Nuvem de documentos</DialogTitle>
        <DialogDescription>{customerName ?? "Contato"}</DialogDescription>
        {customerId && <DocumentBrowser scopeType="CUSTOMER" scopeId={customerId} />}
      </DialogContent>
    </Dialog>
  );
}
