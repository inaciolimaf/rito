import { DataTable } from "@/components/domain/DataTable";
import { Button } from "@/components/ui/button";
import type { DataTableColumn } from "@/components/domain/types";
import type { PartnershipData } from "@/features/partners/api";

const STATUS_LABEL: Record<PartnershipData["status"], string> = {
  PENDENTE: "Pendente",
  ATIVA: "Ativa",
  RECUSADA: "Recusada",
  ENCERRADA: "Encerrada",
};

export interface PartnerNetworkListProps {
  partnerships: PartnershipData[];
  isLoading?: boolean;
  onEnd: (partnership: PartnershipData) => void;
}

/** A rede de parceiros: quem convidou quem, situação e quantos processos estão
 * compartilhados com cada um. */
export function PartnerNetworkList({
  partnerships,
  isLoading = false,
  onEnd,
}: PartnerNetworkListProps): JSX.Element {
  const columns: DataTableColumn<PartnershipData>[] = [
    {
      id: "partner",
      header: "Escritório",
      cell: (row) => row.partner_name ?? row.invited_email,
    },
    {
      id: "origin",
      header: "Origem",
      cell: (row) => (row.is_requester ? "Convite enviado" : "Convite recebido"),
    },
    { id: "status", header: "Situação", cell: (row) => STATUS_LABEL[row.status] },
    { id: "shared", header: "Processos compartilhados", cell: (row) => row.shared_count },
  ];

  return (
    <DataTable
      data={partnerships}
      columns={columns}
      getRowId={(row) => row.id}
      isLoading={isLoading}
      emptyMessage="Nenhum parceiro ainda. Convide um escritório para começar."
      rowActions={(row) =>
        row.status === "ATIVA" || row.status === "PENDENTE" ? (
          <Button type="button" size="sm" variant="ghost" onClick={() => onEnd(row)}>
            Encerrar
          </Button>
        ) : null
      }
    />
  );
}
