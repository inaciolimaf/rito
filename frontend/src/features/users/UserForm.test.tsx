import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_USER_FORM_VALUES } from "@/features/users/schema";
import { UserForm } from "@/features/users/UserForm";

const OCCUPATIONS = [
  { id: 1, name: "Advogado Gestor" },
  { id: 24, name: "Recepcionista" },
];

describe("UserForm", () => {
  it("bloqueia o submit quando o nome está vazio", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <UserForm
        defaultValues={DEFAULT_USER_FORM_VALUES}
        occupations={OCCUPATIONS}
        canEditRoleAndFinancial
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Nome é obrigatório.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("valida e submete convertendo os campos para o formato da API", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <UserForm
        defaultValues={DEFAULT_USER_FORM_VALUES}
        occupations={OCCUPATIONS}
        canEditRoleAndFinancial
        onSubmit={onSubmit}
      />,
    );

    await user.type(screen.getByLabelText("Nome"), "Fulano de Tal");
    await user.selectOptions(screen.getByLabelText("Cargo"), "24");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [submitted] = onSubmit.mock.calls[0] ?? [];
    expect(submitted).toMatchObject({ name: "Fulano de Tal", occupation_id: 24 });
  });

  it("rejeita OAB fora do formato NNNNNN/UF", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <UserForm
        defaultValues={DEFAULT_USER_FORM_VALUES}
        occupations={OCCUPATIONS}
        canEditRoleAndFinancial
        onSubmit={onSubmit}
      />,
    );

    await user.type(screen.getByLabelText("Nome"), "Fulano");
    await user.type(screen.getByLabelText("OAB (NNNNNN/UF)"), "abc123");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("OAB deve estar no formato NNNNNN/UF.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("desabilita perfil e acesso financeiro quando canEditRoleAndFinancial é falso (regra 9)", () => {
    render(
      <UserForm
        defaultValues={DEFAULT_USER_FORM_VALUES}
        occupations={OCCUPATIONS}
        canEditRoleAndFinancial={false}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Perfil")).toBeDisabled();
    expect(screen.getByLabelText("Acesso financeiro")).toBeDisabled();
    expect(screen.getByLabelText("Nome")).toBeEnabled();
  });
});
