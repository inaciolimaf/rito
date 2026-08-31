/**
 * Spec 101, Bloco A (§6): `TransferBeforeDeleteDialog` existe desde a 014 e só estava
 * plugado em grupos de ação e tipos de tarefa. Estas quatro telas são o 3º ao 6º uso.
 *
 * O teste é o mesmo para as quatro, porque o fluxo é o mesmo: o DELETE devolve 409
 * ("em uso"), a tela abre a transferência em vez de cuspir o erro, o usuário escolhe o
 * destino, e aí sim a exclusão passa. Um caso por tela, tabelado — o comportamento do
 * hook em si está coberto em `components/domain/useTransferBeforeDelete.test.tsx`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { CustomerOriginsListPage } from "@/features/customer-origins/CustomerOriginsListPage";
import { CostCentersListPage } from "@/features/financial/CostCentersListPage";
import { FinancialCategoriesListPage } from "@/features/financial/FinancialCategoriesListPage";
import { StagesListPage } from "@/features/stages/StagesListPage";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "gestor-1", role: "GESTOR", financialAccess: "FULL" },
  }),
}));

/** Botões da linha da tabela em que o texto aparece. */
function botoesDaLinha(cell: HTMLElement): HTMLElement[] {
  const row = cell.closest("tr");
  return row ? Array.from(row.querySelectorAll("button")) : [];
}

const CENARIOS = [
  {
    nome: "etapas",
    Page: StagesListPage,
    recurso: "stages",
    extra: () => [
      http.get(`${BASE_URL}/api/v1/steps`, () =>
        HttpResponse.json([{ id: 1, name: "Marketing", position: 1 }]),
      ),
    ],
    itens: [
      {
        id: "origem",
        name: "Etapa Origem",
        step_id: 1,
        step_name: "Marketing",
        position: 1,
        enable_stagnant_days: false,
        stagnant_days: null,
        suggested_workflow_id: null,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "destino",
        name: "Etapa Destino",
        step_id: 1,
        step_name: "Marketing",
        position: 2,
        enable_stagnant_days: false,
        stagnant_days: null,
        suggested_workflow_id: null,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    tituloDialogo: /transferir processos antes de excluir/i,
  },
  {
    nome: "origens de contato",
    Page: CustomerOriginsListPage,
    recurso: "customer-origins",
    extra: () => [],
    itens: [
      { id: "origem", name: "Origem Origem", is_active: true, created_at: "2026-01-01T00:00:00Z" },
      {
        id: "destino",
        name: "Origem Destino",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    tituloDialogo: /transferir contatos antes de excluir/i,
  },
  {
    nome: "categorias financeiras",
    Page: FinancialCategoriesListPage,
    recurso: "financial-categories",
    extra: () => [
      http.get(`${BASE_URL}/api/v1/dre-groups`, () =>
        HttpResponse.json([{ id: 1, name: "Receita Bruta", position: 1 }]),
      ),
    ],
    itens: [
      {
        id: "origem",
        name: "Categoria Origem",
        type: "RECEITA",
        dre_group_id: 1,
        dre_group_name: "Receita Bruta",
        is_default: false,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "destino",
        name: "Categoria Destino",
        type: "RECEITA",
        dre_group_id: 1,
        dre_group_name: "Receita Bruta",
        is_default: false,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    tituloDialogo: /transferir lançamentos antes de excluir/i,
  },
  {
    nome: "centros de custo",
    Page: CostCentersListPage,
    recurso: "cost-centers",
    extra: () => [],
    itens: [
      {
        id: "origem",
        name: "Centro Origem",
        is_default: false,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "destino",
        name: "Centro Destino",
        is_default: false,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    tituloDialogo: /transferir lançamentos antes de excluir/i,
  },
];

describe("TransferBeforeDeleteDialog plugado nas 4 telas restantes (spec 101)", () => {
  afterEach(() => server.resetHandlers());

  it.each(CENARIOS)(
    "$nome: 409 no DELETE abre a transferência, e transferir libera a exclusão",
    async ({ Page, recurso, extra, itens, tituloDialogo }) => {
      let deletes = 0;
      let transferiuPara: string | null = null;

      server.use(
        ...extra(),
        http.get(`${BASE_URL}/api/v1/${recurso}`, () =>
          HttpResponse.json({ items: itens, next_cursor: null, total: itens.length }),
        ),
        http.post(`${BASE_URL}/api/v1/${recurso}/transfer`, async ({ request }) => {
          const body = (await request.json()) as { to_id: string };
          transferiuPara = body.to_id;
          return HttpResponse.json({ transferred_count: 1 });
        }),
        http.delete(`${BASE_URL}/api/v1/${recurso}/origem`, () => {
          deletes += 1;
          if (transferiuPara === null) {
            return HttpResponse.json(
              {
                type: "about:blank",
                title: "Conflito",
                status: 409,
                detail: "Tem vínculos — transfira antes de excluir.",
                instance: `/api/v1/${recurso}/origem`,
              },
              { status: 409, headers: { "Content-Type": "application/problem+json" } },
            );
          }
          return new HttpResponse(null, { status: 204 });
        }),
      );

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <Page />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const celula = await screen.findByText(String(itens[0]?.name));
      const excluir = botoesDaLinha(celula).find((botao) =>
        /excluir/i.test(botao.textContent ?? ""),
      );
      if (!excluir) throw new Error("linha sem botão Excluir — a tela não oferece exclusão");
      await userEvent.click(excluir);

      const confirmar = await screen.findAllByRole("button", { name: /excluir/i });
      const ultimo = confirmar.at(-1);
      if (!ultimo) throw new Error("ConfirmDialog não abriu");
      await userEvent.click(ultimo);

      expect(await screen.findByText(tituloDialogo)).toBeInTheDocument();
      await waitFor(() => expect(deletes).toBe(1));

      await userEvent.selectOptions(screen.getByLabelText("Transferir para"), "destino");
      await userEvent.click(screen.getByRole("button", { name: /transferir e excluir/i }));

      await waitFor(() => expect(transferiuPara).toBe("destino"));
      await waitFor(() => expect(deletes).toBe(2));
    },
  );
});
