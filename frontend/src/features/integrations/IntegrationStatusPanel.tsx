import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { BarChart } from "@/components/domain/BarChart";
import { EmptyState } from "@/components/domain/EmptyState";
import { StatCard } from "@/components/domain/StatCard";
import { Button } from "@/components/ui/button";
import {
  getIntegrationStatus,
  listIntegrationAlerts,
  resolveIntegrationAlert,
} from "@/features/integrations/api";

const INTEGRATION_LABELS: Record<string, string> = { djen: "DJEN", datajud: "DataJud" };
const STATUS_LABELS: Record<string, string> = {
  PENDENTE: "Pendente",
  SINCRONIZANDO: "Sincronizando",
  ATIVO: "Ativo",
  FALHA: "Falha",
  PAUSADO: "Pausado",
};

function healthLabel(isHealthy: boolean | null): string {
  if (isHealthy === null) return "Sem checagem ainda";
  return isHealthy ? "Saudável" : "Com falha";
}

/** Painel de observabilidade da sincronização (spec 049 §6) — somente leitura,
 * exceto resolver alerta (regra 10). `canResolve` é o único ponto de escrita. */
export function IntegrationStatusPanel({ canResolve }: { canResolve: boolean }): JSX.Element {
  const queryClient = useQueryClient();
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["integrations", "status"],
    queryFn: getIntegrationStatus,
  });
  const { data: alerts, isLoading: alertsLoading } = useQuery({
    queryKey: ["integrations", "alerts", { resolved: false }],
    queryFn: () => listIntegrationAlerts(false),
  });
  const resolve = useMutation({
    mutationFn: resolveIntegrationAlert,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["integrations", "alerts"] }).then(() => undefined),
  });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {statusLoading
          ? [0, 1].map((key) => <StatCard key={key} label="…" value="…" isLoading />)
          : (status?.integrations ?? []).map((item) => (
              <StatCard
                key={item.integration}
                label={INTEGRATION_LABELS[item.integration] ?? item.integration}
                value={healthLabel(item.is_healthy)}
                variation={
                  item.failures_24h > 0
                    ? { label: `${item.failures_24h} falha(s) em 24h`, trend: "down" }
                    : { label: "sem falhas em 24h", trend: "flat" }
                }
              />
            ))}
      </div>

      {!statusLoading && status && status.terms_by_status.length > 0 && (
        <BarChart
          title="Termos monitorados por status"
          data={status.terms_by_status.map((item) => ({
            label: STATUS_LABELS[item.status] ?? item.status,
            value: item.count,
          }))}
        />
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium text-primary">Alertas abertos</h3>
        {alertsLoading ? (
          <p className="text-sm text-muted">Carregando…</p>
        ) : !alerts || alerts.items.length === 0 ? (
          <EmptyState title="Nenhum alerta aberto" description="Tudo funcionando normalmente." />
        ) : (
          <ul className="space-y-2">
            {alerts.items.map((alert) => (
              <li
                key={alert.id}
                className="flex items-start justify-between gap-3 rounded border border-default bg-surface p-3"
              >
                <div>
                  <span
                    className={`mr-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                      alert.severity === "critical"
                        ? "bg-danger/15 text-danger"
                        : "bg-warning/15 text-warning"
                    }`}
                  >
                    {alert.severity === "critical" ? "Crítico" : "Aviso"}
                  </span>
                  <span className="text-sm text-primary">{alert.message}</span>
                </div>
                {canResolve && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={resolve.isPending}
                    onClick={() => resolve.mutate(alert.id)}
                  >
                    Resolver
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
