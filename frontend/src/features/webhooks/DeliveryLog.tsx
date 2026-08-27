import { useQuery } from "@tanstack/react-query";

import { listDeliveries } from "@/features/webhooks/api";

export interface DeliveryLogProps {
  endpointId: string;
}

/** Log de entrega (spec 093 §4).
 *
 * Mostra o código HTTP e o corpo da resposta porque a pergunta que chega ao suporte é
 * sempre a mesma: "o que vocês mandaram e o que voltou?". Sem o corpo, a resposta é um
 * número sem contexto. */
export function DeliveryLog({ endpointId }: DeliveryLogProps): JSX.Element {
  const { data, isLoading } = useQuery({
    queryKey: ["webhook-deliveries", endpointId],
    queryFn: () => listDeliveries(endpointId),
  });

  if (isLoading) return <p className="text-sm text-muted">Carregando entregas…</p>;
  const items = data?.items ?? [];
  if (items.length === 0) {
    return <p className="text-sm text-muted">Nenhum envio ainda.</p>;
  }

  return (
    <ul className="space-y-2" aria-label="Entregas">
      {items.map((delivery) => (
        <li key={delivery.id} className="rounded border border-default p-2 text-xs">
          <div className="flex items-center justify-between">
            <span>{new Date(delivery.created_at).toLocaleString("pt-BR")}</span>
            <span className={delivery.delivered_at ? "text-success" : "text-danger"}>
              {delivery.status_code ?? "sem resposta"}
              {delivery.attempt > 1 && ` · tentativa ${delivery.attempt}`}
            </span>
          </div>
          {delivery.error && <p className="mt-1 text-danger">{delivery.error}</p>}
          {delivery.response_body && (
            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-muted">
              {delivery.response_body.slice(0, 500)}
            </pre>
          )}
        </li>
      ))}
    </ul>
  );
}
