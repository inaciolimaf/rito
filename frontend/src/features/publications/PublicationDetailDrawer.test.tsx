import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { PublicationDetailDrawer } from "@/features/publications/PublicationDetailDrawer";

const PUBLICATION = {
  id: "pub-1",
  external_id: 1,
  availability_date: "2026-08-10",
  court_code: "TJSP",
  communication_type: "Intimação",
  document_type: null,
  organ_name: "1ª Vara Cível",
  body: "Texto do inteiro teor da publicação de teste.",
  process_number: "12345678920268260100",
  link: null,
  status: null,
  is_active: true,
  cancellation_reason: null,
  cancelled_at: null,
  lawsuit_id: null,
  post_id: null,
  matched_by: null,
  routed_to: null,
  routed_by: null,
  created_at: "2026-08-10T10:00:00Z",
  recipients: [{ name: "Fulano de Tal", pole: "A" }],
  lawyers: [],
  is_read: false,
};

function renderDrawer(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <PublicationDetailDrawer publicationId="pub-1" onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("PublicationDetailDrawer", () => {
  afterEach(() => server.resetHandlers());

  it("abre o inteiro teor sem sair da lista (regra 4)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/publications/pub-1`, () => HttpResponse.json(PUBLICATION)),
      http.post(`${BASE_URL}/api/v1/publications/pub-1/read`, () =>
        HttpResponse.json({ ...PUBLICATION, is_read: true }),
      ),
    );

    renderDrawer();

    expect(
      await screen.findByText("Texto do inteiro teor da publicação de teste."),
    ).toBeInTheDocument();
    expect(screen.getByText("Fulano de Tal")).toBeInTheDocument();
    expect(screen.getByText("12345678920268260100")).toBeInTheDocument();
  });
});
