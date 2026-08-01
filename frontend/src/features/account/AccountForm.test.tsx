import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccountForm } from "@/features/account/AccountForm";
import { DEFAULT_ACCOUNT_VALUES } from "@/features/account/schema";
import { VIACEP_KNOWN_CEP } from "@/mocks/handlers";

async function fillMinimalValidForm(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Razão social"), "Escritório Modelo Ltda");
  await user.type(screen.getByLabelText("Nome fantasia"), "Escritório Modelo");
  await user.type(screen.getByLabelText("CPF/CNPJ"), "11.222.333/0001-81");
  await user.type(screen.getByLabelText("CEP"), VIACEP_KNOWN_CEP);
  await user.type(screen.getByLabelText("Endereço"), "Av. Paulista, 1000");
  await user.type(screen.getByLabelText("Bairro"), "Bela Vista");
  await user.type(screen.getByLabelText("Cidade"), "São Paulo");
  await user.type(screen.getByLabelText("UF"), "SP");
  await user.type(screen.getByLabelText("Celular"), "11999998888");
  await user.type(screen.getByLabelText("Telefone"), "1130004000");
  await user.type(screen.getByLabelText("E-mail principal"), "contato@escritorio.com.br");
  await user.type(screen.getByLabelText("E-mail financeiro"), "financeiro@escritorio.com.br");
}

describe("AccountForm", () => {
  it("bloqueia o submit e mostra erros quando os campos obrigatórios estão vazios", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<AccountForm defaultValues={DEFAULT_ACCOUNT_VALUES} onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Razão social é obrigatória.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("valida e submete com os valores preenchidos", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<AccountForm defaultValues={DEFAULT_ACCOUNT_VALUES} onSubmit={onSubmit} />);

    await fillMinimalValidForm(user);
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [submitted] = onSubmit.mock.calls[0] ?? [];
    expect(submitted).toMatchObject({
      name: "Escritório Modelo Ltda",
      identification: "11.222.333/0001-81",
    });
  });

  it("busca o CEP na ViaCEP e preenche estado/cidade/endereço/bairro (regra 2)", async () => {
    const user = userEvent.setup();
    render(<AccountForm defaultValues={DEFAULT_ACCOUNT_VALUES} onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText("CEP"), VIACEP_KNOWN_CEP);
    await user.tab();

    await waitFor(() => expect(screen.getByLabelText("Cidade")).toHaveValue("São Paulo"));
    expect(screen.getByLabelText("UF")).toHaveValue("SP");
    expect(screen.getByLabelText("Endereço")).toHaveValue("Av. Paulista");
    expect(screen.getByLabelText("Bairro")).toHaveValue("Bela Vista");
  });

  it("desabilita os campos e esconde o botão salvar quando disabled (regra 6)", () => {
    render(<AccountForm defaultValues={DEFAULT_ACCOUNT_VALUES} disabled onSubmit={vi.fn()} />);

    expect(screen.getByLabelText("Razão social")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();
  });
});
