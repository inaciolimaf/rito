import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AssigneeSelector } from "@/features/posts/AssigneeSelector";
import { DeadlineField } from "@/features/posts/DeadlineField";
import type { TaskFormValues } from "@/features/posts/schema";
import { TaskTypeSelect } from "@/features/posts/TaskTypeSelect";

export interface TaskFormProps {
  form: UseFormReturn<TaskFormValues>;
  onSearchLawsuits: (query: string) => Promise<EntityOption[]>;
  onSearchUsers: (query: string) => Promise<EntityOption[]>;
  /** Processo pré-selecionado (ex.: abrir o modal de dentro do processo). */
  initialLawsuit?: EntityOption | null;
}

/** Formulário "Criar nova tarefa" (spec 032 §6): processo + tipo + responsáveis como
 * obrigatórios (regra 1), datas do ciclo e prazo fatal independente (regra 7). */
export function TaskForm({
  form,
  onSearchLawsuits,
  onSearchUsers,
  initialLawsuit = null,
}: TaskFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const allDay = watch("all_day");
  const assigneeMode = watch("assignee_mode");
  const userIds = watch("user_ids");
  const squadId = watch("squad_id");
  const taskTypeId = watch("task_type_id");
  const deadlineDate = watch("deadline_date");

  // O picker precisa do rótulo do processo escolhido; o form guarda só o id.
  const [selectedLawsuit, setSelectedLawsuit] = React.useState<EntityOption | null>(initialLawsuit);

  return (
    <>
      <div className="space-y-1">
        <Label>Processo ou caso</Label>
        <EntityPicker
          placeholder="Buscar por cliente ou número…"
          value={selectedLawsuit ? [selectedLawsuit] : []}
          onChange={(next) => {
            setSelectedLawsuit(next[0] ?? null);
            setValue("lawsuit_id", next[0]?.id ?? "", { shouldValidate: true });
          }}
          onSearch={onSearchLawsuits}
        />
        {errors.lawsuit_id && <p className="text-sm text-danger">{errors.lawsuit_id.message}</p>}
      </div>

      <TaskTypeSelect
        id="post-task-type"
        value={taskTypeId}
        onChange={(value) => setValue("task_type_id", value, { shouldValidate: true })}
      />
      {errors.task_type_id && <p className="text-sm text-danger">{errors.task_type_id.message}</p>}

      <AssigneeSelector
        value={{ mode: assigneeMode, userIds, squadId }}
        onChange={(next) => {
          setValue("assignee_mode", next.mode, { shouldValidate: true });
          setValue("user_ids", next.userIds, { shouldValidate: true });
          setValue("squad_id", next.squadId, { shouldValidate: true });
        }}
        onSearchUsers={onSearchUsers}
        error={errors.user_ids?.message ?? errors.squad_id?.message}
      />

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="post-date">Data</Label>
          <Input id="post-date" type="date" {...register("scheduled_date")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="post-time">Hora</Label>
          <Input id="post-time" type="time" disabled={allDay} {...register("scheduled_time")} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <DeadlineField
          id="post-deadline"
          value={deadlineDate}
          onChange={(value) => setValue("deadline_date", value)}
        />
        <div className="space-y-1">
          <Label htmlFor="post-location">Local</Label>
          <Input id="post-location" placeholder="Local do evento" {...register("location")} />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-primary" htmlFor="post-all-day">
        <input id="post-all-day" type="checkbox" {...register("all_day")} />
        Dia inteiro
      </label>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="post-end-date">Término</Label>
          <Input id="post-end-date" type="date" {...register("end_date")} />
          {errors.end_date && <p className="text-sm text-danger">{errors.end_date.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="post-end-time">Hora do término</Label>
          <Input id="post-end-time" type="time" disabled={allDay} {...register("end_time")} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="post-comments">Descrição</Label>
        <textarea
          id="post-comments"
          rows={3}
          className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("comments")}
        />
      </div>
    </>
  );
}
