import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { StageForm } from "@/features/stages/StageForm";
import {
  DEFAULT_STAGE_FORM_VALUES,
  stageFormSchema,
  type StageFormValues,
} from "@/features/stages/schema";

const STEPS = [
  { id: 1, name: "Marketing", position: 1 },
  { id: 2, name: "Negociação", position: 2 },
];

function Harness({ onSubmit }: { onSubmit: (values: StageFormValues) => void }): JSX.Element {
  const form = useForm<StageFormValues>({
    resolver: zodResolver(stageFormSchema),
    defaultValues: DEFAULT_STAGE_FORM_VALUES,
  });

  return (
    <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}>
      <StageForm form={form} steps={STEPS} />
      <button type="submit">Salvar</button>
    </form>
  );
}

describe("StageForm", () => {
  it("condiciona dias à estagnação: campo desabilitado até marcar, e exige dia > 0", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    expect(screen.getByLabelText("Dias para estagnação")).toBeDisabled();

    await user.type(screen.getByLabelText("Nome da etapa"), "Aguardando Documentos");
    await user.selectOptions(screen.getByLabelText("Fase"), "1");
    await user.click(screen.getByLabelText("Marcar como estagnado após um número de dias"));

    expect(screen.getByLabelText("Dias para estagnação")).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(
      await screen.findByText("Informe um número de dias maior que zero."),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Dias para estagnação"), "10");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [submitted] = onSubmit.mock.calls[0] ?? [];
    expect(submitted).toMatchObject({
      name: "Aguardando Documentos",
      step_id: "1",
      enable_stagnant_days: true,
      stagnant_days: "10",
    });
  });
});
