import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { SquadForm } from "@/features/squads/SquadForm";
import {
  DEFAULT_SQUAD_FORM_VALUES,
  squadFormSchema,
  type SquadFormValues,
} from "@/features/squads/schema";

const USERS = [
  { id: "1", name: "Ana" },
  { id: "2", name: "Bruno" },
  { id: "3", name: "Carla" },
];

function Harness({ onSubmit }: { onSubmit: (values: SquadFormValues) => void }): JSX.Element {
  const form = useForm<SquadFormValues>({
    resolver: zodResolver(squadFormSchema),
    defaultValues: DEFAULT_SQUAD_FORM_VALUES,
  });

  return (
    <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}>
      <SquadForm form={form} users={USERS} />
      <button type="submit">Salvar</button>
    </form>
  );
}

describe("SquadForm", () => {
  it("seleciona múltiplos colaboradores e submete os ids marcados", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Nome do time"), "Time Cível");
    await user.click(screen.getByLabelText("Ana"));
    await user.click(screen.getByLabelText("Carla"));
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [submitted] = onSubmit.mock.calls[0] ?? [];
    expect(submitted).toMatchObject({ name: "Time Cível" });
    expect(new Set(submitted.member_ids)).toEqual(new Set(["1", "3"]));
  });

  it("avisa quando o time fica sem membros, sem bloquear o submit (regra 2)", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Nome do time"), "Time Vazio");

    expect(
      screen.getByText("Este time ficará sem membros — você pode adicionar depois."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [submitted] = onSubmit.mock.calls[0] ?? [];
    expect(submitted.member_ids).toEqual([]);
  });

  it("bloqueia o submit quando o nome está vazio", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await user.click(screen.getByLabelText("Ana"));
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Nome é obrigatório.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
