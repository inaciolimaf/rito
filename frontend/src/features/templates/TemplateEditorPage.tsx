import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Link, useParams } from "react-router-dom";

import { useAutosave } from "@/components/domain/useAutosave";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { GenerateDocumentDialog } from "@/features/templates/GenerateDocumentDialog";
import {
  getTemplate,
  updateTemplate,
  type TemplateFormPayload,
  type TemplateType,
} from "@/features/templates/api";
import { TemplateEditor } from "@/features/templates/TemplateEditor";

const TYPE_LABELS: Record<TemplateType, string> = {
  CONTRATO: "Contrato",
  PETICAO: "Petição",
  RECURSO: "Recurso",
  DOCUMENTO: "Documento",
};

const STATUS_LABELS = {
  idle: "",
  saving: "Salvando…",
  saved: "Salvo",
  error: "Falha ao salvar — tentando de novo na próxima mudança",
} as const;

/** Editor de modelo (spec 065) — cabeçalho/rodapé/marca d'água são campos separados
 * do corpo (regra 1); tudo autosalva junto, sem botão "Salvar" (regra 2). */
export function TemplateEditorPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [generateOpen, setGenerateOpen] = React.useState(false);

  const { data: template, isLoading } = useQuery({
    queryKey: ["templates", id],
    queryFn: () => getTemplate(id!),
    enabled: !!id,
  });

  const [draft, setDraft] = React.useState<TemplateFormPayload | null>(null);

  React.useEffect(() => {
    if (template && draft === null) {
      setDraft({
        name: template.name,
        type: template.type,
        content: template.content,
        header_content: template.header_content,
        footer_content: template.footer_content,
        watermark_text: template.watermark_text,
      });
    }
  }, [template, draft]);

  const status = useAutosave(
    draft,
    async (value) => {
      if (!id || !value) return;
      const saved = await updateTemplate(id, value);
      queryClient.setQueryData(["templates", id], saved);
      await queryClient.invalidateQueries({ queryKey: ["templates"] });
    },
    { enabled: draft !== null },
  );

  if (isLoading || !template || !draft) {
    return <p className="p-6 text-sm text-muted">Carregando modelo…</p>;
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/library" className="text-xs text-muted underline">
            Modelos
          </Link>
          <h1 className="text-lg font-semibold text-primary">{draft.name || "Modelo sem nome"}</h1>
        </div>
        <div className="flex items-center gap-3">
          <p className="text-sm text-muted" role="status">
            {STATUS_LABELS[status]}
          </p>
          <Button onClick={() => setGenerateOpen(true)}>Gerar documento</Button>
        </div>
      </div>

      {id && (
        <GenerateDocumentDialog
          open={generateOpen}
          onOpenChange={setGenerateOpen}
          templateId={id}
          templateName={draft.name}
        />
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="template-editor-name">Nome</Label>
          <Input
            id="template-editor-name"
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="template-editor-type">Tipo</Label>
          <select
            id="template-editor-type"
            className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            value={draft.type}
            onChange={(event) => setDraft({ ...draft, type: event.target.value as TemplateType })}
          >
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="template-editor-watermark">Marca d'água</Label>
          <Input
            id="template-editor-watermark"
            value={draft.watermark_text ?? ""}
            placeholder="Ex.: MINUTA"
            onChange={(event) => setDraft({ ...draft, watermark_text: event.target.value || null })}
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="template-editor-header">Cabeçalho</Label>
        <textarea
          id="template-editor-header"
          rows={2}
          className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          value={draft.header_content}
          onChange={(event) => setDraft({ ...draft, header_content: event.target.value })}
        />
      </div>

      <TemplateEditor
        content={draft.content}
        onChange={(html) =>
          setDraft((current) => (current ? { ...current, content: html } : current))
        }
      />

      <div className="space-y-1">
        <Label htmlFor="template-editor-footer">Rodapé</Label>
        <textarea
          id="template-editor-footer"
          rows={2}
          className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          value={draft.footer_content}
          onChange={(event) => setDraft({ ...draft, footer_content: event.target.value })}
        />
      </div>
    </div>
  );
}
