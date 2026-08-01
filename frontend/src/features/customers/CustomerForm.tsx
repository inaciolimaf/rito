import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RepresentativeFields } from "@/features/customers/RepresentativeFields";
import {
  DEFAULT_CUSTOMER_FORM_VALUES,
  PF_ONLY_FIELDS,
  type CustomerFormValues,
} from "@/features/customers/schema";

export interface CustomerFormMaritalStatus {
  id: number;
  name: string;
}

export interface CustomerFormProps {
  form: UseFormReturn<CustomerFormValues>;
  maritalStatuses: CustomerFormMaritalStatus[];
  onSearchOrigins: (query: string) => Promise<EntityOption[]>;
  currentOrigin: EntityOption | null;
}

/** Alterna Pessoa física / Pessoa jurídica (regra 2: mudar para PJ limpa e esconde os campos
 * exclusivos de PF). `origin_id` usa EntityPicker (a lista de origens cresce livremente, spec
 * 016) — os demais campos limitados (estado civil, sexo) usam `<select>` nativo. */
export function CustomerForm({
  form,
  maritalStatuses,
  onSearchOrigins,
  currentOrigin,
}: CustomerFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const type = watch("type");
  const hasRepresentative = watch("has_representative");
  const originId = watch("origin_id");
  const isPJ = type === "PJ";

  React.useEffect(() => {
    if (isPJ) {
      for (const field of PF_ONLY_FIELDS) {
        setValue(field, DEFAULT_CUSTOMER_FORM_VALUES[field] as never, { shouldDirty: true });
      }
    }
  }, [isPJ, setValue]);

  const selectedOrigin: EntityOption[] =
    originId && currentOrigin?.id === originId ? [currentOrigin] : [];

  return (
    <>
      <fieldset className="flex gap-4">
        <legend className="text-sm font-medium text-primary">Tipo</legend>
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="radio" value="PF" {...register("type")} />
          Pessoa física
        </label>
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="radio" value="PJ" {...register("type")} />
          Pessoa jurídica
        </label>
      </fieldset>

      <div className="space-y-1">
        <Label htmlFor="customer-name">{isPJ ? "Razão social" : "Nome"}</Label>
        <Input id="customer-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="customer-origin">Origem da pessoa</Label>
        <EntityPicker
          value={selectedOrigin}
          onChange={(next) => setValue("origin_id", next[0]?.id ?? "", { shouldDirty: true })}
          onSearch={onSearchOrigins}
          label="Origem da pessoa"
          placeholder="Buscar origem..."
        />
        {errors.origin_id && <p className="text-sm text-danger">{errors.origin_id.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="identification">{isPJ ? "CNPJ" : "CPF"}</Label>
        <Input id="identification" {...register("identification")} />
      </div>

      {!isPJ && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="document">RG</Label>
              <Input id="document" {...register("document")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="birthdate">Data de nascimento</Label>
              <Input id="birthdate" type="date" {...register("birthdate")} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="marital_status_id">Estado civil</Label>
              <select
                id="marital_status_id"
                className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                {...register("marital_status_id")}
              >
                <option value="">Selecione</option>
                {maritalStatuses.map((status) => (
                  <option key={status.id} value={status.id}>
                    {status.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="gender">Sexo</Label>
              <select
                id="gender"
                className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                {...register("gender")}
              >
                <option value="">Selecione</option>
                <option value="F">Feminino</option>
                <option value="M">Masculino</option>
              </select>
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="occupation">Profissão</Label>
            <Input id="occupation" {...register("occupation")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="nationality">Nacionalidade</Label>
              <Input id="nationality" {...register("nationality")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mother_name">Nome da mãe</Label>
              <Input id="mother_name" {...register("mother_name")} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label htmlFor="number_pis">PIS/PASEP</Label>
              <Input id="number_pis" {...register("number_pis")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="number_ctps">CTPS</Label>
              <Input id="number_ctps" {...register("number_ctps")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="number_cid">CID</Label>
              <Input id="number_cid" {...register("number_cid")} />
            </div>
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="cellphone">Celular</Label>
          <Input id="cellphone" {...register("cellphone")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="phone">Telefone</Label>
          <Input id="phone" {...register("phone")} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="email">E-mail</Label>
        <Input id="email" type="email" {...register("email")} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="country">País</Label>
          <Input id="country" {...register("country")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="postal_code">CEP</Label>
          <Input id="postal_code" {...register("postal_code")} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="state">Estado</Label>
          <Input id="state" maxLength={2} {...register("state")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="city">Cidade</Label>
          <Input id="city" {...register("city")} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="street">Endereço</Label>
          <Input id="street" {...register("street")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="region">Bairro</Label>
          <Input id="region" {...register("region")} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="notes">Anotações gerais</Label>
        <textarea
          id="notes"
          className="min-h-20 w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("notes")}
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register("has_representative")} />
        Adicionar representante
      </label>

      {hasRepresentative && <RepresentativeFields form={form} />}
    </>
  );
}
