import * as React from "react";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { listLawsuits } from "@/features/lawsuits/api";
import { linkPublicationToLawsuit } from "@/features/publications/api";
import { ApiError } from "@/lib/errors";

export interface LinkToLawsuitDialogProps {
  publicationId: string | null;
  onOpenChange: (open: boolean) => void;
  onLinked: () => void;
}

async function searchLawsuits(query: string): Promise<EntityOption[]> {
  const page = await listLawsuits({ q: query, limit: 20 });
  return page.items.map((item) => {
    const firstParty = item.parties[0]?.name;
    const number = item.process_number ?? item.folder ?? "s/nº";
    return { id: item.id, label: `${firstParty ?? "Processo"} — ${number}` };
  });
}

/** Vínculo manual (spec 048 §6, regra 6): escolher o processo dispara o roteamento
 * da spec 045 e cria a tarefa — sem sair da lista de intimações. */
export function LinkToLawsuitDialog({
  publicationId,
  onOpenChange,
  onLinked,
}: LinkToLawsuitDialogProps): JSX.Element {
  const [selected, setSelected] = React.useState<EntityOption[]>([]);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (publicationId === null) {
      setSelected([]);
      setError(null);
    }
  }, [publicationId]);

  async function handleConfirm(): Promise<void> {
    const lawsuit = selected[0];
    if (!publicationId || !lawsuit) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await linkPublicationToLawsuit(publicationId, lawsuit.id);
      onLinked();
      onOpenChange(false);
    } catch (submitError) {
      setError(submitError instanceof ApiError ? submitError.message : "Erro ao vincular.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={publicationId !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Vincular a um processo</DialogTitle>
        <DialogDescription>
          A intimação passa a fazer parte do processo escolhido e uma tarefa é criada para o
          responsável (spec 045).
        </DialogDescription>

        <div className="mt-4">
          <EntityPicker
            label="Processo"
            placeholder="Buscar por cliente ou número…"
            value={selected}
            onChange={setSelected}
            onSearch={searchLawsuits}
          />
        </div>

        {error && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {error}
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            disabled={selected.length === 0 || isSubmitting}
            onClick={() => void handleConfirm()}
          >
            Vincular
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
