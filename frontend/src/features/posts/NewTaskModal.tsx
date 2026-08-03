import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { FormModal } from "@/components/domain/FormModal";
import type { EntityOption } from "@/components/domain/types";
import { listLawsuits } from "@/features/lawsuits/api";
import { createPost, type PostPayload } from "@/features/posts/api";
import {
  DEFAULT_TASK_FORM_VALUES,
  taskFormSchema,
  type TaskFormValues,
} from "@/features/posts/schema";
import { TaskForm } from "@/features/posts/TaskForm";
import { listUsers } from "@/features/users/api";
import { ApiError } from "@/lib/errors";

function toPayload(values: TaskFormValues): PostPayload {
  return {
    lawsuit_id: values.lawsuit_id,
    task_type_id: values.task_type_id,
    user_ids: values.user_ids.map((user) => user.id),
    squad_id: values.assignee_mode === "squad" ? values.squad_id : null,
    scheduled_date: values.scheduled_date || null,
    scheduled_time: values.scheduled_time || null,
    end_date: values.end_date || null,
    end_time: values.end_time || null,
    deadline_date: values.deadline_date || null,
    all_day: values.all_day,
    location: values.location || null,
    comments: values.comments || null,
    is_important: values.is_important,
    is_urgent: values.is_urgent,
    is_future: values.is_future,
    is_private: values.is_private,
    show_in_schedule: values.show_in_schedule,
    // Spec 034: série configurada no mesmo POST — o post criado é o template.
    recurrence: values.is_recurring
      ? {
          period: values.recurrence_period,
          repeat_on: values.recurrence_repeat_on,
          until_date:
            values.recurrence_limit_mode === "until" ? values.recurrence_until_date : null,
          max_occurrences:
            values.recurrence_limit_mode === "max"
              ? Number(values.recurrence_max_occurrences)
              : null,
        }
      : null,
  };
}

async function searchLawsuits(query: string): Promise<EntityOption[]> {
  const page = await listLawsuits({ q: query, limit: 20 });
  return page.items.map((item) => {
    const firstParty = item.parties[0]?.name;
    const number = item.process_number ?? item.folder ?? "s/nº";
    return { id: item.id, label: `${firstParty ?? "Processo"} — ${number}` };
  });
}

async function searchUsers(query: string): Promise<EntityOption[]> {
  const page = await listUsers({ q: query, limit: 20 });
  return page.items.map((item) => ({ id: item.id, label: item.name }));
}

export interface NewTaskModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialLawsuit?: EntityOption | null;
}

/** Modal global "Criar nova tarefa" (spec 032 §6) — aberto pelo botão Adicionar do
 * shell. Depois de criar, invalida as listagens de posts para refletir a tarefa nova. */
export function NewTaskModal({
  open,
  onOpenChange,
  initialLawsuit = null,
}: NewTaskModalProps): JSX.Element {
  const queryClient = useQueryClient();
  const [formError, setFormError] = React.useState<ApiError | null>(null);

  async function handleSubmit(values: TaskFormValues): Promise<void> {
    setFormError(null);
    try {
      await createPost(toPayload(values));
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["posts"] });
      await queryClient.invalidateQueries({ queryKey: ["lawsuit-posts"] });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Criar nova tarefa"
      schema={taskFormSchema}
      defaultValues={
        initialLawsuit
          ? { ...DEFAULT_TASK_FORM_VALUES, lawsuit_id: initialLawsuit.id }
          : DEFAULT_TASK_FORM_VALUES
      }
      serverError={formError}
      onSubmit={handleSubmit}
    >
      {(form) => (
        <TaskForm
          form={form}
          onSearchLawsuits={searchLawsuits}
          onSearchUsers={searchUsers}
          initialLawsuit={initialLawsuit}
        />
      )}
    </FormModal>
  );
}
