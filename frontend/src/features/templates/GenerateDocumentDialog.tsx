import { useMutation, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listCustomers } from "@/features/customers/api";
import { listLawsuits } from "@/features/lawsuits/api";
import {
  generateTemplatePdf,
  resolveTemplate,
  saveTemplateToCloud,
  sendTemplateEmail,
} from "@/features/templates/api";
import { ApiError } from "@/lib/errors";

export interface GenerateDocumentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateId: string;
  templateName: string;
}

async function searchCustomers(query: string): Promise<EntityOption[]> {
  const page = await listCustomers({ q: query });
  return page.items.map((item) => ({ id: item.id, label: item.name }));
}

async function searchLawsuits(query: string): Promise<EntityOption[]> {
  const page = await listLawsuits({ q: query });
  return page.items.map((item) => ({
    id: item.id,
    label: item.process_number ?? item.folder ?? "Processo sem número",
  }));
}

/** Diálogo de geração de documento (spec 067) — escolhe cliente/processo, mostra as
 * variáveis ausentes (spec 066) e as 3 ações (baixar/enviar/salvar na nuvem). */
export function GenerateDocumentDialog({
  open,
  onOpenChange,
  templateId,
  templateName,
}: GenerateDocumentDialogProps): JSX.Element {
  const [customer, setCustomer] = React.useState<EntityOption[]>([]);
  const [lawsuit, setLawsuit] = React.useState<EntityOption[]>([]);
  const [showEmailForm, setShowEmailForm] = React.useState(false);
  const [emailTo, setEmailTo] = React.useState("");
  const [emailSubject, setEmailSubject] = React.useState("");

  const customerId = customer[0]?.id ?? null;
  const lawsuitId = lawsuit[0]?.id ?? null;

  const { data: resolved } = useQuery({
    queryKey: ["template-resolve-preview", templateId, customerId, lawsuitId],
    queryFn: () => resolveTemplate(templateId, { customer_id: customerId, lawsuit_id: lawsuitId }),
    enabled: open,
  });

  const download = useMutation({
    mutationFn: () =>
      generateTemplatePdf(
        templateId,
        { customer_id: customerId, lawsuit_id: lawsuitId },
        `${templateName}.pdf`,
      ),
  });

  const saveToCloud = useMutation({
    mutationFn: () => {
      if (!lawsuitId) throw new Error("Selecione um processo para salvar na nuvem.");
      return saveTemplateToCloud(templateId, { customer_id: customerId, lawsuit_id: lawsuitId });
    },
  });

  const sendEmail = useMutation({
    mutationFn: () =>
      sendTemplateEmail(templateId, {
        customer_id: customerId,
        lawsuit_id: lawsuitId,
        to: emailTo,
        subject: emailSubject || undefined,
      }),
    onSuccess: () => setShowEmailForm(false),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogTitle>Gerar documento — {templateName}</DialogTitle>

        <div className="space-y-3">
          <EntityPicker
            label="Cliente (opcional)"
            placeholder="Buscar cliente…"
            value={customer}
            onChange={setCustomer}
            onSearch={searchCustomers}
          />
          <EntityPicker
            label="Processo (opcional — obrigatório para salvar na nuvem)"
            placeholder="Buscar processo…"
            value={lawsuit}
            onChange={setLawsuit}
            onSearch={searchLawsuits}
          />

          {resolved && resolved.missing.length > 0 && (
            <p className="text-sm text-danger">
              Variáveis sem dado: {resolved.missing.join(", ")} — o PDF sai sinalizado.
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <Button disabled={download.isPending} onClick={() => download.mutate()}>
              Baixar PDF
            </Button>
            <Button
              variant="outline"
              disabled={!lawsuitId || saveToCloud.isPending}
              onClick={() => saveToCloud.mutate()}
            >
              Salvar na nuvem do processo
            </Button>
            <Button variant="outline" onClick={() => setShowEmailForm((current) => !current)}>
              Enviar por e-mail
            </Button>
          </div>

          {saveToCloud.isSuccess && (
            <p className="text-sm text-success">Salvo na nuvem do processo.</p>
          )}
          {saveToCloud.error instanceof ApiError && (
            <p className="text-sm text-danger">{saveToCloud.error.message}</p>
          )}

          {showEmailForm && (
            <div className="space-y-2 rounded border border-default p-3">
              <div className="space-y-1">
                <Label htmlFor="generate-email-to">E-mail do destinatário</Label>
                <Input
                  id="generate-email-to"
                  type="email"
                  value={emailTo}
                  onChange={(event) => setEmailTo(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="generate-email-subject">Assunto (opcional)</Label>
                <Input
                  id="generate-email-subject"
                  value={emailSubject}
                  onChange={(event) => setEmailSubject(event.target.value)}
                />
              </div>
              <Button
                size="sm"
                disabled={emailTo.trim() === "" || sendEmail.isPending}
                onClick={() => sendEmail.mutate()}
              >
                Enviar
              </Button>
              {sendEmail.isSuccess && <p className="text-sm text-success">E-mail enviado.</p>}
              {sendEmail.error instanceof ApiError && (
                <p className="text-sm text-danger">{sendEmail.error.message}</p>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
