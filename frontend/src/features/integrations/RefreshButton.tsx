import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { refreshAggregate } from "@/features/integrations/api";
import { ApiError } from "@/lib/errors";

export interface RefreshButtonProps {
  name: string;
  onRefreshed?: () => void;
}

const THROTTLE_SECONDS = 600; // regra 8: 1 refresh manual por agregado a cada 10 min

/** Refresh manual de um agregado (spec 078, §6) com throttle visível: após disparar,
 * fica desabilitado pelos 10 min da regra 8 com a contagem regressiva no tooltip;
 * um 429 do backend (refresh em outra aba/dispositivo) vira a mesma mensagem. */
export function RefreshButton({ name, onRefreshed }: RefreshButtonProps): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [blockedUntil, setBlockedUntil] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [, setTick] = useState(0);

  const blocked = blockedUntil !== null && blockedUntil > Date.now();
  const remainingSeconds = blocked ? Math.ceil((blockedUntil - Date.now()) / 1000) : 0;

  // Re-render a cada 30 s para a contagem regressiva do throttle andar.
  useEffect(() => {
    if (!blocked) return;
    const timer = setInterval(() => setTick((tick) => tick + 1), 30_000);
    return () => clearInterval(timer);
  }, [blocked]);

  async function handleClick(): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      await refreshAggregate(name);
      setBlockedUntil(Date.now() + THROTTLE_SECONDS * 1000);
      onRefreshed?.();
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setBlockedUntil(Date.now() + THROTTLE_SECONDS * 1000);
        setMessage("Refresh já solicitado nos últimos 10 minutos.");
      } else {
        setMessage("Falha ao solicitar o refresh.");
      }
    } finally {
      setBusy(false);
    }
  }

  const tooltip = blocked
    ? `Limite de 1 refresh a cada 10 min — tente de novo em ${Math.ceil(remainingSeconds / 60)} min.`
    : "Atualizar agora";

  return (
    <span className="inline-flex flex-col gap-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy || blocked}
        title={tooltip}
        onClick={() => void handleClick()}
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        {busy
          ? "Atualizando…"
          : blocked
            ? `Aguarde ${Math.ceil(remainingSeconds / 60)} min`
            : "Atualizar"}
      </Button>
      {message && (
        <span role="alert" className="text-xs text-warning">
          {message}
        </span>
      )}
    </span>
  );
}
