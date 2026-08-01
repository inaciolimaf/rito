import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CpfCnpjField } from "@/features/customers/CpfCnpjField";
import { PostalCodeField } from "@/features/customers/PostalCodeField";
import { StateCitySelect } from "@/features/customers/StateCitySelect";
import type { CustomerFormValues } from "@/features/customers/schema";

export interface RepresentativeFieldsProps {
  form: UseFormReturn<CustomerFormValues>;
}

/** Bloco de representante legal (regra 4: `rep_name` obrigatório quando ativado) —
 * mostrado só quando `has_representative` está marcado. Representante não tem um "tipo"
 * próprio na spec (PF/PJ é só do contato principal) — `CpfCnpjField` assume PF aqui, a
 * imensa maioria dos casos reais (representante de menor/incapaz, procurador). */
export function RepresentativeFields({ form }: RepresentativeFieldsProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    control,
    formState: { errors },
  } = form;

  return (
    <fieldset className="space-y-3 rounded border border-default p-3">
      <legend className="text-sm font-medium text-primary">Representante legal</legend>

      <div className="space-y-1">
        <Label htmlFor="rep_name">Nome do representante</Label>
        <Input id="rep_name" {...register("rep_name")} />
        {errors.rep_name && <p className="text-sm text-danger">{errors.rep_name.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <CpfCnpjField
          control={control}
          name="rep_identification"
          personType="PF"
          label="CPF/CNPJ do representante"
          id="rep_identification"
        />
        <div className="space-y-1">
          <Label htmlFor="rep_document">RG do representante</Label>
          <Input id="rep_document" {...register("rep_document")} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="rep_birthdate">Data de nascimento</Label>
        <Input id="rep_birthdate" type="date" {...register("rep_birthdate")} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="rep_country">País</Label>
          <Input id="rep_country" {...register("rep_country")} />
        </div>
        <PostalCodeField
          control={control}
          name="rep_postal_code"
          id="rep_postal_code"
          onFound={(result) => {
            setValue("rep_state", result.state, { shouldDirty: true });
            setValue("rep_city", result.city, { shouldDirty: true });
            setValue("rep_street", result.street, { shouldDirty: true });
            setValue("rep_region", result.region, { shouldDirty: true });
          }}
        />
      </div>

      <StateCitySelect
        control={control}
        setValue={setValue}
        stateName="rep_state"
        cityName="rep_city"
        stateValue={watch("rep_state") ?? ""}
        cityValue={watch("rep_city") ?? ""}
      />

      <div className="space-y-1">
        <Label htmlFor="rep_street">Endereço</Label>
        <Input id="rep_street" {...register("rep_street")} />
      </div>

      <div className="space-y-1">
        <Label htmlFor="rep_region">Bairro</Label>
        <Input id="rep_region" {...register("rep_region")} />
      </div>
    </fieldset>
  );
}
