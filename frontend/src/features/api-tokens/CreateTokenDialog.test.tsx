import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateTokenDialog } from "@/features/api-tokens/CreateTokenDialog";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

const ESCOPOS = [
  { scope: "read:customers", description: "ler customers" },
  { scope: "write:customers", description: "escrever em customers" },
  { scope: "read:lawsuits", description: "ler lawsuits" },
];

function withApi(onCreate?: (body: unknown) => void): void {
  server.use(
    http.get(`${BASE_URL}/api/v1/api-tokens/scopes`, () => HttpResponse.json(ESCOPOS)),
    http.post(`${BASE_URL}/api/v1/api-tokens`, async ({ request }) => {
      onCreate?.(await request.json());
      return HttpResponse.json(
        {
          id: "token-1",
          name: "n8n",
          prefix: "rito_abc",
          scopes: ["read:customers"],
          allowed_ips: [],
          last_used_at: null,
          expires_at: null,
          revoked_at: null,
          is_active: true,
          created_at: "2026-08-28T10:00:00Z",
          token: "rito_abcdefghijklmnop",
        },
        { status: 201 },
      );
    }),
  );
}

function renderDialog(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <CreateTokenDialog onCreated={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("CreateTokenDialog", () => {
  afterEach(() => server.resetHandlers());

  it("o token é exibido uma vez, com o aviso de que não volta (spec 095, regra 1)", async () => {
    withApi();
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText("Nome do token"), "n8n");
    await user.click(await screen.findByLabelText("read:customers"));
    await user.click(screen.getByRole("button", { name: "Gerar token" }));

    const bloco = await screen.findByLabelText("Token gerado");
    expect(bloco).toHaveTextContent("rito_abcdefghijklmnop");
    expect(bloco).toHaveTextContent("não será mostrado de novo");
  });

  it("depois de guardar, o token some da tela e não volta", async () => {
    withApi();
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText("Nome do token"), "n8n");
    await user.click(await screen.findByLabelText("read:customers"));
    await user.click(screen.getByRole("button", { name: "Gerar token" }));
    await user.click(await screen.findByRole("button", { name: "Já guardei" }));

    expect(screen.queryByText("rito_abcdefghijklmnop")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Novo token de API")).toBeInTheDocument();
  });

  it("sem escopo marcado não dá para gerar — token sem escopo não serve para nada", async () => {
    withApi();
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText("Nome do token"), "n8n");

    expect(screen.getByRole("button", { name: "Gerar token" })).toBeDisabled();
  });

  it("envia os escopos marcados, ler e escrever separados", async () => {
    const enviado = vi.fn();
    withApi(enviado);
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText("Nome do token"), "n8n");
    await user.click(await screen.findByLabelText("read:customers"));
    await user.click(screen.getByLabelText("write:customers"));
    await user.click(screen.getByRole("button", { name: "Gerar token" }));

    await waitFor(() =>
      expect(enviado).toHaveBeenCalledWith(
        expect.objectContaining({ scopes: ["read:customers", "write:customers"] }),
      ),
    );
  });
});
