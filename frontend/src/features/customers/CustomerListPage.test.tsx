import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { CustomerListPage } from "@/features/customers/CustomerListPage";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "gestor-1", role: "GESTOR" } }),
}));

const EMPTY_STATS = {
  total: 0,
  variation_vs_last_month: 0,
  with_active_lawsuit: 0,
  without_active_lawsuit: 0,
  top_origins: [],
  age_ranges: [],
  top_occupations: [],
};

const CUSTOMERS = [
  {
    id: "c1",
    type: "PF",
    name: "Maria Silva",
    cellphone: "11999998888",
    whatsapp_link: "https://wa.me/5511999998888",
    city: "São Paulo",
    birthdate: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "c2",
    type: "PF",
    name: "João Souza",
    cellphone: null,
    whatsapp_link: null,
    city: "Rio de Janeiro",
    birthdate: null,
    is_archived: false,
    created_at: "2026-01-02T00:00:00Z",
  },
];

function baseHandlers() {
  return [
    http.get(`${BASE_URL}/api/v1/states`, () => HttpResponse.json([])),
    http.get(`${BASE_URL}/api/v1/customer-origins`, () =>
      HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
    ),
    http.get(`${BASE_URL}/api/v1/marital-statuses`, () => HttpResponse.json([])),
    http.get(`${BASE_URL}/api/v1/customers/stats`, () => HttpResponse.json(EMPTY_STATS)),
  ];
}

function renderPage(initialEntry = "/customers"): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <CustomerListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CustomerListPage", () => {
  afterEach(() => server.resetHandlers());

  it("filtros refletem na URL e voltam", async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/customers`, ({ request }) => {
        const url = new URL(request.url);
        const type = url.searchParams.get("type");
        let items = CUSTOMERS;
        if (type) items = items.filter((item) => item.type === type);
        return HttpResponse.json({ items, next_cursor: null, total: items.length });
      }),
    );

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Maria Silva")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "PF");

    // useSearchParams usa o history do MemoryRouter, não window.location; o valor
    // persistido é verificado lendo o próprio input (mesmo padrão de FilterBar.test.tsx).
    await waitFor(() => expect(screen.getByLabelText("Tipo")).toHaveValue("PF"));

    // Chegar direto numa URL com o filtro já aplicado restaura o valor selecionado.
    renderPage("/customers?type=PF");
    await waitFor(() => expect(screen.getByLabelText("Tipo")).toHaveValue("PF"));
  });

  it("estado vazio com ação de criar", async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/customers`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
    );

    renderPage();

    expect(await screen.findByText("Nenhum contato cadastrado ainda")).toBeInTheDocument();
    // O EmptyState tem seu próprio botão "Novo contato", distinto do botão do cabeçalho.
    const emptyState = screen.getByRole("status");
    expect(within(emptyState).getByRole("button", { name: "Novo contato" })).toBeInTheDocument();
  });

  it("link de WhatsApp bem formado", async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/customers`, () =>
        HttpResponse.json({ items: CUSTOMERS, next_cursor: null, total: CUSTOMERS.length }),
      ),
    );

    renderPage();

    const link = await screen.findByRole("link", { name: "11999998888" });
    expect(link).toHaveAttribute("href", "https://wa.me/5511999998888");
    expect(screen.getByText("João Souza").closest("tr")).toHaveTextContent("—");
  });
});
