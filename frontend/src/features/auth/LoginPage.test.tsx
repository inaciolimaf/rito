import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LoginPage } from "@/features/auth/LoginPage";
import { validCredentials } from "@/mocks/handlers";
import { AuthProvider } from "@/providers/AuthProvider";

function renderLoginPage(): void {
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Home autenticada</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  it("login com sucesso redireciona para a rota protegida", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("ID do escritório"), validCredentials.tenantId);
    await user.type(screen.getByLabelText("E-mail"), validCredentials.email);
    await user.type(screen.getByLabelText("Senha"), validCredentials.password);
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    await waitFor(() => expect(screen.getByText("Home autenticada")).toBeInTheDocument());
  });

  it("credencial inválida mostra erro", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("ID do escritório"), validCredentials.tenantId);
    await user.type(screen.getByLabelText("E-mail"), validCredentials.email);
    await user.type(screen.getByLabelText("Senha"), "senha-errada");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha inválidos.");
  });
});
