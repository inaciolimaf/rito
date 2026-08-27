import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AutomationBuilder } from "@/features/automations/AutomationBuilder";

describe("AutomationBuilder", () => {
  it("monta gatilho e ações e envia na ordem da tela (spec 092 §6)", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<AutomationBuilder onSave={onSave} />);

    await user.type(screen.getByLabelText("Nome da automação"), "Intimação vira tarefa");
    await user.selectOptions(screen.getByLabelText("Gatilho"), "publication.received");
    await user.selectOptions(screen.getByLabelText("Tipo da ação 1"), "notify");
    await user.click(screen.getByRole("button", { name: "Adicionar ação" }));
    await user.selectOptions(screen.getByLabelText("Tipo da ação 2"), "create_task");
    await user.click(screen.getByRole("button", { name: "Salvar automação" }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Intimação vira tarefa",
        trigger_kind: "publication.received",
        actions: [
          expect.objectContaining({ action_kind: "notify" }),
          expect.objectContaining({ action_kind: "create_task" }),
        ],
      }),
    );
  });

  it("o campo de dias só aparece quando o tempo é em dias", async () => {
    const user = userEvent.setup();
    render(<AutomationBuilder onSave={vi.fn()} />);

    expect(screen.queryByLabelText("Dias da ação 1")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Tempo da ação 1"), "business_days");
    expect(screen.getByLabelText("Dias da ação 1")).toHaveValue(1);
  });

  it("remover uma ação renumera as que sobram", async () => {
    const user = userEvent.setup();
    render(<AutomationBuilder onSave={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Adicionar ação" }));
    await user.selectOptions(screen.getByLabelText("Tipo da ação 2"), "change_stage");
    await user.click(screen.getByRole("button", { name: "Remover ação 1" }));

    const primeira = screen.getByLabelText("Ação 1");
    expect(within(primeira).getByLabelText("Tipo da ação 1")).toHaveValue("change_stage");
  });

  it("sem nome não dá para salvar — automação sem nome é impossível de achar depois", () => {
    render(<AutomationBuilder onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Salvar automação" })).toBeDisabled();
  });
});
