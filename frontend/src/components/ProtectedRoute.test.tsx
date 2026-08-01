import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AuthProvider } from "@/providers/AuthProvider";

function LoginProbe(): JSX.Element {
  const [params] = useSearchParams();
  return <div>Login com next={params.get("next")}</div>;
}

describe("ProtectedRoute", () => {
  it("redireciona para /login preservando o destino em next", async () => {
    render(
      <MemoryRouter initialEntries={["/relatorios"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginProbe />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/relatorios" element={<div>Relatórios</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("Login com next=/relatorios")).toBeInTheDocument());
  });
});
