import { useQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import { listAiAudit, type AuditEntryData } from "@/features/ai/actions";

const TOOL_LABELS: Record<string, string> = {
  create_customer: "Criou o contato",
  update_customer: "Atualizou o contato",
  create_lawsuit: "Abriu o processo",
  update_lawsuit: "Atualizou o processo",
  move_lawsuit_stage: "Moveu de etapa",
  create_task: "Criou a tarefa",
  complete_task: "Concluiu a tarefa",
  create_transaction: "Lançou no financeiro",
  link_publication: "Vinculou a intimação",
  apply_workflow: "Aplicou o workflow",
};

function changedFields(entry: AuditEntryData): string {
  const after = entry.after_state ?? {};
  return Object.keys(after)
    .filter((key) => key !== "id")
    .join(", ");
}

const COLUMNS: DataTableColumn<AuditEntryData>[] = [
  {
    id: "what",
    header: "O que a IA fez",
    cell: (row) => TOOL_LABELS[row.tool_name] ?? row.tool_name,
  },
  { id: "fields", header: "Campos", cell: (row) => changedFields(row) },
  { id: "model", header: "Modelo", cell: (row) => row.model },
  {
    id: "when",
    header: "Quando",
    cell: (row) => new Date(row.created_at).toLocaleString("pt-BR"),
  },
];

export interface AiAuditTrailProps {
  affectedType: string;
  affectedId: string;
}

/** Histórico do que a IA gravou num registro (spec 084, regra 7). É o que o `AiBadge`
 * abre: quem quiser saber "por que este campo mudou?" tem a resposta aqui. */
export function AiAuditTrail({ affectedType, affectedId }: AiAuditTrailProps): JSX.Element {
  const { data, isLoading } = useQuery({
    queryKey: ["ai-audit", affectedType, affectedId],
    queryFn: () => listAiAudit(affectedType, affectedId),
  });

  return (
    <DataTable
      columns={COLUMNS}
      data={data?.items ?? []}
      getRowId={(row) => row.id}
      isLoading={isLoading}
      emptyMessage="A IA nunca alterou este registro."
    />
  );
}
