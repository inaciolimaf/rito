import { zodResolver } from "@hookform/resolvers/zod";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { listSquads } from "@/features/squads/api";
import {
  DEFAULT_TASK_FORM_VALUES,
  taskFormSchema,
  type TaskFormValues,
} from "@/features/posts/schema";
import { TaskForm } from "@/features/posts/TaskForm";
import { listTaskTypes } from "@/features/task-types/api";

vi.mock("@/features/task-types/api", () => ({
  listTaskTypes: vi.fn().mockResolvedValue({
    items: [
      {
        id: "tt-1",
        name: "ANÁLISE DO CASO",
        reward: 8,
        is_active: true,
        is_system: false,
        step_id: null,
        step_name: null,
        complexity: "SIMPLES",
        duration: "MIN_15",
        show_in_schedule: false,
        last_assigned_at: null,
        created_at: "2026-08-01T00:00:00Z",
      },
    ],
    total: 1,
  }),
}));

vi.mock("@/features/squads/api", () => ({
  listSquads: vi.fn().mockResolvedValue({
    items: [{ id: "squad-1", name: "Time Contencioso" }],
    next_cursor: null,
    total: 1,
  }),
}));

vi.mocked(listTaskTypes);
vi.mocked(listSquads);

function Harness({ onSubmit }: { onSubmit: (values: TaskFormValues) => void }): JSX.Element {
  const form = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema),
    defaultValues: { ...DEFAULT_TASK_FORM_VALUES, lawsuit_id: "lawsuit-1" },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)} noValidate>
        <TaskForm
          form={form}
          onSearchLawsuits={vi.fn().mockResolvedValue([])}
          onSearchUsers={vi.fn().mockResolvedValue([])}
          initialLawsuit={{ id: "lawsuit-1", label: "Maria — 0001234-34.2026.8.26.0100" }}
        />
        <button type="submit">Salvar</button>
      </form>
    </QueryClientProvider>
  );
}

describe("TaskForm", () => {
  it("valida obrigatórios e mostra a pontuação no select de tarefa", async () => {
    const submit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={submit} />);

    // O tipo de tarefa aparece com os pontos (Taskscore visível).
    expect(
      await screen.findByRole("option", { name: "ANÁLISE DO CASO (8 pts)" }),
    ).toBeInTheDocument();

    // Processo pré-selecionado, mas sem tipo e sem responsável: validação barra.
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Selecione a tarefa.")).toBeInTheDocument();
    expect(await screen.findByText("Adicione pelo menos 1 responsável.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();

    // Preenchendo tipo + atribuição (via time), o submit passa com o processo pré-selecionado.
    await user.selectOptions(screen.getByLabelText("Tarefa"), "tt-1");
    await user.click(screen.getByRole("button", { name: "Time" }));
    await user.selectOptions(
      await screen.findByLabelText("Time", { selector: "select" }),
      "squad-1",
    );
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    const submitted = submit.mock.calls[0]?.[0] as TaskFormValues;
    expect(submitted.lawsuit_id).toBe("lawsuit-1");
  });

  it("alterna entre usuários e time na atribuição", async () => {
    const user = userEvent.setup();
    render(<Harness onSubmit={vi.fn()} />);

    // Começa no modo usuários (EntityPicker de responsáveis).
    expect(screen.getByLabelText("Responsáveis")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Time" }));
    const squadSelect = await screen.findByLabelText("Time", { selector: "select" });
    expect(await screen.findByRole("option", { name: "Time Contencioso" })).toBeInTheDocument();

    // Sem escolher o time, a validação aponta.
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Selecione o time.")).toBeInTheDocument();

    await user.selectOptions(squadSelect, "squad-1");
    await user.click(screen.getByRole("button", { name: "Usuários" }));
    expect(screen.getByLabelText("Responsáveis")).toBeInTheDocument();
  });
});
