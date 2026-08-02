import * as React from "react";

import { FilterBar } from "@/components/domain/FilterBar";
import type { FilterFieldDef } from "@/components/domain/types";

export interface ListPageLayoutProps {
  title: string;
  /** Botões do canto direito do cabeçalho (export, novo, toggles de visão). */
  actions: React.ReactNode;
  /** Ao lado do título (ex.: seletor de visão rápida). */
  headerExtras?: React.ReactNode;
  /** Painel de indicadores entre o cabeçalho e os filtros (recolhível fica a cargo
   * do próprio painel, ex.: LawsuitStatsPanel). */
  dashboard?: React.ReactNode;
  filterFields: FilterFieldDef[];
  /** A listagem em si: DataTable, EmptyState ou visão agrupada. */
  children: React.ReactNode;
}

/** Casca comum das telas de listagem (spec 030, alvo 2): cabeçalho com ações +
 * dashboard + barra de filtros + conteúdo — o que as páginas de contatos (019) e
 * processos (027) repetiam. */
export function ListPageLayout({
  title,
  actions,
  headerExtras,
  dashboard,
  filterFields,
  children,
}: ListPageLayoutProps): JSX.Element {
  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-primary">{title}</h1>
          {headerExtras}
        </div>
        <div className="flex gap-2">{actions}</div>
      </div>
      {dashboard}
      <FilterBar fields={filterFields} />
      {children}
    </div>
  );
}
