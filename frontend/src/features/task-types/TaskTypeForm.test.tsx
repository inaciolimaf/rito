import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { listSteps } from "@/features/stages/api";
import { suggestTaskReward } from "@/features/task-types/api";
import {
  DEFAULT_TASK_TYPE_FORM_VALUES,
  taskTypeFormSchema,
  type TaskTypeFormValues,
} from "@/features/task-types/schema";
import { TaskTypeForm } from "@/features/task-types/TaskTypeForm";

vi.mock("@/features/stages/api", () => ({
  listSteps: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/features/task-types/api", () => ({
  suggestTaskReward: vi.fn(),
}));

const suggestMock = vi.mocked(suggestTaskReward);
vi.mocked(listSteps);

function Harness(): JSX.Element {
  const form = useForm<TaskTypeFormValues>({
    resolver: zodResolver(taskTypeFormSchema),
    defaultValues: DEFAULT_TASK_TYPE_FORM_VALUES,
  });
  return <TaskTypeForm form={form} />;
}

describe("TaskTypeForm — calculadora ao vivo", () => {
  it("trocar complexidade/duração atualiza a sugestão de pontos (regra 2)", async () => {
    suggestMock.mockResolvedValue({ reward: 8 });
    const user = userEvent.setup();
    render(<Harness />);

    await user.selectOptions(screen.getByLabelText("Complexidade"), "SIMPLES");
    await user.selectOptions(screen.getByLabelText("Tempo médio"), "MIN_15");

    await waitFor(() => expect(screen.getByLabelText("Pontuação")).toHaveValue(8));
    expect(suggestMock).toHaveBeenCalledWith("SIMPLES", "MIN_15");

    // Trocar a duração sugere de novo — o valor ainda é a sugestão anterior.
    suggestMock.mockResolvedValue({ reward: 30 });
    await user.selectOptions(screen.getByLabelText("Tempo médio"), "MIN_30");
    await waitFor(() => expect(screen.getByLabelText("Pontuação")).toHaveValue(30));
  });

  it("valor editado manualmente prevalece sobre sugestões seguintes (regra 2)", async () => {
    suggestMock.mockResolvedValue({ reward: 8 });
    const user = userEvent.setup();
    render(<Harness />);

    await user.selectOptions(screen.getByLabelText("Complexidade"), "SIMPLES");
    await user.selectOptions(screen.getByLabelText("Tempo médio"), "MIN_15");
    await waitFor(() => expect(screen.getByLabelText("Pontuação")).toHaveValue(8));

    // O gestor edita a pontuação…
    const reward = screen.getByLabelText("Pontuação");
    await user.clear(reward);
    await user.type(reward, "42");

    // …e uma nova sugestão NÃO sobrescreve o valor dele.
    suggestMock.mockResolvedValue({ reward: 30 });
    await user.selectOptions(screen.getByLabelText("Tempo médio"), "MIN_30");
    await waitFor(() => expect(suggestMock).toHaveBeenCalledWith("SIMPLES", "MIN_30"));
    expect(reward).toHaveValue(42);
  });
});
