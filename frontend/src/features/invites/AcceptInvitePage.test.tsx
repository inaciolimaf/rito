import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { AcceptInvitePage } from "@/features/invites/AcceptInvitePage";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

function renderPage(query: string): void {
  render(
    <MemoryRouter initialEntries={[`/accept-invite${query}`]}>
      <Routes>
        <Route path="/accept-invite" element={<AcceptInvitePage />} />
        <Route path="/login" element={<p>tela de login</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AcceptInvitePage (spec 102, dívida nº 9)", () => {
  afterEach(() => server.resetHandlers());

  it("envia token, nome e senha e redireciona para o login", async () => {
    let recebido: { corpo: unknown; tenant: string | null } | null = null;
    server.use(
      http.post(`${BASE_URL}/api/v1/invitations/accept`, async ({ request }) => {
        recebido = {
          corpo: await request.json(),
          tenant: request.headers.get("X-Tenant-Id"),
        };
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage("?token=tok-123&tenant=ten-abc");

    await userEvent.type(screen.getByLabelText("Nome"), "Ana Advogada");
    await userEvent.type(screen.getByLabelText("Senha"), "SenhaForte123!");
    await userEvent.click(screen.getByRole("button", { name: "Criar acesso" }));

    await waitFor(() => expect(screen.getByText("tela de login")).toBeInTheDocument());
    expect(recebido).toEqual({
      corpo: { token: "tok-123", name: "Ana Advogada", password: "SenhaForte123!" },
      // O tenant vem do link porque a rota é pré-autenticação e o RLS precisa dele.
      tenant: "ten-abc",
    });
  });

  it("link sem token ou sem tenant não mostra formulário — explica e oferece o login", () => {
    renderPage("?token=tok-123");

    expect(screen.queryByLabelText("Senha")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/incompleto/i);
    expect(screen.getByRole("link", { name: /login/i })).toBeInTheDocument();
  });

  it("convite inválido mostra o erro do backend e não redireciona", async () => {
    server.use(
      http.post(`${BASE_URL}/api/v1/invitations/accept`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Erro",
            status: 400,
            detail: "Convite inválido ou expirado.",
            instance: "/api/v1/invitations/accept",
          },
          { status: 400, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    renderPage("?token=expirado&tenant=ten-abc");

    await userEvent.type(screen.getByLabelText("Nome"), "Ana");
    await userEvent.type(screen.getByLabelText("Senha"), "SenhaForte123!");
    await userEvent.click(screen.getByRole("button", { name: "Criar acesso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Convite inválido ou expirado.");
    expect(screen.queryByText("tela de login")).not.toBeInTheDocument();
  });
});
