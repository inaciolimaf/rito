import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { z } from "zod";

import { CrudListPage } from "@/components/domain/CrudListPage";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const schema = z.object({ name: z.string().min(1, "Nome é obrigatório.") });
type FormValues = z.infer<typeof schema>;

interface Taxonomia {
  id: string;
  name: string;
}

const FILTER_FIELDS: FilterFieldDef[] = [{ key: "q", label: "Buscar", type: "text" }];

const COLUMNS: DataTableColumn<Taxonomia>[] = [
  { id: "name", header: "Nome", cell: (row) => row.name },
];

/** Repositório em memória: o componente não faz fetch (regra 1 da spec 007), então o
 * teste entrega os dados e recebe as chamadas de escrita. */
function Harness({ canWrite = true }: { canWrite?: boolean }): JSX.Element {
  const [items, setItems] = React.useState<Taxonomia[]>([{ id: "1", name: "Cível" }]);

  const crud = useCrudResource<Taxonomia, FormValues>({
    queryKey: ["taxonomias"],
    create: async (values) => {
      const novo = { id: `novo-${items.length}`, name: values.name };
      setItems((atuais) => [...atuais, novo]);
      return novo;
    },
    update: async (item, values) => {
      const atualizado = { ...item, name: values.name };
      setItems((atuais) => atuais.map((i) => (i.id === item.id ? atualizado : i)));
      return atualizado;
    },
    remove: async (item) => {
      setItems((atuais) => atuais.filter((i) => i.id !== item.id));
    },
  });

  return (
    <CrudListPage
      title="Taxonomias"
      createLabel="Nova taxonomia"
      canWrite={canWrite}
      filterFields={FILTER_FIELDS}
      columns={COLUMNS}
      data={items}
      isLoading={false}
      error={null}
      emptyMessage="Nenhuma taxonomia cadastrada ainda."
      crud={crud}
      createTitle="Nova taxonomia"
      editTitle="Editar taxonomia"
      schema={schema}
      emptyFormValues={{ name: "" }}
      toFormValues={(item) => ({ name: item.name })}
      formFields={(form) => (
        <div className="space-y-1">
          <Label htmlFor="taxonomia-name">Nome</Label>
          <Input id="taxonomia-name" {...form.register("name")} />
        </div>
      )}
      confirmTitle="Excluir taxonomia?"
      confirmDescription={(item) => `"${item?.name ?? ""}" será excluída.`}
    />
  );
}

/** O botão de ação da linha em que o texto aparece — mais preciso que indexar
 * `getAllByRole`, e não depende da ordem da tabela. */
function botaoDaLinha(texto: string, nome: string): HTMLElement {
  const linha = screen.getByText(texto).closest("tr");
  if (!linha) throw new Error(`linha de "${texto}" não encontrada`);
  return within(linha).getByRole("button", { name: nome });
}

function renderHarness(props: { canWrite?: boolean } = {}): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/settings/taxonomias"]}>
        <Harness {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CrudListPage", () => {
  it("lista, cria, edita e exclui", async () => {
    const user = userEvent.setup();
    renderHarness();

    expect(screen.getByRole("heading", { name: "Taxonomias" })).toBeInTheDocument();
    expect(screen.getByText("Cível")).toBeInTheDocument();

    // criar
    await user.click(screen.getByRole("button", { name: "Nova taxonomia" }));
    expect(await screen.findByText("Nova taxonomia", { selector: "h2" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nome"), "Trabalhista");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Trabalhista")).toBeInTheDocument();

    // editar a primeira linha
    await user.click(botaoDaLinha("Cível", "Editar"));
    expect(await screen.findByText("Editar taxonomia", { selector: "h2" })).toBeInTheDocument();
    const campo = screen.getByLabelText("Nome");
    await user.clear(campo);
    await user.type(campo, "Cível renomeada");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Cível renomeada")).toBeInTheDocument();

    // excluir a primeira linha, passando pela confirmação
    await user.click(botaoDaLinha("Cível renomeada", "Excluir"));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText('"Cível renomeada" será excluída.')).toBeInTheDocument();
    await user.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(screen.queryByText("Cível renomeada")).not.toBeInTheDocument());
    expect(screen.getByText("Trabalhista")).toBeInTheDocument();
  });

  it("respeita permissão: sem acesso, sem botão de criar nem ações de linha", () => {
    renderHarness({ canWrite: false });

    expect(screen.queryByRole("button", { name: "Nova taxonomia" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Excluir" })).not.toBeInTheDocument();
    expect(screen.getByText("Cível")).toBeInTheDocument();
  });
});
