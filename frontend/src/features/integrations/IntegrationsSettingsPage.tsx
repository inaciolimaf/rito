import { useQuery } from "@tanstack/react-query";

import { CaptureMetricsChart } from "@/features/integrations/CaptureMetricsChart";
import { IntegrationStatusPanel } from "@/features/integrations/IntegrationStatusPanel";
import { getPublicationMetrics } from "@/features/integrations/api";
import { useAuth } from "@/providers/AuthProvider";

/** Configurações > Integrações (spec 049 §6) — painel de status + métricas de
 * captura; resolver alerta é a única ação de escrita (regra 10), só GESTOR. */
export function IntegrationsSettingsPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const { data: metrics } = useQuery({
    queryKey: ["publications", "metrics", 7],
    queryFn: () => getPublicationMetrics(7),
  });

  return (
    <div className="space-y-8 p-6">
      <h1 className="text-lg font-semibold text-primary">Integrações</h1>
      <IntegrationStatusPanel canResolve={isGestor} />
      {metrics && <CaptureMetricsChart metrics={metrics} />}
    </div>
  );
}
