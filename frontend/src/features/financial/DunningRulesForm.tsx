import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import {
  listDunningRules,
  upsertDunningRule,
  type DunningChannel,
  type DunningRuleData,
} from "@/features/financial/dunning-api";
import {
  DEFAULT_DUNNING_RULE_FORM_VALUES,
  dunningRuleFormSchema,
  type DunningRuleFormValues,
} from "@/features/financial/schema";
import { TemplateEditor } from "@/features/financial/TemplateEditor";
import { ApiError } from "@/lib/errors";

const CHANNEL_LABELS: Record<DunningChannel, string> = {
  EMAIL: "E-mail",
  SMS: "SMS",
  WHATSAPP: "WhatsApp",
};

function toFormValues(rule: DunningRuleData): DunningRuleFormValues {
  return {
    days_offset: String(rule.days_offset),
    channel: rule.channel,
    template: rule.template,
    is_active: rule.is_active,
  };
}

/** Régua de cobrança (spec 061, regras 3/4/9) — upsert por `(days_offset, channel)`, sem
 * `DELETE`: desativar é sempre `is_active=false`. Clicar numa régua existente carrega o
 * formulário para edição — não há modal, a lista de réguas costuma ser pequena. */
export function DunningRulesForm(): JSX.Element {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [serverError, setServerError] = React.useState<string | null>(null);

  const {
    data: rules,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["dunning-rules"],
    queryFn: () => listDunningRules(),
  });

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors },
  } = useForm<DunningRuleFormValues>({
    resolver: zodResolver(dunningRuleFormSchema),
    defaultValues: DEFAULT_DUNNING_RULE_FORM_VALUES,
  });
  const template = watch("template");

  const upsert = useMutation({
    mutationFn: (values: DunningRuleFormValues) =>
      upsertDunningRule({
        days_offset: Number(values.days_offset),
        channel: values.channel,
        template: values.template,
        is_active: values.is_active,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dunning-rules"] });
      setServerError(null);
      setEditingId(null);
      reset(DEFAULT_DUNNING_RULE_FORM_VALUES);
    },
    onError: (mutationError: unknown) => {
      setServerError(
        mutationError instanceof ApiError ? mutationError.message : "Erro ao salvar a régua.",
      );
    },
  });

  function editRule(rule: DunningRuleData): void {
    setEditingId(rule.id);
    reset(toFormValues(rule));
  }

  function cancelEdit(): void {
    setEditingId(null);
    reset(DEFAULT_DUNNING_RULE_FORM_VALUES);
  }

  const columns: DataTableColumn<DunningRuleData>[] = [
    {
      id: "days_offset",
      header: "Disparo",
      cell: (row) =>
        row.days_offset < 0
          ? `${Math.abs(row.days_offset)} dias antes do vencimento`
          : `${row.days_offset} dias após o vencimento`,
    },
    { id: "channel", header: "Canal", cell: (row) => CHANNEL_LABELS[row.channel] },
    {
      id: "is_active",
      header: "Situação",
      cell: (row) => (row.is_active ? "Ativa" : "Inativa"),
    },
  ];

  return (
    <div className="space-y-6">
      <form
        className="space-y-4 rounded border border-default bg-surface p-4"
        onSubmit={handleSubmit((values) => upsert.mutate(values))}
      >
        <h3 className="text-sm font-medium text-primary">
          {editingId ? "Editar régua" : "Nova régua"}
        </h3>

        {serverError && <p className="text-sm text-danger">{serverError}</p>}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="rule-days-offset">
              Dias em relação ao vencimento (negativo = antes)
            </Label>
            <Input id="rule-days-offset" type="number" {...register("days_offset")} />
            {errors.days_offset && (
              <p className="text-sm text-danger">{errors.days_offset.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <Label htmlFor="rule-channel">Canal</Label>
            <select
              id="rule-channel"
              className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              {...register("channel")}
            >
              {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <TemplateEditor
          id="rule-template"
          value={template}
          onChange={(value) => setValue("template", value, { shouldValidate: true })}
          error={errors.template?.message}
        />

        <div className="flex items-center gap-2">
          <input id="rule-is-active" type="checkbox" {...register("is_active")} />
          <Label htmlFor="rule-is-active">Régua ativa</Label>
        </div>

        <div className="flex gap-2">
          <Button type="submit" disabled={upsert.isPending}>
            {editingId ? "Salvar régua" : "Criar régua"}
          </Button>
          {editingId && (
            <Button type="button" variant="ghost" onClick={cancelEdit}>
              Cancelar edição
            </Button>
          )}
        </div>
      </form>

      <DataTable
        columns={columns}
        data={rules ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhuma régua de cobrança configurada ainda."
        rowActions={(row) => (
          <button
            type="button"
            className="text-sm text-accent underline"
            onClick={() => editRule(row)}
          >
            Editar
          </button>
        )}
      />
    </div>
  );
}
