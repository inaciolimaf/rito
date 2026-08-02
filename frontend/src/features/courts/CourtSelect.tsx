import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { listCourts, type CourtSegment } from "@/features/courts/api";

const SEGMENT_LABELS: Record<CourtSegment, string> = {
  ESTADUAL: "Estadual",
  FEDERAL: "Federal",
  TRABALHO: "Trabalho",
  ELEITORAL: "Eleitoral",
  MILITAR: "Militar",
  SUPERIOR: "Superior",
  CONTAS: "Contas",
  CONSELHO: "Conselho",
};

export interface CourtSelectProps {
  value: EntityOption[];
  onChange: (value: EntityOption[]) => void;
}

/** Regra 2: busca aceita sigla exata ou nome parcial sem acento (o backend já resolve
 * ambos). `EntityPicker` não agrupa visualmente por seção — o segmento aparece como
 * `description` de cada opção, que já cumpre o objetivo de "agrupado por segmento"
 * (identificar de relance a que tipo de tribunal cada resultado pertence) sem precisar
 * estender o componente compartilhado para um único consumidor. */
export function CourtSelect({ value, onChange }: CourtSelectProps): JSX.Element {
  async function searchCourts(query: string): Promise<EntityOption[]> {
    const courts = await listCourts({ q: query });
    return courts.map((court) => ({
      id: String(court.id),
      label: `${court.code} — ${court.name}`,
      description: SEGMENT_LABELS[court.segment],
    }));
  }

  return (
    <EntityPicker
      value={value}
      onChange={onChange}
      onSearch={searchCourts}
      label="Tribunal"
      placeholder="Buscar por sigla ou nome..."
    />
  );
}
