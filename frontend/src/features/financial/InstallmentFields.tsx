import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TransactionFormValues } from "@/features/financial/schema";
import { installmentDueDates, splitInstallmentAmounts } from "@/lib/installments";
import { formatBrl } from "@/lib/money";

export interface InstallmentFieldsProps {
  form: UseFormReturn<TransactionFormValues>;
}

/** Regra 2/3/6 (spec 057): preview ao vivo das parcelas antes de salvar — mesma divisão
 * (resto na última) e mesmo clamp de vencimento (dia 31 → último dia) que o backend vai
 * aplicar de verdade na criação. */
export function InstallmentFields({ form }: InstallmentFieldsProps): JSX.Element {
  const { register, watch } = form;
  const count = Number(watch("installmentCount"));
  const amount = Number(watch("amount"));
  const dueDate = watch("due_date");

  const preview =
    Number.isInteger(count) && count >= 2 && count <= 100 && amount > 0 && dueDate
      ? installmentDueDates(dueDate, count).map((date, index) => ({
          number: index + 1,
          due_date: date,
          amount: splitInstallmentAmounts(amount, count)[index] ?? 0,
        }))
      : [];

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <Label htmlFor="installment-count">Número de parcelas</Label>
        <Input
          id="installment-count"
          type="number"
          min={2}
          max={100}
          {...register("installmentCount")}
        />
      </div>

      {preview.length > 0 && (
        <ul className="max-h-40 space-y-1 overflow-y-auto rounded border border-default p-2 text-sm">
          {preview.map((item) => (
            <li key={item.number} className="flex justify-between text-primary">
              <span>
                {item.number}/{count} — {item.due_date.split("-").reverse().join("/")}
              </span>
              <span>{formatBrl(item.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
