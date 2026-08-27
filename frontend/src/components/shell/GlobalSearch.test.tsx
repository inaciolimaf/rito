import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { GlobalSearch } from "@/components/shell/GlobalSearch";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

const RESULTADO = {
  people: {
    items: [{ id: "customer-1", label: "Ana Souza", sublabel: "11144477735", extra: {} }],
    total: 42,
  },
  lawsuits: { items: [], total: 0 },
  tasks: { items: [], total: 0 },
  took_ms: 12,
  query_kind: "full_text",
  recent: [],
};

function withSearch(onSearch?: (query: string) => void): void {
  server.use(
    http.get(`${BASE_URL}/api/v1/search`, ({ request }) => {
      const query = new URL(request.url).searchParams.get("q") ?? "";
      onSearch?.(query);
      if (query.trim().length < 2) {
        return HttpResponse.json({
          ...RESULTADO,
          people: { items: [], total: 0 },
          query_kind: "too_short",
          recent: ["marina duarte"],
        });
      }
      return HttpResponse.json(RESULTADO);
    }),
    http.post(`${BASE_URL}/api/v1/search/click`, () => new HttpResponse(null, { status: 204 })),
  );
}

function renderGlobalSearch(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <input aria-label="Outro campo" />
        <GlobalSearch />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GlobalSearch", () => {
  afterEach(() => server.resetHandlers());

  it("'/' foca a busca quando o foco não está num campo de texto", async () => {
    withSearch();
    const user = userEvent.setup();
    renderGlobalSearch();

    document.body.focus();
    await user.keyboard("/");

    expect(screen.getByRole("combobox")).toHaveFocus();
  });

  it("'/' não interfere quando o foco já está num campo de texto", async () => {
    withSearch();
    const user = userEvent.setup();
    renderGlobalSearch();

    await user.click(screen.getByLabelText("Outro campo"));
    await user.keyboard("/");

    expect(screen.getByLabelText("Outro campo")).toHaveFocus();
    expect(screen.getByLabelText("Outro campo")).toHaveValue("/");
  });

  it("navega pelos resultados com as setas e abre com Enter", async () => {
    withSearch();
    const user = userEvent.setup();
    renderGlobalSearch();

    const input = screen.getByRole("combobox");
    await user.click(input);
    await user.type(input, "ana");

    const option = await screen.findByRole("option", { name: /Ana Souza/ });
    await user.keyboard("{ArrowDown}");
    expect(option).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Enter}");
    expect(input).toHaveValue("");
  });

  it("não dispara uma consulta por tecla digitada (spec 096, regra 7)", async () => {
    const buscas: string[] = [];
    withSearch((query) => buscas.push(query));
    const user = userEvent.setup();
    renderGlobalSearch();

    const input = screen.getByRole("combobox");
    await user.click(input);
    await user.type(input, "marina");

    await waitFor(() => expect(buscas).toContain("marina"));
    // Sem debounce seriam seis consultas ("m", "ma", "mar", …). O tempo exato é do
    // `useDebounced`, testado em unidade; aqui o que importa é que a tela não pergunta
    // ao servidor a cada tecla.
    const parciais = buscas.filter((item) => item.length >= 2 && item !== "marina");
    expect(parciais.length).toBeLessThanOrEqual(2);
  });

  it("destaca o termo buscado no resultado (spec 096 §6)", async () => {
    withSearch();
    const user = userEvent.setup();
    renderGlobalSearch();

    const input = screen.getByRole("combobox");
    await user.click(input);
    await user.type(input, "ana");

    const option = await screen.findByRole("option", { name: /Ana Souza/ });
    const marcado = option.querySelector("mark");
    expect(marcado).not.toBeNull();
    expect(marcado?.textContent).toBe("Ana");
  });

  it("mostra o total quando há mais resultados do que cabem na lista (regra 5)", async () => {
    withSearch();
    const user = userEvent.setup();
    renderGlobalSearch();

    const input = screen.getByRole("combobox");
    await user.click(input);
    await user.type(input, "ana");

    expect(await screen.findByText("42 no total")).toBeInTheDocument();
  });

  it("com menos de dois caracteres mostra as buscas recentes (regras 1 e 12)", async () => {
    withSearch();
    const user = userEvent.setup();
    renderGlobalSearch();

    await user.click(screen.getByRole("combobox"));

    expect(await screen.findByLabelText("Buscas recentes")).toHaveTextContent("marina duarte");
  });
});
