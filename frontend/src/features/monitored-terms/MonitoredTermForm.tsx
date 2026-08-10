import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { StateData } from "@/features/locations/api";
import type { MonitoredTermFormValues } from "@/features/monitored-terms/schema";
import type { UserData } from "@/features/users/api";

export interface MonitoredTermFormProps {
  form: UseFormReturn<MonitoredTermFormValues>;
  states: StateData[];
  users: UserData[];
}

const KIND_LABELS: Record<MonitoredTermFormValues["kind"], string> = {
  OAB: "OAB",
  CPF: "CPF",
  CNPJ: "CNPJ",
};

/** Tipo → campos condicionais (spec 043 §6): a UF só existe para OAB (regra 1); CPF/CNPJ
 * dispensam. O backend revalida tudo — aqui é ergonomia, não fronteira de segurança. */
export function MonitoredTermForm({ form, states, users }: MonitoredTermFormProps): JSX.Element {
  const {
    register,
    watch,
    formState: { errors },
  } = form;

  const kind = watch("kind");

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="term-kind">Tipo</Label>
        <select
          id="term-kind"
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

      <div className="space-y-1">
        <Label htmlFor="term-value">
          {kind === "OAB" ? "Número da OAB" : kind === "CPF" ? "CPF" : "CNPJ"}
        </Label>
        <Input
          id="term-value"
          placeholder={kind === "OAB" ? "Somente números" : "Com ou sem máscara"}
          {...register("value")}
        />
        {errors.value && <p className="text-sm text-danger">{errors.value.message}</p>}
      </div>

      {kind === "OAB" && (
        <div className="space-y-1">
          <Label htmlFor="term-oab-state">UF da OAB</Label>
          <select
            id="term-oab-state"
            className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            {...register("oab_state")}
          >
            <option value="">Selecione a UF</option>
            {states.map((state) => (
              <option key={state.code} value={state.code}>
                {state.code} — {state.name}
              </option>
            ))}
          </select>
          {errors.oab_state && <p className="text-sm text-danger">{errors.oab_state.message}</p>}
        </div>
      )}

      <div className="space-y-1">
        <Label htmlFor="term-label">Rótulo (opcional)</Label>
        <Input id="term-label" placeholder="Ex.: OAB do sócio" {...register("label")} />
      </div>

      <div className="space-y-1">
        <Label htmlFor="term-user">Responsável pelas intimações (opcional)</Label>
        <select
          id="term-user"
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("user_id")}
        >
          <option value="">Regra do grupo de ação</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="term-backfill">Captura inicial a partir de (opcional)</Label>
        <Input id="term-backfill" type="date" {...register("backfill_from")} />
        <p className="text-xs text-muted">Padrão: 30 dias atrás. Máximo: 12 meses.</p>
        {errors.backfill_from && (
          <p className="text-sm text-danger">{errors.backfill_from.message}</p>
        )}
      </div>
    </>
  );
}
