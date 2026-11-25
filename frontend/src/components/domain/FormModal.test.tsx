import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormModal } from "@/components/domain/FormModal";
import { ApiError } from "@/lib/errors";

const schema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
});

function Harness({
  onSubmit,
  serverError,
}: {
  onSubmit: (values: z.infer<typeof schema>) => Promise<void>;
  serverError?: ApiError | null;
}): JSX.Element {
  return (
    <FormModal
      open
      onOpenChange={() => undefined}
      title="Novo contato"
      schema={schema}
      defaultValues={{ name: "" }}
      onSubmit={onSubmit}
      serverError={serverError}
    >
      {(form) => (
        <div>
          <Label htmlFor="name">Nome</Label>
          <Input id="name" {...form.register("name")} />
          {form.formState.errors.name && <p role="alert">{form.formState.errors.name.message}</p>}
        </div>
      )}
    </FormModal>
  );
}

describe("FormModal", () => {
  it("valida pelo schema Zod e não chama onSubmit se inválido", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<Harness onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Nome é obrigatório.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("mapeia erro 422 do servidor para o campo correspondente", () => {
    const serverError = new ApiError({
      type: "https://rito.app/errors/validation",
      title: "Dados inválidos",
      status: 422,
      detail: "Um ou mais campos são inválidos.",
      instance: "/api/v1/contatos",
      errors: [{ loc: ["body", "name"], msg: "Já existe um contato com este nome." }],
    });

    render(<Harness onSubmit={vi.fn()} serverError={serverError} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Já existe um contato com este nome.");
  });

  it("bloqueia fechamento com alterações não salvas (dirty guard)", async () => {
    const user = userEvent.setup();

    render(<Harness onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText("Nome"), "Maria");
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.getByText("Descartar alterações?")).toBeInTheDocument());
  });

  it("mostra a lista de critérios quando `errors` vem como lista de strings (spec 138, regra 5)", () => {
    // Corpo real de `users/router.py` e `auth/router.py` para a política de senha.
    const problem = new ApiError({
      type: "https://rito.app/errors/validation",
      title: "Dados inválidos",
      status: 422,
      detail: "Senha não atende à política.",
      instance: "/api/v1/invitations/accept",
      errors: ["Mínimo de 8 caracteres.", "Precisa de ao menos um número."],
    });

    render(<Harness onSubmit={vi.fn()} serverError={problem} />);

    expect(screen.getByText("Senha não atende à política.")).toBeInTheDocument();
    expect(screen.getByText("Mínimo de 8 caracteres.")).toBeInTheDocument();
    expect(screen.getByText("Precisa de ao menos um número.")).toBeInTheDocument();
  });

  it("erro de model_validator (loc: ['body']) aparece em vez de sumir", () => {
    // O FastAPI prefixa `loc` com "body"; para uma regra que vale para o objeto inteiro,
    // "body" é tudo o que sobra — e nenhum campo do formulário escuta esse nome.
    const problem = new ApiError({
      type: "https://rito.app/errors/validation",
      title: "Dados inválidos",
      status: 422,
      detail: "Dados inválidos.",
      instance: "/api/v1/users/1",
      errors: [
        { loc: ["body"], msg: "work_end deve ser depois de work_start.", type: "value_error" },
      ],
    });

    render(<Harness onSubmit={vi.fn()} serverError={problem} />);

    expect(screen.getByText("work_end deve ser depois de work_start.")).toBeInTheDocument();
  });

  it("erro com campo continua indo para o campo, sem alerta geral redundante", () => {
    const problem = new ApiError({
      type: "https://rito.app/errors/validation",
      title: "Dados inválidos",
      status: 422,
      detail: "Dados inválidos.",
      instance: "/api/v1/customers",
      errors: [{ loc: ["body", "name"], msg: "Nome já usado.", type: "value_error" }],
    });

    render(<Harness onSubmit={vi.fn()} serverError={problem} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Nome já usado.");
    expect(screen.queryByText("Dados inválidos.")).not.toBeInTheDocument();
  });
});
