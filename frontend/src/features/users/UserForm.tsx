import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mapApiErrorToFields } from "@/components/domain/FormModal";
import type { Occupation } from "@/features/users/api";
import { userFormSchema, type UserFormValues } from "@/features/users/schema";
import { durationInputToApi, timeInputToApi } from "@/features/users/timeFormat";
import { WorkScheduleField } from "@/features/users/WorkScheduleField";
import { ApiError } from "@/lib/errors";

export interface UserFormProps {
  defaultValues: UserFormValues;
  occupations: Occupation[];
  /** Regra 9: usuário editando o próprio perfil não pode mudar role/financial_access. */
  canEditRoleAndFinancial: boolean;
  disabled?: boolean;
  serverError?: ApiError | null;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
}

export function UserForm({
  defaultValues,
  occupations,
  canEditRoleAndFinancial,
  disabled = false,
  serverError,
  onSubmit,
}: UserFormProps): JSX.Element {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<UserFormValues>({
    resolver: zodResolver(userFormSchema),
    defaultValues,
  });

  React.useEffect(() => {
    if (!serverError) return;
    for (const { field, message } of mapApiErrorToFields(serverError)) {
      setError(field as keyof UserFormValues, { type: "server", message });
    }
  }, [serverError, setError]);

  const submit = handleSubmit((values) => {
    const payload: Record<string, unknown> = {
      name: values.name,
      role: values.role,
      financial_access: values.financial_access,
      occupation_id: values.occupation_id ? Number(values.occupation_id) : null,
      identification: values.identification || null,
      document: values.document || null,
      birthdate: values.birthdate || null,
      number_ctps: values.number_ctps || null,
      number_oab: values.number_oab || null,
      cellphone: values.cellphone || null,
      phone: values.phone || null,
      salary: values.salary || null,
      admission_date: values.admission_date || null,
      resignation_date: values.resignation_date || null,
      work_start: values.workStart ? timeInputToApi(values.workStart) : null,
      work_interval: values.workInterval ? durationInputToApi(values.workInterval) : null,
      work_end: values.workEnd ? timeInputToApi(values.workEnd) : null,
      points_goal: values.points_goal ? Number(values.points_goal) : null,
      report_deadline: values.report_deadline,
      report_deleted: values.report_deleted,
      is_responsible: values.is_responsible,
    };
    return onSubmit(payload);
  });

  const roleAndFinancialDisabled = disabled || !canEditRoleAndFinancial;

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="max-w-2xl space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="name">Nome</Label>
          <Input id="name" disabled={disabled} {...register("name")} />
          {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
        </div>

        <div className="space-y-1">
          <Label htmlFor="occupation_id">Cargo</Label>
          <select
            id="occupation_id"
            disabled={disabled}
            className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
            {...register("occupation_id")}
          >
            <option value="">Selecione...</option>
            {occupations.map((occupation) => (
              <option key={occupation.id} value={occupation.id}>
                {occupation.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="role">Perfil</Label>
          <select
            id="role"
            disabled={roleAndFinancialDisabled}
            className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
            {...register("role")}
          >
            <option value="COLABORADOR">Colaborador</option>
            <option value="ADMINISTRADOR">Administrador</option>
            <option value="GESTOR">Gestor</option>
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="financial_access">Acesso financeiro</Label>
          <select
            id="financial_access"
            disabled={roleAndFinancialDisabled}
            className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
            {...register("financial_access")}
          >
            <option value="NONE">Sem acesso</option>
            <option value="READ_ONLY">Somente visualização</option>
            <option value="FULL">Acesso completo</option>
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="identification">CPF</Label>
          <Input id="identification" disabled={disabled} {...register("identification")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="document">RG</Label>
          <Input id="document" disabled={disabled} {...register("document")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="birthdate">Data de nascimento</Label>
          <Input id="birthdate" type="date" disabled={disabled} {...register("birthdate")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="number_ctps">CTPS</Label>
          <Input id="number_ctps" disabled={disabled} {...register("number_ctps")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="number_oab">OAB (NNNNNN/UF)</Label>
          <Input id="number_oab" disabled={disabled} {...register("number_oab")} />
          {errors.number_oab && <p className="text-sm text-danger">{errors.number_oab.message}</p>}
        </div>

        <div className="space-y-1">
          <Label htmlFor="cellphone">Celular</Label>
          <Input id="cellphone" disabled={disabled} {...register("cellphone")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="phone">Telefone</Label>
          <Input id="phone" disabled={disabled} {...register("phone")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="salary">Salário</Label>
          <Input id="salary" disabled={disabled} {...register("salary")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="points_goal">Meta de pontos</Label>
          <Input id="points_goal" type="number" disabled={disabled} {...register("points_goal")} />
        </div>

        <div className="space-y-1">
          <Label htmlFor="admission_date">Admissão</Label>
          <Input
            id="admission_date"
            type="date"
            disabled={disabled}
            {...register("admission_date")}
          />
        </div>

        <div className="space-y-1">
          <Label htmlFor="resignation_date">Demissão</Label>
          <Input
            id="resignation_date"
            type="date"
            disabled={disabled}
            {...register("resignation_date")}
          />
          {errors.resignation_date && (
            <p className="text-sm text-danger">{errors.resignation_date.message}</p>
          )}
        </div>
      </div>

      <WorkScheduleField register={register} errors={errors} disabled={disabled} />

      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="checkbox" disabled={disabled} {...register("report_deadline")} />
          Recebe relatório de prazos
        </label>
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="checkbox" disabled={disabled} {...register("report_deleted")} />
          Recebe relatório de exclusões
        </label>
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="checkbox" disabled={disabled} {...register("is_responsible")} />
          Responsável padrão
        </label>
      </div>

      {serverError && !serverError.errors?.length && (
        <p role="alert" className="text-sm text-danger">
          {serverError.message}
        </p>
      )}

      {!disabled && (
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Salvando..." : "Salvar"}
        </Button>
      )}
    </form>
  );
}
