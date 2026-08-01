import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mapApiErrorToFields } from "@/components/domain/FormModal";
import {
  ALLOWED_TIMEZONES,
  accountSchema,
  type AccountFormValues,
} from "@/features/account/schema";
import { lookupCep } from "@/lib/cep";
import { ApiError } from "@/lib/errors";

export interface AccountFormProps {
  defaultValues: AccountFormValues;
  disabled?: boolean;
  serverError?: ApiError | null;
  onSubmit: (values: AccountFormValues) => Promise<void>;
}

interface FieldConfig {
  name: keyof AccountFormValues;
  label: string;
  type?: string;
}

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Razão social" },
  { name: "alternate_name", label: "Nome fantasia" },
  { name: "identification", label: "CPF/CNPJ" },
  { name: "postal_code", label: "CEP" },
  { name: "street", label: "Endereço" },
  { name: "region", label: "Bairro" },
  { name: "city", label: "Cidade" },
  { name: "country", label: "País" },
  { name: "cellphone", label: "Celular" },
  { name: "phone", label: "Telefone" },
  { name: "email", label: "E-mail principal", type: "email" },
  { name: "email_admin", label: "E-mail financeiro", type: "email" },
  { name: "site", label: "Site" },
];

export function AccountForm({
  defaultValues,
  disabled = false,
  serverError,
  onSubmit,
}: AccountFormProps): JSX.Element {
  const {
    register,
    handleSubmit,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<AccountFormValues>({
    resolver: zodResolver(accountSchema),
    defaultValues,
  });

  React.useEffect(() => {
    if (!serverError) return;
    for (const { field, message } of mapApiErrorToFields(serverError)) {
      setError(field as keyof AccountFormValues, { type: "server", message });
    }
  }, [serverError, setError]);

  async function handleCepBlur(event: React.FocusEvent<HTMLInputElement>): Promise<void> {
    const result = await lookupCep(event.target.value);
    if (!result) return;
    setValue("state", result.state, { shouldValidate: true });
    setValue("city", result.city, { shouldValidate: true });
    if (result.street) setValue("street", result.street, { shouldValidate: true });
    if (result.region) setValue("region", result.region, { shouldValidate: true });
  }

  return (
    <form
      onSubmit={(event) => void handleSubmit(onSubmit)(event)}
      noValidate
      className="grid max-w-2xl gap-4 sm:grid-cols-2"
    >
      {FIELDS.map(({ name, label, type }) => {
        const registration = register(name);
        return (
          <div key={name} className="space-y-1">
            <Label htmlFor={name}>{label}</Label>
            <Input
              id={name}
              type={type ?? "text"}
              disabled={disabled}
              {...registration}
              onBlur={(event) => {
                void registration.onBlur(event);
                if (name === "postal_code") void handleCepBlur(event);
              }}
            />
            {errors[name] && <p className="text-sm text-danger">{errors[name]?.message}</p>}
          </div>
        );
      })}

      <div className="space-y-1">
        <Label htmlFor="state">UF</Label>
        <Input id="state" maxLength={2} disabled={disabled} {...register("state")} />
        {errors.state && <p className="text-sm text-danger">{errors.state.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="timezone">Timezone</Label>
        <select
          id="timezone"
          disabled={disabled}
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
          {...register("timezone")}
        >
          {ALLOWED_TIMEZONES.map((tz) => (
            <option key={tz.value} value={tz.value}>
              {tz.label}
            </option>
          ))}
        </select>
        {errors.timezone && <p className="text-sm text-danger">{errors.timezone.message}</p>}
      </div>

      {serverError && !serverError.errors?.length && (
        <p role="alert" className="text-sm text-danger sm:col-span-2">
          {serverError.message}
        </p>
      )}

      {!disabled && (
        <div className="sm:col-span-2">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Salvando..." : "Salvar"}
          </Button>
        </div>
      )}
    </form>
  );
}
