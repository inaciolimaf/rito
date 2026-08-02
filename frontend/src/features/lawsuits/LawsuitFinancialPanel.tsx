import { StatCard } from "@/components/domain/StatCard";
import type { FinancialSummary } from "@/features/lawsuits/api";
import { formatBrl } from "@/lib/money";

export interface LawsuitFinancialPanelProps {
  summary: FinancialSummary;
}

/** Painel de resumo financeiro do processo (spec 024 §6). Recebido/a receber/despesas/
 * líquido ficam zerados até a spec 056 (lançamentos). */
export function LawsuitFinancialPanel({ summary }: LawsuitFinancialPanelProps): JSX.Element {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-primary">Resumo financeiro</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <StatCard label="Valor da causa" value={formatBrl(summary.case_value)} />
        <StatCard label="Honorários contratados" value={formatBrl(summary.fees_value)} />
        <StatCard label="Recebido" value={formatBrl(summary.received)} />
        <StatCard label="A receber" value={formatBrl(summary.to_receive)} />
        <StatCard label="Despesas" value={formatBrl(summary.expenses)} />
        <StatCard label="Resultado líquido" value={formatBrl(summary.net_result)} />
      </div>
    </div>
  );
}
