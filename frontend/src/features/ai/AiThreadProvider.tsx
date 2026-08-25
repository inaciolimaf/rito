import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import {
  cancelThread,
  createThread,
  getThread,
  listThreadSteps,
  resumeThread,
  type CreateThreadPayload,
  type StepData,
  type ThreadData,
} from "@/features/ai/threads";

interface AiThreadValue {
  thread: ThreadData | null;
  steps: StepData[];
  isLoading: boolean;
  start: (payload: CreateThreadPayload) => Promise<ThreadData>;
  decide: (approved: boolean, humanInput?: Record<string, unknown>) => Promise<void>;
  cancel: () => Promise<void>;
  reset: () => void;
}

const AiThreadContext = React.createContext<AiThreadValue | null>(null);

/** Estado de uma conversa de agente (spec 082 §7). As features de IA (085+) montam a
 * UI delas em cima disto — nenhuma precisa saber de thread, passo ou retomada. */
export function AiThreadProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [threadId, setThreadId] = React.useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: thread, isLoading } = useQuery({
    queryKey: ["ai-thread", threadId],
    queryFn: () => getThread(threadId!),
    enabled: threadId !== null,
  });
  const { data: steps } = useQuery({
    queryKey: ["ai-thread", threadId, "steps"],
    queryFn: () => listThreadSteps(threadId!),
    enabled: threadId !== null,
  });

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["ai-thread", threadId] }).then(() => undefined);

  const startMutation = useMutation({
    mutationFn: (payload: CreateThreadPayload) => createThread(payload),
    onSuccess: (created) => setThreadId(created.id),
  });
  const decideMutation = useMutation({
    mutationFn: ({
      approved,
      humanInput,
    }: {
      approved: boolean;
      humanInput?: Record<string, unknown>;
    }) => resumeThread(threadId!, approved, humanInput),
    onSuccess: invalidate,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelThread(threadId!),
    onSuccess: invalidate,
  });

  const value = React.useMemo<AiThreadValue>(
    () => ({
      thread: thread ?? null,
      steps: steps?.items ?? [],
      isLoading,
      start: (payload) => startMutation.mutateAsync(payload),
      decide: async (approved, humanInput) => {
        await decideMutation.mutateAsync({ approved, humanInput });
      },
      cancel: async () => {
        await cancelMutation.mutateAsync();
      },
      reset: () => setThreadId(null),
    }),
    [thread, steps, isLoading, startMutation, decideMutation, cancelMutation],
  );

  return <AiThreadContext.Provider value={value}>{children}</AiThreadContext.Provider>;
}

export function useAiThread(): AiThreadValue {
  const value = React.useContext(AiThreadContext);
  if (value === null) {
    throw new Error("useAiThread precisa estar dentro de <AiThreadProvider>.");
  }
  return value;
}
