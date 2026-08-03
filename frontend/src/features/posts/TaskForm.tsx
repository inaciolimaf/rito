import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AssigneeSelector } from "@/features/posts/AssigneeSelector";
import { TaskFlags } from "@/features/posts/TaskFlags";
import { DeadlineField } from "@/features/posts/DeadlineField";
import { RecurrenceFields } from "@/features/posts/RecurrenceFields";
import { RecurrencePreview } from "@/features/posts/RecurrencePreview";
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
  const scheduledDate = watch("scheduled_date");
  const recurrenceValues = {
    isRecurring: watch("is_recurring"),
    period: watch("recurrence_period"),
    repeatOn: watch("recurrence_repeat_on"),
    limitMode: watch("recurrence_limit_mode"),
    untilDate: watch("recurrence_until_date"),
    maxOccurrences: watch("recurrence_max_occurrences"),
  };
  const flagValues = {
    is_important: watch("is_important"),
    is_urgent: watch("is_urgent"),
    is_future: watch("is_future"),
    is_private: watch("is_private"),
    show_in_schedule: watch("show_in_schedule"),
  };

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

      <TaskFlags
        value={flagValues}
        onChange={(next) => {
          setValue("is_important", next.is_important);
          setValue("is_urgent", next.is_urgent);
          setValue("is_future", next.is_future);
          setValue("is_private", next.is_private);
          setValue("show_in_schedule", next.show_in_schedule);
        }}
      />

      <RecurrenceFields
        value={recurrenceValues}
        onChange={(next) => {
          setValue("is_recurring", next.isRecurring);
          setValue("recurrence_period", next.period);
          setValue("recurrence_repeat_on", next.repeatOn);
          setValue("recurrence_limit_mode", next.limitMode);
          setValue("recurrence_until_date", next.untilDate);
          setValue("recurrence_max_occurrences", next.maxOccurrences);
        }}
        error={errors.recurrence_until_date?.message ?? errors.recurrence_max_occurrences?.message}
      />
      {recurrenceValues.isRecurring && (
        <RecurrencePreview
          scheduledDate={scheduledDate}
          period={recurrenceValues.period}
          repeatOn={recurrenceValues.repeatOn}
          untilDate={
            recurrenceValues.limitMode === "until" ? recurrenceValues.untilDate : undefined
          }
          maxOccurrences={
            recurrenceValues.limitMode === "max"
              ? Number(recurrenceValues.maxOccurrences) || undefined
              : undefined
          }
        />
      )}

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
