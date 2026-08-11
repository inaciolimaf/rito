import type { UseFormReturn } from "react-hook-form";

import { MoneyField } from "@/components/domain/MoneyField";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InstitutionSelect } from "@/features/financial/InstitutionSelect";
import type { BankAccountFormValues } from "@/features/financial/schema";

export interface BankAccountFormProps {
  form: UseFormReturn<BankAccountFormValues>;
  institutionLabel?: string | null;
}

const KIND_LABELS: Record<BankAccountFormValues["kind"], string> = {
  CORRENTE: "Conta corrente",
  POUPANCA: "Poupança",
  INVESTIMENTO: "Investimento",
  CARTAO_CREDITO: "Cartão de crédito",
  OUTRO: "Outro",
};

/** Nome + tipo + instituição/agência/número + saldo inicial, com fechamento/vencimento
 * SÓ pra cartão de crédito (regra 1, spec 055) — os campos somem pros demais tipos em
 * vez de aparecer desabilitados, porque não fazem sentido nenhum fora do cartão. */
export function BankAccountForm({ form, institutionLabel }: BankAccountFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    control,
    formState: { errors },
  } = form;

  const kind = watch("kind");
  const isCard = kind === "CARTAO_CREDITO";
  const institutionId = watch("institution_id");

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="account-name">Nome</Label>
        <Input id="account-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="account-kind">Tipo</Label>
        <select
          id="account-kind"
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("kind")}
        >
          {Object.entries(KIND_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <InstitutionSelect
        value={institutionId}
        onChange={(id) => setValue("institution_id", id)}
        currentLabel={institutionLabel}
      />

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="account-agency">Agência</Label>
          <Input id="account-agency" {...register("agency")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="account-number">Conta</Label>
          <Input id="account-number" {...register("account_number")} />
        </div>
      </div>

      {isCard && (
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="account-cycle-day">Fechamento (dia)</Label>
            <Input
              id="account-cycle-day"
              type="number"
              min={1}
              max={31}
              {...register("cycle_day")}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="account-due-day">Vencimento (dia)</Label>
            <Input id="account-due-day" type="number" min={1} max={31} {...register("due_day")} />
          </div>
        </div>
      )}
      {errors.cycle_day && <p className="text-sm text-danger">{errors.cycle_day.message}</p>}

      <MoneyField control={control} name="initial_amount" label="Saldo inicial" />

      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register("is_default")} />
        Definir como conta padrão
      </label>
    </>
  );
}
