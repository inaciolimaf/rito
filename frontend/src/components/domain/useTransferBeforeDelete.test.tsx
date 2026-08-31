import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { useTransferBeforeDelete } from "@/components/domain/useTransferBeforeDelete";
import { TransferBeforeDeleteDialog } from "@/components/domain/TransferBeforeDeleteDialog";
import { ApiError } from "@/lib/errors";

interface Item {
  id: string;
  name: string;
}

const EM_USO = new ApiError({
  type: "about:blank",
  title: "Conflito",
  status: 409,
  detail: "Etapa tem processos vinculados — transfira-os antes de excluir.",
  instance: "/api/v1/stages/a",
});

function Harness({
  remove,
  transfer,
  onError,
}: {
  remove: (item: Item) => Promise<void>;
  transfer: (item: Item, destinationId: string) => Promise<void>;
  onError?: (error: unknown) => void;
}): JSX.Element {
  const alvo: Item = { id: "a", name: "Origem" };
  const flow = useTransferBeforeDelete<Item>({ queryKey: ["itens"], remove, transfer });

  return (
    <div>
      <button
        onClick={() => {
          // O erro que não é 409 tem que continuar propagando; aqui só o capturamos
          // para o teste inspecionar, como a tela faria ao exibi-lo.
          flow.requestDelete(alvo).catch((error: unknown) => onError?.(error));
        }}
      >
        Excluir
      </button>
      <TransferBeforeDeleteDialog
        open={flow.dialogOpen}
        onOpenChange={(open) => {
          if (!open) flow.closeDialog();
        }}
        title="Transferir antes de excluir"
        options={[{ id: "b", label: "Destino" }]}
        onTransfer={flow.transferAndDelete}
      />
    </div>
  );
}

function renderHarness(
  remove: (item: Item) => Promise<void>,
  transfer: (item: Item, destinationId: string) => Promise<void>,
  onError?: (error: unknown) => void,
): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <Harness remove={remove} transfer={transfer} onError={onError} />
    </QueryClientProvider>,
  );
}

describe("useTransferBeforeDelete (spec 101, Bloco A)", () => {
  it("exclui direto quando o backend não reclama — sem diálogo de transferência", async () => {
    const remove = vi.fn<(item: Item) => Promise<void>>().mockResolvedValue(undefined);
    const transfer = vi
      .fn<(item: Item, destinationId: string) => Promise<void>>()
      .mockResolvedValue(undefined);
    renderHarness(remove, transfer);

    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Transferir antes de excluir")).not.toBeInTheDocument();
    expect(transfer).not.toHaveBeenCalled();
  });

  it("abre a transferência no 409 e, ao confirmar, transfere e só então exclui", async () => {
    // 1ª tentativa: 409 (em uso). 2ª (depois da transferência): sucesso.
    const remove = vi
      .fn<(item: Item) => Promise<void>>()
      .mockRejectedValueOnce(EM_USO)
      .mockResolvedValueOnce(undefined);
    const transfer = vi
      .fn<(item: Item, destinationId: string) => Promise<void>>()
      .mockResolvedValue(undefined);
    renderHarness(remove, transfer);

    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));

    // O 409 não vira erro na tela: vira o diálogo que resolve o problema.
    expect(await screen.findByText("Transferir antes de excluir")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Transferir para"), "b");
    await userEvent.click(screen.getByRole("button", { name: /transferir/i }));

    await waitFor(() => expect(transfer).toHaveBeenCalledWith({ id: "a", name: "Origem" }, "b"));
    // A ordem importa: transferir e DEPOIS excluir — o inverso violaria a FK.
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
    const ordemTransfer = transfer.mock.invocationCallOrder[0] ?? Number.POSITIVE_INFINITY;
    const ordemSegundoRemove = remove.mock.invocationCallOrder[1] ?? -1;
    expect(ordemTransfer).toBeLessThan(ordemSegundoRemove);
  });

  it("erro que não é 409 continua propagando — não vira diálogo de transferência", async () => {
    const explosao = new ApiError({
      type: "about:blank",
      title: "Erro",
      status: 500,
      detail: "boom",
      instance: "/api/v1/stages/a",
    });
    const remove = vi.fn<(item: Item) => Promise<void>>().mockRejectedValue(explosao);
    const transfer = vi
      .fn<(item: Item, destinationId: string) => Promise<void>>()
      .mockResolvedValue(undefined);
    const capturado = vi.fn();
    renderHarness(remove, transfer, capturado);

    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(capturado).toHaveBeenCalledWith(explosao));
    expect(remove).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Transferir antes de excluir")).not.toBeInTheDocument();
  });
});
