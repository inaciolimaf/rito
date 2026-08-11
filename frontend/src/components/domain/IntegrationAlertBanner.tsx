import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { listOpenIntegrationAlerts } from "@/features/integration-alerts/api";
import { useAuth } from "@/providers/AuthProvider";

/** Banner global de alerta crítico de integração externa (spec 046 §6) — nasce com o
 * "chave do DataJud rotacionada" e é reutilizado pelo DJEN na spec 049. Só aparece
 * quando há alerta ABERTO de severidade `critical`; `warning` fica só no painel
 * de observabilidade (spec 049), não interrompe a tela toda. Spec 049, regra 4:
 * restrito a ADMINISTRADOR/GESTOR — o Colaborador não precisa (nem deveria) ver
 * um alerta de infraestrutura que não pode resolver. */
export function IntegrationAlertBanner(): JSX.Element | null {
  const { user } = useAuth();
  const canSee = user?.role === "ADMINISTRADOR" || user?.role === "GESTOR";
  const { data } = useQuery({
    queryKey: ["integration-alerts", "open"],
    queryFn: listOpenIntegrationAlerts,
    staleTime: 60_000,
    enabled: canSee,
  });

  const critical = data?.items.filter((alert) => alert.severity === "critical") ?? [];
  if (!canSee || critical.length === 0) {
    return null;
  }

  return (
    <div role="alert" className="border-b border-danger bg-danger/10 px-4 py-2">
      {critical.map((alert) => (
        <div key={alert.id} className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{alert.message}</span>
        </div>
      ))}
    </div>
  );
}
