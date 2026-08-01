import * as React from "react";
import { useSearchParams } from "react-router-dom";

import type { FilterFieldDef } from "@/components/domain/types";

export type FilterValues = Record<string, string | string[] | undefined>;

export interface UseFiltersResult {
  values: FilterValues;
  setValue: (key: string, value: string | string[] | undefined) => void;
  clear: () => void;
  activeCount: number;
}

const MULTI_SEPARATOR = ",";

/** URL como fonte de verdade (regra 2): recarregar a página preserva o estado, o link é
 * compartilhável. `FilterBar` usa este hook — qualquer feature pode usá-lo direto também. */
export function useFilters(fields: FilterFieldDef[]): UseFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams();

  const values = React.useMemo<FilterValues>(() => {
    const result: FilterValues = {};
    for (const field of fields) {
      const raw = searchParams.get(field.key);
      if (raw === null || raw === "") {
        continue;
      }
      result[field.key] = field.type === "multiselect" ? raw.split(MULTI_SEPARATOR) : raw;
    }
    return result;
  }, [fields, searchParams]);

  const setValue = React.useCallback(
    (key: string, value: string | string[] | undefined) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) {
            next.delete(key);
          } else if (Array.isArray(value)) {
            next.set(key, value.join(MULTI_SEPARATOR));
          } else {
            next.set(key, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const clear = React.useCallback(() => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        for (const field of fields) {
          next.delete(field.key);
        }
        return next;
      },
      { replace: true },
    );
  }, [fields, setSearchParams]);

  const activeCount = Object.keys(values).length;

  return { values, setValue, clear, activeCount };
}
