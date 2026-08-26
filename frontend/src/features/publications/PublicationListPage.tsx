import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";
import { DataTable } from "@/components/domain/DataTable";
import { ListPageLayout } from "@/components/domain/ListPageLayout";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { useListPage } from "@/components/domain/useListPage";
import { Button } from "@/components/ui/button";
import { getPublicationMetrics } from "@/features/integrations/api";
import { listMonitoredTerms } from "@/features/monitored-terms/api";
import {
  exportPublications,
  getPublicationCounts,
  listPublications,
  type PublicationFilters as PublicationFiltersParams,
  type PublicationListItem,
} from "@/features/publications/api";
import { CancelledBadge } from "@/features/publications/CancelledBadge";
import { LinkToLawsuitDialog } from "@/features/publications/LinkToLawsuitDialog";
import { PublicationDetailDrawer } from "@/features/publications/PublicationDetailDrawer";
import { UnlinkedBanner } from "@/features/publications/UnlinkedBanner";
import { useAuth } from "@/providers/AuthProvider";
import { AutoReadToggle } from "@/features/publications/AutoReadToggle";
import { setAutoReadPublications } from "@/features/publications/analysis";

const FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "interval",
    label: "Período",
    type: "select",
    options: [
      { value: "today", label: "Hoje" },
      { value: "3d", label: "Últimos 3 dias" },
      { value: "7d", label: "Últimos 7 dias" },
      { value: "custom", label: "Personalizado" },
    ],
  },
  { key: "date_from", label: "De", type: "date" },
  { key: "date_to", label: "Até", type: "date" },
  { key: "court_code", label: "Tribunal", type: "text" },
  { key: "process_number", label: "Número do processo", type: "text" },
  { key: "linked", label: "Vinculada", type: "boolean" },
  { key: "cancelled", label: "Cancelada", type: "boolean" },
  { key: "read", label: "Lida", type: "boolean" },
];

/** Tela da controladoria (spec 048): o que chegou, o que já virou tarefa, o que
 * ficou sem processo. Regra 8: sem termo monitorado cadastrado, mostra estado
 * vazio explicativo em vez de uma lista sempre vazia sem explicação. */
export function PublicationListPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canSeeMetrics = user?.role === "ADMINISTRADOR" || user?.role === "GESTOR";

  const { data: termsPage, isLoading: isLoadingTerms } = useQuery({
    queryKey: ["monitored-terms", "for-publications-empty-state"],
    queryFn: () => listMonitoredTerms({}),
  });
  const hasNoTermConfigured = !isLoadingTerms && (termsPage?.total ?? 0) === 0;

  // Spec 049 §6: "painel no topo de /publications" — a taxa de vínculo automático
  // (regra 8) é o que mais importa pra controladoria enxergar de cara.
  const { data: metrics } = useQuery({
    queryKey: ["publications", "metrics", 7],
    queryFn: () => getPublicationMetrics(7),
    enabled: canSeeMetrics && !hasNoTermConfigured,
  });

  // Spec 086, regra 10: a leitura automática é decisão do escritório e vive junto da
  // lista, onde a consequência dela aparece.
  const [autoRead, setAutoRead] = React.useState(false);
  const [savingAutoRead, setSavingAutoRead] = React.useState(false);

  const { values, setValue } = useFilters(FILTER_FIELDS);
  const dateFrom = typeof values.date_from === "string" ? values.date_from : undefined;
  const dateTo = typeof values.date_to === "string" ? values.date_to : undefined;
  const explicitInterval =
    typeof values.interval === "string"
      ? (values.interval as PublicationFiltersParams["interval"])
      : undefined;
  const interval = explicitInterval ?? (dateFrom || dateTo ? "custom" : "7d");
  const courtCode = typeof values.court_code === "string" ? values.court_code : undefined;
  const processNumber =
    typeof values.process_number === "string" ? values.process_number : undefined;
  const linked = values.linked === undefined ? undefined : values.linked === "true";
  const cancelled = values.cancelled === undefined ? undefined : values.cancelled === "true";
  const read = values.read === undefined ? undefined : values.read === "true";

  const filters: PublicationFiltersParams = {
    interval,
    date_from: interval === "custom" ? dateFrom : undefined,
    date_to: interval === "custom" ? dateTo : undefined,
    court_code: courtCode,
    process_number: processNumber,
    linked,
    cancelled,
    read,
  };

  const listPage = useListPage({
    queryKey: "publications",
    filters,
    fetchPage: listPublications,
    exportFile: exportPublications,
    resetDeps: [interval, dateFrom, dateTo, courtCode, processNumber, linked, cancelled, read],
  });

  const { data: counts } = useQuery({
    queryKey: ["publications", "counts", interval, dateFrom, dateTo, courtCode, processNumber],
    queryFn: () =>
      getPublicationCounts({
        interval,
        date_from: interval === "custom" ? dateFrom : undefined,
        date_to: interval === "custom" ? dateTo : undefined,
        court_code: courtCode,
        process_number: processNumber,
      }),
  });

  const [detailId, setDetailId] = React.useState<string | null>(null);
  const [linkId, setLinkId] = React.useState<string | null>(null);

  function afterLink(): void {
    void queryClient.invalidateQueries({ queryKey: ["publications"] });
  }

  const columns: DataTableColumn<PublicationListItem>[] = [
    {
      id: "availability_date",
      header: "Data de disponibilização",
      cell: (row) => (
        <span className={row.is_read ? undefined : "font-semibold text-primary"}>
          {new Date(row.availability_date).toLocaleDateString("pt-BR")}
        </span>
      ),
    },
    { id: "court_code", header: "Tribunal", cell: (row) => row.court_code },
    { id: "organ_name", header: "Órgão", cell: (row) => row.organ_name ?? "—" },
    { id: "process_number", header: "Processo", cell: (row) => row.process_number ?? "—" },
    {
      id: "parties",
      header: "Partes",
      cell: (row) => (row.parties.length > 0 ? row.parties.join(", ") : "—"),
    },
    { id: "routed_to_name", header: "Responsável", cell: (row) => row.routed_to_name ?? "—" },
    {
      id: "status",
      header: "Status",
      cell: (row) =>
        !row.is_active ? (
          <CancelledBadge reason={row.cancellation_reason} />
        ) : row.lawsuit_id ? (
          <span className="text-sm text-success">Vinculada</span>
        ) : (
          <span className="text-sm text-warning">Não vinculada</span>
        ),
    },
  ];

  return (
    <ListPageLayout
      title="Intimações"
      filterFields={FILTER_FIELDS}
      dashboard={
        canSeeMetrics ? (
          <AutoReadToggle
            enabled={autoRead}
            disabled={savingAutoRead}
            onChange={(enabled) => {
              setAutoRead(enabled);
              setSavingAutoRead(true);
              void setAutoReadPublications(enabled).finally(() => setSavingAutoRead(false));
            }}
          />
        ) : undefined
      }
      actions={
        <>
          <Button variant="outline" onClick={() => void listPage.exportAs("xlsx")}>
            Exportar XLSX
          </Button>
          <Button variant="outline" onClick={() => void listPage.exportAs("pdf")}>
            Exportar PDF
          </Button>
        </>
      }
    >
      {hasNoTermConfigured ? (
        <EmptyState
          title="Nenhum termo monitorado cadastrado"
          description="Cadastre um termo (OAB, CPF ou CNPJ) para começar a receber intimações automaticamente."
          action={{
            label: "Configurar termos monitorados",
            onClick: () => navigate("/settings/monitored-terms"),
          }}
        />
      ) : (
        <>
          {metrics && (
            <div className="max-w-xs">
              <StatCard
                label={`Taxa de vínculo automático (${metrics.period_days} dias)`}
                value={
                  metrics.auto_link_rate === null
                    ? "—"
                    : `${Math.round(metrics.auto_link_rate * 100)}%`
                }
              />
            </div>
          )}

          <UnlinkedBanner
            count={counts?.unlinked ?? 0}
            onFilterUnlinked={() => setValue("linked", "false")}
          />

          <DataTable
            columns={columns}
            data={listPage.items}
            getRowId={(row) => row.id}
            isLoading={listPage.isLoading}
            error={listPage.error}
            emptyMessage="Nenhuma intimação encontrada com esses filtros."
            rowActions={(row) => (
              <div className="flex gap-2">
                <button
                  type="button"
                  className="text-sm text-accent underline"
                  onClick={() => setDetailId(row.id)}
                >
                  Ver
                </button>
                {!row.lawsuit_id && (
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => setLinkId(row.id)}
                  >
                    Vincular
                  </button>
                )}
              </div>
            )}
            pagination={listPage.pagination}
          />
        </>
      )}

      <PublicationDetailDrawer
        publicationId={detailId}
        onOpenChange={(open) => !open && setDetailId(null)}
      />
      <LinkToLawsuitDialog
        publicationId={linkId}
        onOpenChange={(open) => !open && setLinkId(null)}
        onLinked={afterLink}
      />
    </ListPageLayout>
  );
}
