import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { AggregateStatusPanel } from "@/features/integrations/AggregateStatusPanel";
import { CaptureMetricsChart } from "@/features/integrations/CaptureMetricsChart";
import { IntegrationStatusPanel } from "@/features/integrations/IntegrationStatusPanel";
import { getPublicationMetrics } from "@/features/integrations/api";
import { useAuth } from "@/providers/AuthProvider";

type IntegrationsTab = "status" | "aggregates";

const TABS = [
  { value: "status", label: "Status" },
  { value: "aggregates", label: "Agregados" },
] as const;

/** Configurações > Integrações (spec 049 §6) — painel de status + métricas de
 * captura; resolver alerta é a única ação de escrita (regra 10), só GESTOR.
 * Spec 078, §6: a aba `?tab=aggregates` mostra o registry de views materializadas
 * (defasagem, último erro) com refresh manual — visível para ADMINISTRADOR/GESTOR,
 * refresh só GESTOR. */
export function IntegrationsSettingsPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const canSeeAggregates = isGestor || user?.role === "ADMINISTRADOR";
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const tab: IntegrationsTab =
    requestedTab === "aggregates" && canSeeAggregates ? "aggregates" : "status";
  const { data: metrics } = useQuery({
    queryKey: ["publications", "metrics", 7],
    queryFn: () => getPublicationMetrics(7),
    enabled: tab === "status",
  });

  function handleSelect(value: IntegrationsTab): void {
    setSearchParams(value === "status" ? {} : { tab: value });
  }

  return (
    <div className="space-y-8 p-6">
      <h1 className="text-lg font-semibold text-primary">Integrações</h1>
      {canSeeAggregates && (
        <TabBar items={TABS} active={tab} ariaLabel="Abas de integrações" onSelect={handleSelect} />
      )}
      {tab === "status" ? (
        <>
          <IntegrationStatusPanel canResolve={isGestor} />
          {metrics && <CaptureMetricsChart metrics={metrics} />}
        </>
      ) : (
        <AggregateStatusPanel canRefresh={isGestor} />
      )}
    </div>
  );
}
