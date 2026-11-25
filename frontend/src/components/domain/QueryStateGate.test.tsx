import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QueryStateGate } from "@/components/domain/QueryStateGate";
import { ApiError } from "@/lib/errors";

function problem(status: number, detail = "Falhou."): ApiError {
  return new ApiError({
    type: "about:blank",
    title: "Erro",
    status,
    detail,
    instance: "/api/v1/lawsuits/1",
  });
}

describe("QueryStateGate (spec 138, regras 4 e 9)", () => {
  it("com erro, mostra o erro — e NÃO o carregando (o bug do spinner eterno)", () => {
    // Com a API falhando, o TanStack Query deixa `isLoading: false` e `data: undefined`.
    // O padrão antigo (`isLoading || !data`) caía no ramo de carregando e ficava lá.
    render(
      <QueryStateGate
        isLoading={false}
        error={problem(500, "Erro interno.")}
        data={undefined}
        loadingLabel="Carregando processo…"
      >
        {() => <p>Processo</p>}
      </QueryStateGate>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível carregar.");
    expect(screen.queryByText("Carregando processo…")).not.toBeInTheDocument();
  });

  it("403 diz que é permissão e não oferece 'tentar de novo'", async () => {
    render(
      <QueryStateGate isLoading={false} error={problem(403)} data={undefined} onRetry={vi.fn()}>
        {() => <p>Processo</p>}
      </QueryStateGate>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Você não tem acesso a esta área.");
    // Tentar de novo daria 403 de novo: oferecer o botão seria mentir sobre a saída.
    expect(screen.queryByRole("button", { name: "Tentar de novo" })).not.toBeInTheDocument();
  });

  it("404 tem nome próprio", () => {
    render(
      <QueryStateGate isLoading={false} error={problem(404)} data={undefined}>
        {() => <p>Processo</p>}
      </QueryStateGate>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Não encontramos este registro.");
  });

  it("erro de servidor oferece tentar de novo, e o clique chama o refetch", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <QueryStateGate isLoading={false} error={problem(500)} data={undefined} onRetry={onRetry}>
        {() => <p>Processo</p>}
      </QueryStateGate>,
    );

    await user.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("carregando enquanto carrega, conteúdo quando há dado", () => {
    const { rerender } = render(
      <QueryStateGate isLoading error={null} data={undefined} loadingLabel="Carregando tarefa…">
        {() => <p>Tarefa</p>}
      </QueryStateGate>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Carregando tarefa…");

    rerender(
      <QueryStateGate isLoading={false} error={null} data={{ id: "1" }}>
        {(data) => <p>Tarefa {data.id}</p>}
      </QueryStateGate>,
    );
    expect(screen.getByText("Tarefa 1")).toBeInTheDocument();
  });

  it("sem erro e sem dado mostra o vazio, nunca o carregando", () => {
    render(
      <QueryStateGate isLoading={false} error={null} data={null}>
        {() => <p>Nunca</p>}
      </QueryStateGate>,
    );

    expect(screen.getByText("Nada para mostrar.")).toBeInTheDocument();
    expect(screen.queryByText("Nunca")).not.toBeInTheDocument();
  });
});
