import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm, type Resolver, type UseFormReturn } from "react-hook-form";
import type { z } from "zod";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { ServerErrorAlert } from "@/components/domain/ServerErrorAlert";
import { describeApiErrors } from "@/components/domain/apiErrors";
import { ApiError } from "@/lib/errors";

export { describeApiErrors, mapApiErrorToFields } from "@/components/domain/apiErrors";
export type { ServerFieldError, ApiErrorSummary } from "@/components/domain/apiErrors";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface FormModalProps<TSchema extends z.ZodType<any, any, any>> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  schema: TSchema;
  defaultValues: z.infer<TSchema>;
  onSubmit: (values: z.infer<TSchema>) => Promise<void>;
  serverError?: ApiError | null;
  children: (form: UseFormReturn<z.infer<TSchema>>) => React.ReactNode;
  submitLabel?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function FormModal<TSchema extends z.ZodType<any, any, any>>({
  open,
  onOpenChange,
  title,
  description,
  schema,
  defaultValues,
  onSubmit,
  serverError,
  children,
  submitLabel = "Salvar",
}: FormModalProps<TSchema>): JSX.Element {
  type Values = z.infer<TSchema>;
  const form = useForm<Values, unknown, Values>({
    // zod 4 types the resolver as input -> output; for a generic schema TS cannot prove they
    // match. Every schema passed here has input = output (no transforms), so this is sound.
    resolver: zodResolver(schema) as unknown as Resolver<Values, unknown, Values>,
    defaultValues,
  });
  // react-hook-form só mantém `formState` reativo para os campos lidos durante o render do
  // componente que chamou `useForm` — ler `form.formState.isDirty` só dentro do event handler
  // `requestClose` (abaixo) devolvia sempre `false` (Proxy nunca "assinado"). Desestruturar
  // aqui, no corpo do componente, resolve.
  const { isDirty } = form.formState;
  const [showDirtyGuard, setShowDirtyGuard] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      form.reset(defaultValues);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  React.useEffect(() => {
    if (!serverError) return;
    for (const { field, message } of describeApiErrors(serverError).fields) {
      form.setError(field as never, { type: "server", message });
    }
  }, [serverError, form]);

  function requestClose(): void {
    if (isDirty) {
      setShowDirtyGuard(true);
      return;
    }
    onOpenChange(false);
  }

  const handleSubmit = form.handleSubmit(async (values) => {
    await onSubmit(values);
  });

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) {
            requestClose();
            return;
          }
          onOpenChange(next);
        }}
      >
        <DialogContent>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}

          <form
            onSubmit={(event) => void handleSubmit(event)}
            className="mt-4 space-y-4"
            noValidate
          >
            {children(form)}

            <ServerErrorAlert error={serverError} />

            <div className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={requestClose}>
                Cancelar
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {submitLabel}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={showDirtyGuard}
        onOpenChange={setShowDirtyGuard}
        title="Descartar alterações?"
        description="Você tem alterações não salvas. Se sair agora, elas serão perdidas."
        confirmLabel="Descartar"
        destructive
        onConfirm={() => {
          setShowDirtyGuard(false);
          onOpenChange(false);
        }}
      />
    </>
  );
}
