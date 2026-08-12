import { useQuery } from "@tanstack/react-query";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  listDunningAttempts,
  type DunningAttemptData,
  type DunningChannel,
  type DunningStatus,
} from "@/features/financial/dunning-api";
import { formatBrl } from "@/lib/money";

const CHANNEL_LABELS: Record<DunningChannel, string> = {
  EMAIL: "E-mail",
  SMS: "SMS",
  WHATSAPP: "WhatsApp",
};

const STATUS_LABELS: Record<DunningStatus, string> = {
  SENT: "Enviado",
  FAILED: "Falhou",
  SKIPPED: "Não enviado",
};

const STATUS_CLASSES: Record<DunningStatus, string> = {
  SENT: "text-success",
  FAILED: "text-danger",
  SKIPPED: "text-muted",
};

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("pt-BR");
}

export interface DunningHistoryDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transactionId: string | null;
  transactionAmount?: number | null;
}

function attemptOrigin(attempt: DunningAttemptData): string {
  return attempt.is_manual ? "Envio manual" : "Régua automática";
}

/** Histórico de tentativas de cobrança de um lançamento (spec 061, regra 4/8) —
 * régua e envio manual nunca colidem (`rule_id` diferencia), por isso cada linha mostra
 * a origem explicitamente. */
export function DunningHistoryDrawer({
  open,
  onOpenChange,
  transactionId,
  transactionAmount,
}: DunningHistoryDrawerProps): JSX.Element {
  const { data: attempts, isLoading } = useQuery({
    queryKey: ["dunning-attempts", transactionId],
    queryFn: () => listDunningAttempts(transactionId as string),
    enabled: open && transactionId !== null,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Histórico de cobrança</DialogTitle>
        <DialogDescription>
          {transactionAmount != null
            ? `Lançamento de ${formatBrl(transactionAmount)}.`
            : "Tentativas de cobrança registradas para este lançamento."}
        </DialogDescription>

        {isLoading && <p className="text-sm text-muted">Carregando…</p>}

        {!isLoading && (attempts ?? []).length === 0 && (
          <p className="text-sm text-muted">Nenhuma tentativa de cobrança ainda.</p>
        )}

        {!isLoading && (attempts ?? []).length > 0 && (
          <ul className="max-h-96 space-y-2 overflow-y-auto">
            {(attempts ?? []).map((attempt) => (
              <li key={attempt.id} className="rounded border border-default bg-surface p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-primary">
                    {CHANNEL_LABELS[attempt.channel]} · {attemptOrigin(attempt)}
                  </span>
                  <span className={`font-medium ${STATUS_CLASSES[attempt.status]}`}>
                    {STATUS_LABELS[attempt.status]}
                  </span>
                </div>
                <p className="text-muted">{formatDateTime(attempt.sent_at)}</p>
                {attempt.sent_to && <p className="text-muted">Para: {attempt.sent_to}</p>}
                {attempt.error && <p className="text-danger">{attempt.error}</p>}
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
