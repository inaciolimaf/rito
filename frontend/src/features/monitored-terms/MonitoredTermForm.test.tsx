import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { MonitoredTermForm } from "@/features/monitored-terms/MonitoredTermForm";
import {
  DEFAULT_MONITORED_TERM_FORM_VALUES,
  monitoredTermFormSchema,
  type MonitoredTermFormValues,
} from "@/features/monitored-terms/schema";

const STATES = [
  { code: "MG", name: "Minas Gerais", ibge_code: 31 },
  { code: "SP", name: "São Paulo", ibge_code: 35 },
];

const USERS = [{ id: "u1", name: "Ana Advogada" }] as never[];

function Harness({
  onSubmit,
}: {
  onSubmit: (values: MonitoredTermFormValues) => void;
}): JSX.Element {
  const form = useForm<MonitoredTermFormValues>({
    resolver: zodResolver(monitoredTermFormSchema),
    defaultValues: DEFAULT_MONITORED_TERM_FORM_VALUES,
  });

  return (
    <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}>
      <MonitoredTermForm form={form} states={STATES} users={USERS} />
      <button type="submit">Salvar</button>
    </form>
  );
}

describe("MonitoredTermForm", () => {
  it("alterna os campos pelo tipo: UF só aparece para OAB", async () => {
    const user = userEvent.setup();
    render(<Harness onSubmit={vi.fn()} />);

    // default é OAB: UF visível
    expect(screen.getByLabelText("UF da OAB")).toBeInTheDocument();
    expect(screen.getByLabelText("Número da OAB")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "CPF");
    expect(screen.queryByLabelText("UF da OAB")).not.toBeInTheDocument();
    expect(screen.getByLabelText("CPF")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "CNPJ");
    expect(screen.queryByLabelText("UF da OAB")).not.toBeInTheDocument();
    expect(screen.getByLabelText("CNPJ")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "OAB");
    expect(screen.getByLabelText("UF da OAB")).toBeInTheDocument();
  });

  it("OAB sem UF não submete e mostra o erro", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Número da OAB"), "114962");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("UF da OAB é obrigatória.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("OAB com letra é rejeitada; CPF pede 11 dígitos", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Número da OAB"), "114A62");
    await user.selectOptions(screen.getByLabelText("UF da OAB"), "MG");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(
      await screen.findByText("Número de OAB deve conter apenas dígitos."),
    ).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "CPF");
    await user.clear(screen.getByLabelText("CPF"));
    await user.type(screen.getByLabelText("CPF"), "123");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("CPF deve ter 11 dígitos.")).toBeInTheDocument();

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submete OAB válida com UF e responsável", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Número da OAB"), "114962");
    await user.selectOptions(screen.getByLabelText("UF da OAB"), "MG");
    await user.selectOptions(
      screen.getByLabelText("Responsável pelas intimações (opcional)"),
      "u1",
    );
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "OAB", value: "114962", oab_state: "MG", user_id: "u1" }),
      expect.anything(),
    );
  });
});
