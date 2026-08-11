import { useQuery } from "@tanstack/react-query";

import { StatCard } from "@/components/domain/StatCard";
import { getBankAccountBalance, type BankAccountData } from "@/features/financial/api";
import { formatBrl } from "@/lib/money";

/** Saldo (ou fatura do ciclo, pra cartão) de uma conta — reaproveita `StatCard` (spec
 * 007). Regras 3/4 completas na spec 056 (lançamentos); por enquanto mostra o saldo
 * inicial, que é o que a API já devolve (spec 055, Descobertas). */
export function AccountBalanceCard({ account }: { account: BankAccountData }): JSX.Element {
  const { data, isLoading } = useQuery({
    queryKey: ["bank-account-balance", account.id],
    queryFn: () => getBankAccountBalance(account.id),
  });

  const label = account.kind === "CARTAO_CREDITO" ? "Fatura do ciclo" : "Saldo";
  return (
    <StatCard
      label={`${label} — ${account.name}`}
      value={formatBrl(data?.balance ?? null)}
      isLoading={isLoading}
    />
  );
}
