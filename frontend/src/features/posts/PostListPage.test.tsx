import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { PostListPage } from "@/features/posts/PostListPage";

const perfil = vi.hoisted(() => ({ role: "GESTOR" as string }));

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", role: perfil.role } }),
}));

const ATIVIDADES = [
  {
    id: "p1",
    lawsuit_id: "l1",
    task_type_name: "Análise do caso",
    process_number: "0001234-55.2026.8.26.0100",
    folder: null,
    scheduled_date: "2026-09-10",
    scheduled_time: null,
    deadline_date: "2026-09-15",
    is_important: false,
    is_urgent: true,
    is_private: false,
    status: "PENDENTE",
    assignee_names: ["Ana Lima"],
    assignees_total: 1,
    created_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "p2",
    lawsuit_id: "l2",
    task_type_name: "Protocolar petição",
    process_number: null,
    folder: "PASTA-9",
    scheduled_date: null,
    scheduled_time: null,
    deadline_date: null,
    is_important: false,
    is_urgent: false,
    is_private: false,
    status: "ATRASADA",
    assignee_names: [],
    assignees_total: 0,
    created_at: "2026-09-02T00:00:00Z",
  },
];

function baseHandlers() {
  return [
    http.get(`${BASE_URL}/api/v1/task-types`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(`${BASE_URL}/api/v1/users`, () =>
      HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
    ),
  ];
}

function renderPage(initialEntry = "/posts"): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <PostListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PostListPage", () => {
  afterEach(() => {
    perfil.role = "GESTOR";
    server.resetHandlers();
  });

  it("mostra as colunas da atividade, com data brasileira e status", async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/posts`, () =>
        HttpResponse.json({ items: ATIVIDADES, next_cursor: null, total: 2 }),
      ),
    );

    renderPage();

    const linha = (await screen.findByText("Análise do caso")).closest("tr");
    expect(linha).toHaveTextContent("0001234-55.2026.8.26.0100");
    expect(linha).toHaveTextContent("Ana Lima");
    // CLAUDE.md §9: ISO na API, DD/MM/AAAA na UI.
    expect(linha).toHaveTextContent("10/09/2026");
    expect(linha).toHaveTextContent("15/09/2026");
    expect(linha).toHaveTextContent("Pendente");

    // Sem número, mostra a pasta; sem responsável e sem data, o travessão.
    const semNumero = screen.getByText("PASTA-9").closest("tr");
    expect(semNumero).toHaveTextContent("Atrasada");
    expect(semNumero).toHaveTextContent("—");
  });

  it("filtro vai para a URL, chega ao backend e volta ao recarregar", async () => {
    const vistos: string[] = [];
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/posts`, ({ request }) => {
        const url = new URL(request.url);
        vistos.push(url.searchParams.get("view") ?? "");
        const items = url.searchParams.get("view") === "overdue" ? [ATIVIDADES[1]] : ATIVIDADES;
        return HttpResponse.json({ items, next_cursor: null, total: items.length });
      }),
    );

    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("Análise do caso")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Situação"), "overdue");

    await waitFor(() => expect(vistos).toContain("overdue"));
    await waitFor(() => expect(screen.queryByText("Análise do caso")).not.toBeInTheDocument());

    // Chegar direto na URL com o filtro aplicado restaura o valor selecionado.
    renderPage("/posts?view=overdue");
    await waitFor(() => expect(screen.getByLabelText("Situação")).toHaveValue("overdue"));
  });

  it("paginação avança pelo cursor e volta", async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/posts`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        return cursor
          ? HttpResponse.json({ items: [ATIVIDADES[1]], next_cursor: null, total: 2 })
          : HttpResponse.json({ items: [ATIVIDADES[0]], next_cursor: "cursor-2", total: 2 });
      }),
    );

    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("Análise do caso")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /pró|próxima|next/i }));
    expect(await screen.findByText("Protocolar petição")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /anterior|previous/i }));
    expect(await screen.findByText("Análise do caso")).toBeInTheDocument();
  });

  it("estado vazio sem filtro e ação em massa escondida do colaborador", async () => {
    server.use(
      ...baseHandlers(),
      http.get(`${BASE_URL}/api/v1/posts`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
    );

    renderPage();

    const vazio = await screen.findByRole("status");
    expect(within(vazio).getByText("Nenhuma atividade pendente")).toBeInTheDocument();

    // Regra 9 da 033: concluir a linha de outro é do ADMINISTRADOR para cima.
    perfil.role = "COLABORADOR";
    server.use(
      http.get(`${BASE_URL}/api/v1/posts`, () =>
        HttpResponse.json({ items: ATIVIDADES, next_cursor: null, total: 2 }),
      ),
    );
    renderPage();
    expect(await screen.findByText("Análise do caso")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Concluir selecionadas" })).not.toBeInTheDocument();
  });
});
