import { z } from "zod";

import { FormModal } from "@/components/domain/FormModal";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { MovementPayload, TimelineItem } from "@/features/lawsuits/api";

const movementFormSchema = z.object({
  occurred_at: z.string().min(1, "Data e hora são obrigatórias."),
  title: z.string().min(1, "Título é obrigatório."),
  body: z.string().optional(),
});

type MovementFormValues = z.infer<typeof movementFormSchema>;

export interface AddMovementModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Preenchido na edição (só movimentações manuais, regra 3). */
  editing?: TimelineItem | null;
  onSubmit: (values: MovementPayload) => Promise<void>;
}

function toLocalInputValue(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Movimentação manual (spec 026 §6) — criação e edição compartilham o mesmo modal. */
export function AddMovementModal({
  open,
  onOpenChange,
  editing,
  onSubmit,
}: AddMovementModalProps): JSX.Element {
  async function handleSubmit(values: MovementFormValues): Promise<void> {
    await onSubmit({
      occurred_at: new Date(values.occurred_at).toISOString(),
      title: values.title,
      body: values.body || null,
    });
  }

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={editing ? "Editar movimentação" : "Nova movimentação"}
      schema={movementFormSchema}
      defaultValues={
        editing
          ? {
              occurred_at: toLocalInputValue(editing.occurred_at),
              title: editing.title,
              body: editing.summary ?? "",
            }
          : { occurred_at: "", title: "", body: "" }
      }
      onSubmit={handleSubmit}
    >
      {(form) => (
        <>
          <div className="space-y-1">
            <Label htmlFor="movement-occurred-at">Data e hora</Label>
            <Input
              id="movement-occurred-at"
              type="datetime-local"
              {...form.register("occurred_at")}
            />
            {form.formState.errors.occurred_at && (
              <p className="text-sm text-danger">{form.formState.errors.occurred_at.message}</p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="movement-title">Título</Label>
            <Input id="movement-title" {...form.register("title")} />
            {form.formState.errors.title && (
              <p className="text-sm text-danger">{form.formState.errors.title.message}</p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="movement-body">Detalhes</Label>
            <textarea
              id="movement-body"
              rows={3}
              className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              {...form.register("body")}
            />
          </div>
        </>
      )}
    </FormModal>
  );
}
