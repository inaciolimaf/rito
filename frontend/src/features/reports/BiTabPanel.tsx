import * as React from "react";

import { FilterBar } from "@/components/domain/FilterBar";
import type { FilterFieldDef } from "@/components/domain/types";
import { BiRefreshIndicator } from "@/features/reports/BiRefreshIndicator";

export interface BiTabPanelProps {
  filterFields: FilterFieldDef[];
  /** A faixa de indicadores do topo — cada aba monta os seus. */
  cards?: React.ReactNode;
  /** Alerta entre os indicadores e o conteúdo (ex.: processos parados, spec 074). */
  alert?: React.ReactNode;
  /** Gráficos e tabelas da aba. */
  children: React.ReactNode;
  /** Defasagem da view materializada (spec 078) — nulo enquanto o dado não chegou. */
  stalenessHint?: string | null;
}

/** Casca comum das abas de BI (refatoração 080, alvo 3): filtros no topo, indicadores,
 * conteúdo e o aviso de defasagem no rodapé — a mesma sequência que as quatro abas
 * (074–077) repetiam à mão, com o risco de uma esquecer o rodapé. */
export function BiTabPanel({
  filterFields,
  cards,
  alert,
  children,
  stalenessHint,
}: BiTabPanelProps): JSX.Element {
  return (
    <div className="space-y-4">
      <FilterBar fields={filterFields} />
      {cards}
      {alert}
      {children}
      {stalenessHint && <BiRefreshIndicator hint={stalenessHint} />}
    </div>
  );
}
