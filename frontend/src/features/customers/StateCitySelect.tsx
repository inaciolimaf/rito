import { useQuery } from "@tanstack/react-query";
import type { Control, FieldValues, Path, PathValue, UseFormSetValue } from "react-hook-form";
import { Controller } from "react-hook-form";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Label } from "@/components/ui/label";
import { listCities, listStates } from "@/features/locations/api";

export interface StateCitySelectProps<TValues extends FieldValues> {
  control: Control<TValues>;
  setValue: UseFormSetValue<TValues>;
  stateName: Path<TValues>;
  cityName: Path<TValues>;
  stateValue: string;
  cityValue: string;
}

/** Regra 8: cidade só é selecionável depois do estado; trocar o estado limpa a cidade. UF
 * é um `<select>` (27 opções, lista fixa); cidade usa `EntityPicker` (IBGE tem milhares de
 * municípios por estado, não cabe num `<select>` só). */
export function StateCitySelect<TValues extends FieldValues>({
  control,
  setValue,
  stateName,
  cityName,
  stateValue,
  cityValue,
}: StateCitySelectProps<TValues>): JSX.Element {
  const { data: states = [] } = useQuery({ queryKey: ["states"], queryFn: listStates });

  async function searchCities(query: string): Promise<EntityOption[]> {
    if (!stateValue) return [];
    const cities = await listCities(stateValue, query);
    return cities.map((city) => ({ id: String(city.ibge_code), label: city.name }));
  }

  const cityOption: EntityOption[] = cityValue ? [{ id: cityValue, label: cityValue }] : [];

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="space-y-1">
        <Label htmlFor="state">Estado</Label>
        <Controller
          control={control}
          name={stateName}
          render={({ field }) => (
            <select
              id="state"
              className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              value={field.value ?? ""}
              onChange={(event) => {
                field.onChange(event.target.value);
                setValue(cityName, "" as PathValue<TValues, Path<TValues>>, {
                  shouldDirty: true,
                });
              }}
            >
              <option value="">Selecione</option>
              {states.map((state) => (
                <option key={state.code} value={state.code}>
                  {state.name}
                </option>
              ))}
            </select>
          )}
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="city">Cidade</Label>
        {stateValue ? (
          <EntityPicker
            value={cityOption}
            onChange={(next) =>
              setValue(cityName, (next[0]?.label ?? "") as PathValue<TValues, Path<TValues>>, {
                shouldDirty: true,
              })
            }
            onSearch={searchCities}
            label="Cidade"
            placeholder="Buscar cidade..."
          />
        ) : (
          <p className="text-sm text-muted">Selecione um estado primeiro.</p>
        )}
      </div>
    </div>
  );
}
