import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { CashFlowChart } from "@/components/domain/CashFlowChart";
import { StatCard, type StatCardProps } from "@/components/domain/StatCard";
import { AccountBalanceRow } from "@/features/financial/AccountBalanceRow";
import {
  getTransactionChart,
  getTransactionStats,
  listBankAccountBalances,
  type Regime,
} from "@/features/financial/api";
import { MonthNavigator } from "@/features/financial/MonthNavigator";
import { RegimeSelect } from "@/features/financial/RegimeSelect";
import { formatBrl } from "@/lib/money";

type Trend = NonNullable<StatCardProps["variation"]>["trend"];

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Regra 9 (ADVBOX): saldo compara "agora" com o fim do mês anterior — não é uma
 * variação percentual de contagem, então calculamos o rótulo aqui (mesmo padrão de
 * `variationOf` em LawsuitStatsPanel), passando `value` já formatado em R$. */
function balanceVariation(current: number, previous: number): { label: string; trend: Trend } {
  if (previous === 0) {
    if (current === 0) return { label: "sem movimento", trend: "flat" };
    return { label: "novo saldo", trend: current > 0 ? "up" : "down" };
  }
  const pct = ((current - previous) / Math.abs(previous)) * 100;
  const trend: Trend = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
  const sign = pct > 0 ? "+" : "";
  return { label: `${sign}${pct.toFixed(1)}% vs. mês anterior`, trend };
}

function formatDay(isoDate: string): string {
  const [, month, day] = isoDate.split("-");
  return `${day}/${month}`;
}

/** Dashboard financeiro (spec 059) — cards, gráfico receitas × despesas e saldo por
 * conta, nos 4 regimes de visualização. Regra 8: regime/mês vivem na URL, então
 * recarregar a página ou compartilhar o link preserva o estado. */
export function FinancialDashboard(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const regime = (searchParams.get("regime") as Regime | null) ?? "due";
  const month = searchParams.get("month") ?? currentMonth();

  const setRegime = React.useCallback(
    (value: Regime) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.set("regime", value);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setMonth = React.useCallback(
    (value: string) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.set("month", value);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["transactions", "stats", { regime, month }],
    queryFn: () => getTransactionStats({ regime, month }),
  });

  const { data: chart } = useQuery({
    queryKey: ["transactions", "chart", { month }],
    queryFn: () => getTransactionChart({ month, group_by: "day" }),
  });

  const { data: balances } = useQuery({
    queryKey: ["bank-accounts", "balances"],
    queryFn: () => listBankAccountBalances(),
  });

  return (
    <section aria-label="Painel financeiro" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonthNavigator month={month} onChange={setMonth} />
        <RegimeSelect value={regime} onChange={setRegime} />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="space-y-1">
          <StatCard
            label="Saldo"
            value={formatBrl(stats?.balance ?? 0)}
            isLoading={statsLoading}
            negative={(stats?.balance ?? 0) < 0}
            variation={stats ? balanceVariation(stats.balance, stats.balance_previous) : null}
          />
          {stats && <p className="text-[11px] text-muted">{stats.balance_staleness_hint}</p>}
        </div>
        <StatCard
          label="Receita"
          value={formatBrl(stats?.income_realized ?? 0)}
          isLoading={statsLoading}
          variation={
            stats ? { label: `Previsto: ${formatBrl(stats.income_expected)}`, trend: "flat" } : null
          }
        />
        <StatCard
          label="Despesa"
          value={formatBrl(stats?.expense_realized ?? 0)}
          isLoading={statsLoading}
          variation={
            stats
              ? { label: `Previsto: ${formatBrl(stats.expense_expected)}`, trend: "flat" }
              : null
          }
        />
        <StatCard
          label="Atrasados"
          value={formatBrl(stats?.overdue ?? 0)}
          isLoading={statsLoading}
        />
      </div>

      <div className="rounded border border-default bg-surface p-4">
        <CashFlowChart
          title="Receitas x Despesas por vencimento"
          data={(chart ?? []).map((point) => ({
            label: formatDay(point.period_start),
            income: point.income,
            expense: point.expense,
          }))}
        />
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-primary">Saldo por conta</h3>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {(balances ?? []).map((item) => (
            <AccountBalanceRow key={item.account_id} item={item} />
          ))}
        </div>
      </div>
    </section>
  );
}
