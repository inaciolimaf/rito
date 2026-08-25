import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ShareLawsuitDialog } from "@/features/partners/ShareLawsuitDialog";
import type { PartnershipData } from "@/features/partners/api";

const PARTNERSHIP: PartnershipData = {
  id: "partnership-1",
  status: "ATIVA",
  invited_email: "banca@example.com",
  partner_tenant_id: "tenant-2",
  partner_name: "Banca Parceira",
  is_requester: true,
  shared_count: 0,
  accepted_at: "2026-08-20T12:00:00Z",
  created_at: "2026-08-19T12:00:00Z",
};

describe("ShareLawsuitDialog", () => {
  it("mostra o escopo do compartilhamento antes de confirmar (spec 079, regra 4)", async () => {
    const onShare = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <ShareLawsuitDialog
        open
        onOpenChange={() => undefined}
        partnerships={[PARTNERSHIP]}
        lawsuitLabel="0000001-11.2026.8.26.0100"
        onShare={onShare}
      />,
    );

    const scope = screen.getByTestId("share-scope");
    expect(scope).toHaveTextContent("Dados deste processo, partes e timeline");
    expect(scope).toHaveTextContent("Seus outros processos e sua carteira de contatos");
    expect(scope).toHaveTextContent("Financeiro, configurações, relatórios e BI do escritório");

    // Regra 9: o financeiro só abre por marcação explícita — nasce desmarcado.
    expect(screen.getByRole("checkbox", { name: "Ver valores do processo" })).not.toBeChecked();

    await user.selectOptions(screen.getByLabelText("Parceiro"), "partnership-1");
    await user.click(screen.getByRole("button", { name: "Compartilhar" }));

    expect(onShare).toHaveBeenCalledWith({
      partnership_id: "partnership-1",
      can_view_financial: false,
      can_create_tasks: true,
    });
  });
});
