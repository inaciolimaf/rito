import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TimelineFilters } from "@/features/lawsuits/TimelineFilters";
import { useTimelineKinds } from "@/features/lawsuits/useTimelineKinds";
import { getMyPreferences, putMyPreferences } from "@/features/users/api";

vi.mock("@/features/users/api", () => ({
  getMyPreferences: vi.fn(),
  putMyPreferences: vi.fn(),
}));

const getPrefsMock = vi.mocked(getMyPreferences);
const putPrefsMock = vi.mocked(putMyPreferences);

function Harness(): JSX.Element {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <FiltersWithHook />
    </QueryClientProvider>
  );
}

function FiltersWithHook(): JSX.Element {
  const { kinds, setKinds, isLoading } = useTimelineKinds();
  if (isLoading) return <p>Carregando…</p>;
  return <TimelineFilters kinds={kinds} onChange={setKinds} />;
}

describe("useTimelineKinds + TimelineFilters", () => {
  it("carrega a seleção persistida e grava cada mudança (regra 7)", async () => {
    getPrefsMock.mockResolvedValue({
      preferences: { lawsuit_timeline_kinds: ["movement_manual"] },
    });
    putPrefsMock.mockResolvedValue({
      preferences: { lawsuit_timeline_kinds: ["movement_manual", "movement_auto"] },
    });
    const user = userEvent.setup();
    render(<Harness />);

    // Estado inicial vem do servidor: só "Movimentação manual" marcado.
    const manual = await screen.findByLabelText("Mostrar Movimentação manual");
    const andamento = screen.getByLabelText("Mostrar Andamento");
    expect(manual).toBeChecked();
    expect(andamento).not.toBeChecked();

    // Ligar um toggle persiste a nova seleção inteira.
    await user.click(andamento);
    await waitFor(() =>
      expect(putPrefsMock).toHaveBeenCalledWith({
        lawsuit_timeline_kinds: ["movement_manual", "movement_auto"],
      }),
    );

    // Desligar também persiste.
    putPrefsMock.mockResolvedValue({ preferences: { lawsuit_timeline_kinds: [] } });
    await user.click(manual);
    await waitFor(() =>
      expect(putPrefsMock).toHaveBeenLastCalledWith({
        lawsuit_timeline_kinds: ["movement_auto"],
      }),
    );
  });

  it("sem preferência gravada, todos os tipos vêm marcados", async () => {
    getPrefsMock.mockResolvedValue({ preferences: {} });
    render(<Harness />);

    expect(await screen.findByLabelText("Mostrar Tarefa")).toBeChecked();
    expect(screen.getByLabelText("Mostrar Publicação")).toBeChecked();
    expect(screen.getByLabelText("Mostrar Financeiro")).toBeChecked();
  });
});
