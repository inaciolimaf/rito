import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { QueryStateGate } from "@/components/domain/QueryStateGate";
import { ServerErrorAlert } from "@/components/domain/ServerErrorAlert";
import { StatCard } from "@/components/domain/StatCard";
import { getAiBudget, saveAiBudget, type BudgetData } from "@/features/ai/api";
import { ApiError } from "@/lib/errors";
import { formatUsd } from "@/lib/format";

/** Barra de consumo do mês. A cor é informação, não enfeite: verde até o alerta,
 * âmbar entre alerta e teto, vermelho estourado. */
function ConsumptionBar({ budget }: { budget: BudgetData }): JSX.Element | null {
  if (budget.used_pct === null) return null;
  const largura = Math.min(budget.used_pct, 100);
  const cor = budget.is_exceeded ? "bg-danger" : budget.is_alerting ? "bg-warning" : "bg-success";
  return (
    <div
      className="h-2 w-full overflow-hidden rounded bg-muted/20"
      role="progressbar"
      aria-label="Consumo do orçamento mensal"
      aria-valuenow={Math.round(budget.used_pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={`h-full ${cor}`} style={{ width: `${largura}%` }} />
    </div>
  );
}

/** Orçamento mensal de IA (spec 090, alvo 2).
 *
 * A tela existe para responder duas perguntas antes da fatura: quanto já foi gasto este
 * mês, e o que acontece quando o teto chegar. */
export function AiBudgetPanel(): JSX.Element {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["ai-budget"],
    queryFn: getAiBudget,
  });
  const [limite, setLimite] = React.useState<string | null>(null);
  const [alerta, setAlerta] = React.useState<number | null>(null);
  const [bloqueia, setBloqueia] = React.useState<boolean | null>(null);

  const salvar = useMutation({
    mutationFn: saveAiBudget,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["ai-budget"] }).then(() => undefined),
  });

  return (
    <QueryStateGate
      isLoading={isLoading}
      error={error}
      data={data}
      loadingLabel="Carregando orçamento…"
      className=""
      onRetry={() => void refetch()}
    >
      {(budget) => (
        <BudgetForm
          budget={budget}
          limite={limite}
          alerta={alerta}
          bloqueia={bloqueia}
          onLimite={setLimite}
          onAlerta={setAlerta}
          onBloqueia={setBloqueia}
          onSave={(payload) => salvar.mutate(payload)}
          isSaving={salvar.isPending}
          saveError={salvar.error instanceof ApiError ? salvar.error : null}
        />
      )}
    </QueryStateGate>
  );
}

interface BudgetFormProps {
  budget: BudgetData;
  limite: string | null;
  alerta: number | null;
  bloqueia: boolean | null;
  onLimite: (value: string) => void;
  onAlerta: (value: number) => void;
  onBloqueia: (value: boolean) => void;
  onSave: (payload: {
    monthly_limit_usd: string | null;
    alert_pct: number;
    is_blocking: boolean;
  }) => void;
  isSaving: boolean;
  saveError: ApiError | null;
}

function BudgetForm({
  budget: data,
  limite,
  alerta,
  bloqueia,
  onLimite,
  onAlerta,
  onBloqueia,
  onSave,
  isSaving,
  saveError,
}: BudgetFormProps): JSX.Element {
  const limiteAtual =
    limite ?? (data.monthly_limit_usd === null ? "" : String(data.monthly_limit_usd));
  const alertaAtual = alerta ?? data.alert_pct;
  const bloqueiaAtual = bloqueia ?? data.is_blocking;

  return (
    <section className="space-y-3" aria-label="Orçamento de IA">
      <h2 className="text-sm font-semibold text-primary">Orçamento mensal</h2>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <StatCard label="Gasto no mês" value={formatUsd(data.spent_usd)} />
        <StatCard
          label="Teto"
          value={data.monthly_limit_usd === null ? "sem teto" : formatUsd(data.monthly_limit_usd)}
        />
        <StatCard label="Consumido" value={data.used_pct === null ? "—" : `${data.used_pct}%`} />
      </div>

      <ConsumptionBar budget={data} />

      {data.is_exceeded && (
        <p role="alert" className="rounded border border-danger bg-danger/10 p-3 text-sm">
          Teto do mês atingido.{" "}
          {data.is_blocking
            ? "As chamadas de IA estão bloqueadas até o próximo mês ou até o teto ser aumentado."
            : "O bloqueio está desligado: as chamadas continuam acontecendo e o gasto segue subindo."}
        </p>
      )}
      {!data.is_exceeded && data.is_alerting && (
        <p role="alert" className="rounded border border-warning bg-warning/10 p-3 text-sm">
          O consumo passou de {data.alert_pct}% do teto do mês.
        </p>
      )}

      {data.anomalies.length > 0 && (
        <ul className="space-y-1 text-sm" aria-label="Gasto fora do padrão">
          {data.anomalies.map((item) => (
            <li key={item.feature_key} className="rounded border border-warning/60 p-2">
              <strong>{item.feature_key}</strong> gastou hoje {item.factor}× a média diária dela (
              {formatUsd(item.today_usd)} contra {formatUsd(item.daily_average_usd)}).
            </li>
          ))}
        </ul>
      )}

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          // Spec 138, regra 5: `void mutateAsync(...)` descartava a rejeição e o
          // componente nunca lia `salvar.isError` — o teto recusado pelo servidor sumia
          // sem uma palavra. `mutate` + `ServerErrorAlert` põem o 422 na tela.
          onSave({
            monthly_limit_usd: limiteAtual.trim() === "" ? null : limiteAtual.trim(),
            alert_pct: alertaAtual,
            is_blocking: bloqueiaAtual,
          });
        }}
      >
        <label className="flex flex-col text-xs text-muted">
          Teto mensal (US$)
          <input
            className="mt-1 w-32 rounded border border-default bg-surface p-1 text-sm"
            inputMode="decimal"
            placeholder="sem teto"
            value={limiteAtual}
            onChange={(event) => onLimite(event.target.value)}
          />
        </label>
        <label className="flex flex-col text-xs text-muted">
          Alertar em (%)
          <input
            className="mt-1 w-20 rounded border border-default bg-surface p-1 text-sm"
            type="number"
            min={1}
            max={100}
            value={alertaAtual}
            onChange={(event) => onAlerta(Number(event.target.value))}
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={bloqueiaAtual}
            onChange={(event) => onBloqueia(event.target.checked)}
          />
          Bloquear ao atingir o teto
        </label>
        <button
          type="submit"
          className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
          disabled={isSaving}
        >
          Salvar orçamento
        </button>
      </form>
      <ServerErrorAlert error={saveError} />
      <p className="text-xs text-muted">
        Desligar o bloqueio mantém o alerta: há escritório que prefere estourar o teto a parar no
        meio de um prazo.
      </p>
    </section>
  );
}
