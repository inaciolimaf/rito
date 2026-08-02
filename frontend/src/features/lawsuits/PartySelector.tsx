import { X } from "lucide-react";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Label } from "@/components/ui/label";

export const PARTY_POLES = ["ATIVO", "PASSIVO", "CONTRARIA", "TERCEIRO"] as const;
export type PartyPole = (typeof PARTY_POLES)[number];

export const PARTY_POLE_LABELS: Record<PartyPole, string> = {
  ATIVO: "Polo ativo",
  PASSIVO: "Polo passivo",
  CONTRARIA: "Parte contrária",
  TERCEIRO: "Terceiro",
};

export interface PartyFormValue {
  customer_id: string;
  label: string;
  pole: PartyPole;
  is_client: boolean;
}

export interface PartySelectorProps {
  value: PartyFormValue[];
  onChange: (value: PartyFormValue[]) => void;
  onSearch: (query: string) => Promise<EntityOption[]>;
}

/** Seleção de partes do processo (spec 023 §6): dois campos — "Adicionar partes
 * envolvidas" (nasce ATIVO/cliente) e "Partes contrárias" (nasce CONTRARIA/não cliente,
 * regra 4) — e chips com nome + polo editável + remover (regra 2: a mesma pessoa pode
 * aparecer em polos distintos, então a chave de deduplicação é customer_id + polo). */
export function PartySelector({ value, onChange, onSearch }: PartySelectorProps): JSX.Element {
  function addParty(option: EntityOption, pole: PartyPole, isClient: boolean): void {
    const exists = value.some((item) => item.customer_id === option.id && item.pole === pole);
    if (!exists) {
      onChange([
        ...value,
        { customer_id: option.id, label: option.label, pole, is_client: isClient },
      ]);
    }
  }

  function removeParty(target: PartyFormValue): void {
    onChange(
      value.filter(
        (item) => !(item.customer_id === target.customer_id && item.pole === target.pole),
      ),
    );
  }

  function changePole(target: PartyFormValue, pole: PartyPole): void {
    const conflict = value.some(
      (item) =>
        item.customer_id === target.customer_id && item.pole === pole && item.pole !== target.pole,
    );
    if (conflict) return;
    onChange(
      value.map((item) =>
        item.customer_id === target.customer_id && item.pole === target.pole
          ? { ...item, pole, is_client: pole === "CONTRARIA" ? false : item.is_client }
          : item,
      ),
    );
  }

  // Regra 7: exibição por polo (ordem de PARTY_POLES) e, dentro do polo, alfabética.
  const ordered = [...value].sort(
    (a, b) =>
      PARTY_POLES.indexOf(a.pole) - PARTY_POLES.indexOf(b.pole) || a.label.localeCompare(b.label),
  );

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <Label htmlFor="party-involved">Adicionar partes envolvidas</Label>
        <EntityPicker
          value={[]}
          onChange={(next) => {
            const option = next[next.length - 1];
            if (option) addParty(option, "ATIVO", true);
          }}
          onSearch={onSearch}
          label="Adicionar partes envolvidas"
          placeholder="Buscar contato..."
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="party-opposing">Partes contrárias</Label>
        <EntityPicker
          value={[]}
          onChange={(next) => {
            const option = next[next.length - 1];
            if (option) addParty(option, "CONTRARIA", false);
          }}
          onSearch={onSearch}
          label="Partes contrárias"
          placeholder="Buscar contato..."
        />
      </div>

      {ordered.length > 0 && (
        <ul className="space-y-1" aria-label="Partes selecionadas">
          {ordered.map((party) => (
            <li
              key={`${party.customer_id}-${party.pole}`}
              className="flex items-center gap-2 rounded bg-surface-muted px-2 py-1 text-sm text-primary"
            >
              <span className="flex-1">{party.label}</span>
              <select
                aria-label={`Polo de ${party.label}`}
                className="rounded border border-default bg-surface px-1 py-0.5 text-xs text-primary"
                value={party.pole}
                onChange={(event) => changePole(party, event.target.value as PartyPole)}
              >
                {PARTY_POLES.map((pole) => (
                  <option key={pole} value={pole}>
                    {PARTY_POLE_LABELS[pole]}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => removeParty(party)}
                aria-label={`Remover ${party.label}`}
                className="text-muted hover:text-danger"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
