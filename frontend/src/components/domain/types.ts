import type * as React from "react";

/** Contrato de listagem (spec 007, seção 5) — toda feature de listagem segue este formato. */
export interface ListResponse<T> {
  items: T[];
  next_cursor: string | null;
  total: number;
}

export interface DataTableSort {
  field: string;
  order: "asc" | "desc";
}

export interface DataTableColumn<T> {
  id: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  sortable?: boolean;
  className?: string;
}

export interface DataTablePagination {
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  onNextPage: () => void;
  onPreviousPage: () => void;
}

export type FilterFieldType = "text" | "select" | "multiselect" | "date" | "boolean";

export interface FilterFieldOption {
  value: string;
  label: string;
}

export interface FilterFieldDef {
  key: string;
  label: string;
  type: FilterFieldType;
  options?: FilterFieldOption[];
}

export interface EntityOption {
  id: string;
  label: string;
  description?: string;
}
