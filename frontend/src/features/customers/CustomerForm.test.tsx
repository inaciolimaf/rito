import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import type { EntityOption } from "@/components/domain/types";
import { CustomerForm } from "@/features/customers/CustomerForm";
import {
  customerFormSchema,
  DEFAULT_CUSTOMER_FORM_VALUES,
  type CustomerFormValues,
} from "@/features/customers/schema";

const MARITAL_STATUSES = [
  { id: 1, name: "SOLTEIRO(A)" },
  { id: 2, name: "CASADO(A)" },
];

const ORIGIN_OPTION: EntityOption = { id: "origin-1", label: "Indicação" };

function Harness({ onSubmit }: { onSubmit: (values: CustomerFormValues) => void }): JSX.Element {
  const form = useForm<CustomerFormValues>({
    resolver: zodResolver(customerFormSchema),
    defaultValues: DEFAULT_CUSTOMER_FORM_VALUES,
  });

  return (
    <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}>
      <CustomerForm
        form={form}
        maritalStatuses={MARITAL_STATUSES}
        onSearchOrigins={async () => [ORIGIN_OPTION]}
        currentOrigin={null}
      />
      <button type="submit">Salvar</button>
    </form>
  );
}

async function selectOrigin(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Origem da pessoa"), "Indi");
  const option = await screen.findByRole("option", { name: "Indicação" });
  await user.click(option);
}

describe("CustomerForm", () => {
  it("alternar PF/PJ mostra e limpa campos", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    expect(screen.getByLabelText("Profissão")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Profissão"), "Advogada");
    expect(screen.getByLabelText("Profissão")).toHaveValue("Advogada");

    await user.click(screen.getByLabelText("Pessoa jurídica"));

    expect(screen.queryByLabelText("Profissão")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("RG")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Razão social")).toBeInTheDocument();
    expect(screen.getByLabelText("CNPJ")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Pessoa física"));

    expect(screen.getByLabelText("Profissão")).toHaveValue("");
  });

  it("representante abre e valida", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    expect(screen.queryByLabelText("Nome do representante")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Adicionar representante"));
    expect(screen.getByLabelText("Nome do representante")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Nome"), "Cliente Teste");
    await selectOrigin(user);
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Nome do representante é obrigatório.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Nome do representante"), "Representante Legal");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [submitted] = onSubmit.mock.calls[0] ?? [];
    expect(submitted).toMatchObject({
      has_representative: true,
      rep_name: "Representante Legal",
    });
  });
});
