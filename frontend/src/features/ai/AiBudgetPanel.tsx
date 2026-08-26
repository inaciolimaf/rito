import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { StatCard } from "@/components/domain/StatCard";
import { getAiBudget, saveAiBudget, type BudgetData } from "@/features/ai/api";

function formatUsd(value: number): string {
  return `US$ ${value.toFixed(2)}`;
}

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
  const { data, isLoading } = useQuery({ queryKey: ["ai-budget"], queryFn: getAiBudget });
  const [limite, setLimite] = React.useState<string | null>(null);
  const [alerta, setAlerta] = React.useState<number | null>(null);
  const [bloqueia, setBloqueia] = React.useState<boolean | null>(null);

  const salvar = useMutation({
    mutationFn: saveAiBudget,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["ai-budget"] }).then(() => undefined),
  });

  if (isLoading || !data) {
    return <p className="text-sm text-muted">Carregando orçamento…</p>;
  }

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
          void salvar.mutateAsync({
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
            onChange={(event) => setLimite(event.target.value)}
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
            onChange={(event) => setAlerta(Number(event.target.value))}
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={bloqueiaAtual}
            onChange={(event) => setBloqueia(event.target.checked)}
          />
          Bloquear ao atingir o teto
        </label>
        <button
          type="submit"
          className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
          disabled={salvar.isPending}
        >
          Salvar orçamento
        </button>
      </form>
      <p className="text-xs text-muted">
        Desligar o bloqueio mantém o alerta: há escritório que prefere estourar o teto a parar no
        meio de um prazo.
      </p>
    </section>
  );
}
