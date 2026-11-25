import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setSession } from "@/lib/api";
import { validCredentials } from "@/mocks/handlers";
import { AuthProvider, useAuth } from "@/providers/AuthProvider";

/** Réplica da forma de chave do `useListPage`: a listagem de um escritório. */
function ListaDeClientes({ tenant }: { tenant: string }): JSX.Element {
  const { data } = useQuery({
    queryKey: ["customers-list", "escritorio-a", {}, undefined],
    queryFn: () => Promise.resolve([`cliente do tenant ${tenant}`]),
  });
  return <p>{data?.[0] ?? "carregando"}</p>;
}

function BotaoSair(): JSX.Element {
  const { logout } = useAuth();
  return (
    <button type="button" onClick={() => void logout()}>
      Sair
    </button>
  );
}

describe("AuthProvider e o cache do React Query (spec 138, regra 3)", () => {
  it("logout limpa o cache — o próximo login não vê o dado do escritório anterior", async () => {
    const user = userEvent.setup();
    // Um QueryClient só, como o singleton de módulo do App.tsx.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
    });
    setSession({ accessToken: "a", refreshToken: "r", tenantId: validCredentials.tenantId });

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ListaDeClientes tenant="A" />
          <BotaoSair />
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("cliente do tenant A")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sair" }));
    await waitFor(() => expect(queryClient.getQueryCache().getAll()).toHaveLength(0));

    // Segundo login na mesma aba (logout e login são client-side: não há reload que
    // limpe a memória). O primeiro paint já é do escritório novo.
    rerender(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ListaDeClientes tenant="B" />
          <BotaoSair />
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByText("cliente do tenant A")).not.toBeInTheDocument();
    expect(await screen.findByText("cliente do tenant B")).toBeInTheDocument();
  });
});
