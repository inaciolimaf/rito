import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CustomerFormValues } from "@/features/customers/schema";

export interface RepresentativeFieldsProps {
  form: UseFormReturn<CustomerFormValues>;
}

/** Bloco de representante legal (regra 4: `rep_name` obrigatório quando ativado) —
 * mostrado só quando `has_representative` está marcado. */
export function RepresentativeFields({ form }: RepresentativeFieldsProps): JSX.Element {
  const {
    register,
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
        <div className="space-y-1">
          <Label htmlFor="rep_identification">CPF/CNPJ do representante</Label>
          <Input id="rep_identification" {...register("rep_identification")} />
        </div>
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
        <div className="space-y-1">
          <Label htmlFor="rep_state">Estado</Label>
          <Input id="rep_state" maxLength={2} {...register("rep_state")} />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="rep_city">Cidade</Label>
        <Input id="rep_city" {...register("rep_city")} />
      </div>

      <div className="space-y-1">
        <Label htmlFor="rep_street">Endereço</Label>
        <Input id="rep_street" {...register("rep_street")} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="rep_region">Bairro</Label>
          <Input id="rep_region" {...register("rep_region")} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="rep_postal_code">CEP</Label>
          <Input id="rep_postal_code" {...register("rep_postal_code")} />
        </div>
      </div>
    </fieldset>
  );
}
