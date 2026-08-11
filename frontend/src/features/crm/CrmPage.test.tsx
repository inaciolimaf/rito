import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { CrmPage } from "@/features/crm/CrmPage";
import { listStages } from "@/features/stages/api";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

const BOARD_BODY = {
  columns: [
    {
      step_id: 1,
      step_name: "Marketing",
      total: 1,
      items: [
        {
          id: "lawsuit-1",
          process_number: null,
          folder: null,
          lawsuit_type_name: "Cível",
          stage_id: "stage-a",
          stage_name: "Etapa A",
          case_value: null,
          responsible_id: "user-1",
          responsible_name: "Fulano",
          stage_entered_at: "2026-08-01T00:00:00Z",
          parties: [{ name: "Cliente Teste", pole: "A" }],
          parties_total: 1,
        },
      ],
    },
    { step_id: 2, step_name: "Negociação", total: 0, items: [] },
  ],
  total: 1,
  suggest_refine_filters: false,
};

const STAGES_BODY = {
  items: [
    {
      id: "stage-b",
      name: "Etapa B",
      step_id: 2,
      step_name: "Negociação",
      position: 0,
      enable_stagnant_days: false,
      stagnant_days: null,
      suggested_workflow_id: null,
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  next_cursor: null,
  total: 1,
};

async function renderPage(): Promise<void> {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // Pré-aquece o cache de etapas com a MESMA chave que o CrmPage usa — resolver
  // "primeira etapa da fase destino" (regra 3) não pode ficar numa corrida com o
  // fetch inicial da tela num teste; isolar essa query evita depender de timing.
  await queryClient.prefetchQuery({
    queryKey: ["stages", "all-for-crm"],
    queryFn: () => listStages({}),
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/crm"]}>
        <CrmPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CrmPage", () => {
  afterEach(() => server.resetHandlers());

  it("falha da API ao mover reverte a UI pro estado do servidor", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/crm/board`, () => HttpResponse.json(BOARD_BODY)),
      http.get(`${BASE_URL}/api/v1/stages`, () => HttpResponse.json(STAGES_BODY)),
      http.post(`${BASE_URL}/api/v1/lawsuits/lawsuit-1/move-stage`, async () => {
        // Atraso de propósito: sem ele, o revert (onError → invalida → refetch) resolve
        // antes do teste conseguir observar o estado otimista intermediário.
        await delay(80);
        return HttpResponse.json({ detail: "erro simulado" }, { status: 500 });
      }),
    );

    await renderPage();

    const card = await screen.findByTestId("kanban-card-lawsuit-1");
    const marketingColumn = screen.getByTestId("kanban-column-1");
    const negotiationColumn = screen.getByTestId("kanban-column-2");
    expect(marketingColumn.contains(card)).toBe(true);

    fireEvent.dragStart(card);
    fireEvent.dragOver(negotiationColumn);
    fireEvent.drop(negotiationColumn);

    // Otimista: sai de Marketing na hora, mesmo antes da resposta do servidor.
    await waitFor(() => {
      expect(negotiationColumn.contains(screen.getByTestId("kanban-card-lawsuit-1"))).toBe(true);
    });

    // A API falhou (500) → onError invalida e busca o board de novo; como o servidor
    // nunca mudou (a chamada de move-stage falhou), o card volta pra Marketing.
    await waitFor(() => {
      expect(marketingColumn.contains(screen.getByTestId("kanban-card-lawsuit-1"))).toBe(true);
    });
  });
});
