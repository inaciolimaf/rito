import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ALL_TIMELINE_KINDS } from "@/features/lawsuits/TimelineFilters";
import type { TimelineKind } from "@/features/lawsuits/api";
import { getMyPreferences, putMyPreferences } from "@/features/users/api";

const PREFS_KEY = "lawsuit_timeline_kinds";

function isTimelineKind(value: unknown): value is TimelineKind {
  return typeof value === "string" && (ALL_TIMELINE_KINDS as string[]).includes(value);
}

/** Seleção de tipos da timeline persistida por usuário (spec 026, regra 7):
 * lê de `/users/me/preferences` (default: todos os tipos) e grava otimista. */
export function useTimelineKinds(): {
  kinds: TimelineKind[];
  setKinds: (kinds: TimelineKind[]) => void;
  isLoading: boolean;
} {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["me", "preferences"],
    queryFn: getMyPreferences,
  });

  const stored = data?.preferences[PREFS_KEY];
  const kinds: TimelineKind[] = Array.isArray(stored)
    ? stored.filter(isTimelineKind)
    : ALL_TIMELINE_KINDS;

  const mutation = useMutation({
    mutationFn: (next: TimelineKind[]) => putMyPreferences({ [PREFS_KEY]: next }),
    onSuccess: (response) => {
      queryClient.setQueryData(["me", "preferences"], response);
    },
  });

  return { kinds, setKinds: (next) => mutation.mutate(next), isLoading };
}
