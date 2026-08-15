import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import type {
  AccessLogTableRow,
  ContraryPartyTableRow,
  DelayedTaskTableRow,
  HearingTableRow,
  LawsuitOutcomeTableRow,
  NewCustomerTableRow,
  NewLawsuitTableRow,
  ProductivityTableRow,
  ReportKey,
} from "@/features/reports/api";
import { formatBrl } from "@/lib/money";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR");
}

const COMMON_FILTER_FIELDS: FilterFieldDef[] = [
  { key: "from", label: "De", type: "date" },
  { key: "to", label: "Até", type: "date" },
];

/** Definição de metadados de um relatório (spec 072 regra 1): colunas, filtros extras
 * e se mostra o rodapé de soma de pontos — a página genérica só sabe ler daqui, nunca
 * hardcoda por relatório. `columns` usa `any` propositalmente: é o único ponto do app
 * onde o shape da linha varia por chave em tempo de execução (dicionário heterogêneo),
 * o restante do código permanece tipado por relatório via `ReportTableRow`. */
export interface ReportDefinition {
  key: ReportKey;
  label: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: DataTableColumn<any>[];
  extraFilterFields: FilterFieldDef[];
  showPointsTotal: boolean;
  emptyMessage: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  rowId: (row: any) => string;
}

export const REPORT_DEFINITIONS: Record<ReportKey, ReportDefinition> = {
  productivity: {
    key: "productivity",
    rowId: (row: ProductivityTableRow) => row.post_id,
    label: "Produtividade",
    columns: [
      {
        id: "responsible_name",
        header: "Responsável",
        cell: (row: ProductivityTableRow) => row.responsible_name,
      },
      {
        id: "customer_name",
        header: "Cliente",
        cell: (row: ProductivityTableRow) => row.customer_name ?? "—",
      },
      {
        id: "task_type_name",
        header: "Tarefa",
        cell: (row: ProductivityTableRow) => row.task_type_name,
      },
      { id: "points", header: "Pontuação", cell: (row: ProductivityTableRow) => row.points },
      {
        id: "scheduled_date",
        header: "Data compromisso",
        cell: (row: ProductivityTableRow) => formatDate(row.scheduled_date),
      },
      {
        id: "completed_at",
        header: "Conclusão",
        cell: (row: ProductivityTableRow) => formatDateTime(row.completed_at),
      },
    ],
    extraFilterFields: [],
    showPointsTotal: true,
    emptyMessage: "Nenhuma tarefa no período.",
  },
  delayed_tasks: {
    key: "delayed_tasks",
    rowId: (row: DelayedTaskTableRow) => row.post_id,
    label: "Tarefas atrasadas",
    columns: [
      {
        id: "responsible_name",
        header: "Responsável",
        cell: (row: DelayedTaskTableRow) => row.responsible_name,
      },
      {
        id: "customer_name",
        header: "Cliente",
        cell: (row: DelayedTaskTableRow) => row.customer_name ?? "—",
      },
      {
        id: "task_type_name",
        header: "Tarefa",
        cell: (row: DelayedTaskTableRow) => row.task_type_name,
      },
      { id: "points", header: "Pontuação", cell: (row: DelayedTaskTableRow) => row.points },
      {
        id: "scheduled_date",
        header: "Data compromisso",
        cell: (row: DelayedTaskTableRow) => formatDate(row.scheduled_date),
      },
      {
        id: "delay_days",
        header: "Atraso",
        cell: (row: DelayedTaskTableRow) => `${row.delay_days} dia(s)`,
      },
    ],
    extraFilterFields: [],
    showPointsTotal: true,
    emptyMessage: "Nenhuma tarefa atrasada no período.",
  },
  access_logs: {
    key: "access_logs",
    rowId: (row: AccessLogTableRow) => `${row.user_id}-${row.day}`,
    label: "Registros de acesso",
    columns: [
      { id: "user_name", header: "Colaborador", cell: (row: AccessLogTableRow) => row.user_name },
      { id: "day", header: "Data", cell: (row: AccessLogTableRow) => formatDate(row.day) },
      { id: "ip_address", header: "IP", cell: (row: AccessLogTableRow) => row.ip_address ?? "—" },
      {
        id: "first_login",
        header: "Primeiro login",
        cell: (row: AccessLogTableRow) => formatDateTime(row.first_login),
      },
      {
        id: "last_login",
        header: "Último login",
        cell: (row: AccessLogTableRow) => formatDateTime(row.last_login),
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhum registro de acesso.",
  },
  new_customers: {
    key: "new_customers",
    rowId: (row: NewCustomerTableRow) => row.customer_id,
    label: "Novos clientes",
    columns: [
      { id: "name", header: "Nome", cell: (row: NewCustomerTableRow) => row.name },
      { id: "contact", header: "Contato", cell: (row: NewCustomerTableRow) => row.contact ?? "—" },
      {
        id: "city_state",
        header: "Cidade/UF",
        cell: (row: NewCustomerTableRow) => row.city_state ?? "—",
      },
      {
        id: "origin_name",
        header: "Origem",
        cell: (row: NewCustomerTableRow) => row.origin_name ?? "—",
      },
      {
        id: "created_at",
        header: "Data",
        cell: (row: NewCustomerTableRow) => formatDateTime(row.created_at),
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhum cliente novo no período.",
  },
  new_lawsuits: {
    key: "new_lawsuits",
    rowId: (row: NewLawsuitTableRow) => row.lawsuit_id,
    label: "Novos processos",
    columns: [
      { id: "parties", header: "Partes", cell: (row: NewLawsuitTableRow) => row.parties },
      {
        id: "lawsuit_type_name",
        header: "Tipo de ação",
        cell: (row: NewLawsuitTableRow) => row.lawsuit_type_name,
      },
      {
        id: "process_number",
        header: "Número",
        cell: (row: NewLawsuitTableRow) => row.process_number ?? "—",
      },
      {
        id: "responsible_name",
        header: "Responsável",
        cell: (row: NewLawsuitTableRow) => row.responsible_name,
      },
      {
        id: "created_at",
        header: "Data",
        cell: (row: NewLawsuitTableRow) => formatDateTime(row.created_at),
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhum processo novo no período.",
  },
  won_lawsuits: {
    key: "won_lawsuits",
    rowId: (row: LawsuitOutcomeTableRow) => row.lawsuit_id,
    label: "Processos ganhos",
    columns: [
      { id: "parties", header: "Partes", cell: (row: LawsuitOutcomeTableRow) => row.parties },
      {
        id: "lawsuit_type_name",
        header: "Tipo",
        cell: (row: LawsuitOutcomeTableRow) => row.lawsuit_type_name,
      },
      {
        id: "process_number",
        header: "Número",
        cell: (row: LawsuitOutcomeTableRow) => row.process_number ?? "—",
      },
      {
        id: "fees_value",
        header: "Honorários",
        cell: (row: LawsuitOutcomeTableRow) =>
          row.fees_value === null ? "—" : formatBrl(Number(row.fees_value)),
      },
      {
        id: "closure_date",
        header: "Fechamento",
        cell: (row: LawsuitOutcomeTableRow) => formatDate(row.closure_date),
      },
      {
        id: "total_days",
        header: "Tempo total",
        cell: (row: LawsuitOutcomeTableRow) => `${row.total_days} dia(s)`,
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhum processo ganho no período.",
  },
  lost_lawsuits: {
    key: "lost_lawsuits",
    rowId: (row: LawsuitOutcomeTableRow) => row.lawsuit_id,
    label: "Processos perdidos",
    columns: [
      { id: "parties", header: "Partes", cell: (row: LawsuitOutcomeTableRow) => row.parties },
      {
        id: "lawsuit_type_name",
        header: "Tipo",
        cell: (row: LawsuitOutcomeTableRow) => row.lawsuit_type_name,
      },
      {
        id: "process_number",
        header: "Número",
        cell: (row: LawsuitOutcomeTableRow) => row.process_number ?? "—",
      },
      {
        id: "fees_value",
        header: "Honorários",
        cell: (row: LawsuitOutcomeTableRow) =>
          row.fees_value === null ? "—" : formatBrl(Number(row.fees_value)),
      },
      {
        id: "closure_date",
        header: "Fechamento",
        cell: (row: LawsuitOutcomeTableRow) => formatDate(row.closure_date),
      },
      {
        id: "total_days",
        header: "Tempo total",
        cell: (row: LawsuitOutcomeTableRow) => `${row.total_days} dia(s)`,
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhum processo perdido no período.",
  },
  hearings: {
    key: "hearings",
    rowId: (row: HearingTableRow) => row.post_id,
    label: "Pauta de audiências",
    columns: [
      {
        id: "scheduled_date",
        header: "Data",
        cell: (row: HearingTableRow) => formatDate(row.scheduled_date),
      },
      {
        id: "scheduled_time",
        header: "Hora",
        cell: (row: HearingTableRow) => row.scheduled_time ?? "—",
      },
      { id: "task_type_name", header: "Tipo", cell: (row: HearingTableRow) => row.task_type_name },
      {
        id: "process_number",
        header: "Processo",
        cell: (row: HearingTableRow) => row.process_number ?? "—",
      },
      { id: "parties", header: "Partes", cell: (row: HearingTableRow) => row.parties },
      { id: "location", header: "Local", cell: (row: HearingTableRow) => row.location ?? "—" },
      {
        id: "responsible_name",
        header: "Advogado",
        cell: (row: HearingTableRow) => row.responsible_name ?? "—",
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhuma audiência futura na pauta.",
  },
  contrary_parties: {
    key: "contrary_parties",
    rowId: (row: ContraryPartyTableRow) => row.customer_id,
    label: "Partes contrárias",
    columns: [
      { id: "name", header: "Nome", cell: (row: ContraryPartyTableRow) => row.name },
      {
        id: "identification",
        header: "Documento",
        cell: (row: ContraryPartyTableRow) => row.identification ?? "—",
      },
      { id: "city", header: "Cidade", cell: (row: ContraryPartyTableRow) => row.city ?? "—" },
      {
        id: "lawsuit_count",
        header: "Nº de processos",
        cell: (row: ContraryPartyTableRow) => row.lawsuit_count,
      },
    ],
    extraFilterFields: [],
    showPointsTotal: false,
    emptyMessage: "Nenhuma parte contrária cadastrada.",
  },
};

export const REPORT_OPTIONS: { value: ReportKey; label: string }[] = (
  Object.values(REPORT_DEFINITIONS) as ReportDefinition[]
).map((definition) => ({ value: definition.key, label: definition.label }));

export function filterFieldsFor(definition: ReportDefinition): FilterFieldDef[] {
  return [...COMMON_FILTER_FIELDS, ...definition.extraFilterFields];
}
