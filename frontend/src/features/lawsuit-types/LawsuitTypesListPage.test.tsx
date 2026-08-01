import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { LawsuitTypesListPage } from "@/features/lawsuit-types/LawsuitTypesListPage";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "gestor-1", role: "GESTOR" } }),
}));

const GROUPS = [
  {
    id: "group-civel",
    name: "Cível",
    publications_user_id: null,
    is_active: true,
    lawsuit_types_count: 1,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "group-trabalhista",
    name: "Trabalhista",
    publications_user_id: null,
    is_active: true,
    lawsuit_types_count: 1,
    created_at: "2026-01-01T00:00:00Z",
  },
];

const TYPES = [
  {
    id: "type-1",
    name: "Reintegração de Posse",
    action_group_id: "group-civel",
    action_group_name: "Cível",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "type-2",
    name: "Reclamatória Trabalhista",
    action_group_id: "group-trabalhista",
    action_group_name: "Trabalhista",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  },
];

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/settings/lawsuit-types"]}>
        <LawsuitTypesListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LawsuitTypesListPage", () => {
  afterEach(() => server.resetHandlers());

  it("seleção de tipo filtra pelo grupo", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/action-groups`, () =>
        HttpResponse.json({ items: GROUPS, next_cursor: null, total: GROUPS.length }),
      ),
      http.get(`${BASE_URL}/api/v1/lawsuit-types`, ({ request }) => {
        const url = new URL(request.url);
        const groupId = url.searchParams.get("group_id");

        let items = TYPES;
        if (groupId) items = items.filter((item) => item.action_group_id === groupId);

        return HttpResponse.json({ items, next_cursor: null, total: items.length });
      }),
    );

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Reintegração de Posse")).toBeInTheDocument();
    expect(screen.getByText("Reclamatória Trabalhista")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("option", { name: "Cível" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Grupo de ação"), "group-civel");

    await waitFor(() =>
      expect(screen.queryByText("Reclamatória Trabalhista")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Reintegração de Posse")).toBeInTheDocument();
  });
});
