import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_USER_FORM_VALUES } from "@/features/users/schema";
import { UserForm } from "@/features/users/UserForm";
import { ApiError } from "@/lib/errors";

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

  it("salário é campo com máscara pt-BR, e o 422 do servidor aparece (spec 138, regra 5)", async () => {
    const user = userEvent.setup();
    // `loc: ["body"]` é o que um `model_validator` do Pydantic produz (jornada e demissão
    // em `users/schemas.py`): não é um campo, e antes sumia sem deixar rastro.
    const serverError = new ApiError({
      type: "https://rito.app/errors/validation",
      title: "Dados inválidos",
      status: 422,
      detail: "Dados inválidos.",
      instance: "/api/v1/users/u1",
      errors: [
        { loc: ["body"], msg: "work_end deve ser depois de work_start.", type: "value_error" },
      ],
    });

    render(
      <UserForm
        defaultValues={DEFAULT_USER_FORM_VALUES}
        occupations={OCCUPATIONS}
        canEditRoleAndFinancial
        serverError={serverError}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("work_end deve ser depois de work_start.")).toBeInTheDocument();

    // O campo Salário passou a ser o `MoneyField` do design system: digitar em pt-BR
    // exibe em pt-BR, e o valor que vai para a API é o cru com ponto que o `Decimal` do
    // backend aceita.
    await user.type(screen.getByLabelText("Salário"), "350000");
    expect(screen.getByLabelText("Salário")).toHaveValue("3.500,00");
  });
});
