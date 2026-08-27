import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AutomationBuilder } from "@/features/automations/AutomationBuilder";
import { BranchEditor } from "@/features/automations/BranchEditor";

const CANDIDATOS = [
  { position: 1, label: "2. Criar tarefa" },
  { position: 2, label: "3. Notificar" },
];

describe("BranchEditor", () => {
  it("marca uma ação no ramo escolhido (spec 094 §7)", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <BranchEditor
        branches={["urgente", "normal"]}
        assignment={{ urgente: [], normal: [] }}
        candidates={CANDIDATOS}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByLabelText("2. Criar tarefa no ramo urgente"));

    expect(onChange).toHaveBeenCalledWith({ urgente: [1], normal: [] });
  });

  it("uma ação pertence a no máximo um ramo — marcar no segundo tira do primeiro", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <BranchEditor
        branches={["urgente", "normal"]}
        assignment={{ urgente: [1], normal: [] }}
        candidates={CANDIDATOS}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByLabelText("2. Criar tarefa no ramo normal"));

    expect(onChange).toHaveBeenCalledWith({ urgente: [], normal: [1] });
  });

  it("sem ações depois da decisão, explica o que fazer em vez de mostrar caixas vazias", () => {
    render(
      <BranchEditor
        branches={["urgente", "normal"]}
        assignment={{}}
        candidates={[]}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/Adicione ações depois da decisão/)).toBeInTheDocument();
  });
});

describe("AutomationBuilder com decisão por IA", () => {
  it("monta a decisão com ramos e distribui as ações seguintes", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<AutomationBuilder onSave={onSave} />);

    await user.type(screen.getByLabelText("Nome da automação"), "Triagem de intimação");
    await user.selectOptions(screen.getByLabelText("Tipo da ação 1"), "llm_decision");
    await user.type(
      screen.getByLabelText("Pergunta da decisão"),
      "Esta intimação exige resposta em até 5 dias?",
    );
    await user.type(screen.getByLabelText("Novo ramo"), "urgente{Enter}");
    await user.type(screen.getByLabelText("Novo ramo"), "normal{Enter}");
    await user.selectOptions(screen.getByLabelText("Ramo padrão"), "normal");

    await user.click(screen.getByRole("button", { name: "Adicionar ação" }));
    await user.selectOptions(screen.getByLabelText("Tipo da ação 2"), "create_task");
    await user.click(screen.getByLabelText("2. Criar tarefa no ramo urgente"));

    await user.click(screen.getByRole("button", { name: "Salvar automação" }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        actions: [
          expect.objectContaining({
            action_kind: "llm_decision",
            branches: { urgente: [1], normal: [] },
            action_config: expect.objectContaining({
              default_branch: "normal",
              branches: ["urgente", "normal"],
            }),
          }),
          expect.objectContaining({ action_kind: "create_task" }),
        ],
      }),
    );
  });

  it("o ramo padrão é explicado, não escondido — é o caminho quando a IA falha", async () => {
    const user = userEvent.setup();
    render(<AutomationBuilder onSave={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText("Tipo da ação 1"), "llm_decision");

    const bloco = screen.getByLabelText("Decisão por IA");
    expect(within(bloco).getByText(/nunca para por causa da IA/)).toBeInTheDocument();
    expect(within(bloco).getByText(/nunca altera nada no sistema/)).toBeInTheDocument();
  });
});
