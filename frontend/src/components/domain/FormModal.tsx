import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
import type { z } from "zod";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { ApiError } from "@/lib/errors";

export interface ServerFieldError {
  field: string;
  message: string;
}

/** Regra 4: erro de validação do servidor (422) mapeia para o campo correspondente. */
export function mapApiErrorToFields(error: ApiError): ServerFieldError[] {
  if (!Array.isArray(error.errors)) return [];
  const mapped: ServerFieldError[] = [];
  for (const item of error.errors) {
    if (
      typeof item === "object" &&
      item !== null &&
      "loc" in item &&
      "msg" in item &&
      Array.isArray((item as { loc: unknown }).loc)
    ) {
      const loc = (item as { loc: unknown[] }).loc;
      const field = loc[loc.length - 1];
      if (typeof field === "string") {
        mapped.push({ field, message: String((item as { msg: unknown }).msg) });
      }
    }
  }
  return mapped;
}

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
  const form = useForm<z.infer<TSchema>>({
    resolver: zodResolver(schema),
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
    for (const { field, message } of mapApiErrorToFields(serverError)) {
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

            {serverError && !serverError.errors?.length && (
              <p role="alert" className="text-sm text-danger">
                {serverError.message}
              </p>
            )}

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
