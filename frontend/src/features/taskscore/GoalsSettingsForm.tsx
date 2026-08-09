import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getClosureGoals, putClosureGoals, setPointsGoal } from "@/features/taskscore/api";
import { listUsers } from "@/features/users/api";

/** Formulário de metas (spec 039 §6) — duas seções: fechamentos por grupo de ação
 * (upsert em lote) e pontos por colaborador (endpoint leve por usuário). */
export function GoalsSettingsForm(): JSX.Element {
  const queryClient = useQueryClient();
  const { data: goals } = useQuery({ queryKey: ["closure-goals"], queryFn: getClosureGoals });
  const { data: users } = useQuery({
    queryKey: ["users", "goals"],
    queryFn: () => listUsers({ status: "active", limit: 100 }),
  });

  const [targets, setTargets] = React.useState<Record<string, string>>({});
  const [pointGoals, setPointGoals] = React.useState<Record<string, string>>({});
  const [feedback, setFeedback] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (goals) {
      setTargets(
        Object.fromEntries(
          goals.map((item) => [item.action_group_id, String(item.monthly_target)]),
        ),
      );
    }
  }, [goals]);

  React.useEffect(() => {
    if (users) {
      setPointGoals(
        Object.fromEntries(
          users.items.map((item) => [
            item.id,
            item.points_goal === null ? "" : String(item.points_goal),
          ]),
        ),
      );
    }
  }, [users]);

  const saveClosures = useMutation({
    mutationFn: () =>
      putClosureGoals(
        (goals ?? []).map((item) => ({
          action_group_id: item.action_group_id,
          monthly_target: Number(targets[item.action_group_id] ?? "0") || 0,
        })),
      ),
    onSuccess: async () => {
      setFeedback("Metas de fechamento salvas.");
      await queryClient.invalidateQueries({ queryKey: ["closure-goals"] });
    },
  });

  const savePointGoal = useMutation({
    mutationFn: (userId: string) => {
      const raw = (pointGoals[userId] ?? "").trim();
      return setPointsGoal(userId, raw === "" ? null : Number(raw));
    },
    onSuccess: async () => {
      setFeedback("Meta de pontos salva.");
      await queryClient.invalidateQueries({ queryKey: ["users", "goals"] });
    },
  });

  return (
    <div className="space-y-8">
      <section aria-label="Metas de fechamento" className="space-y-3">
        <h2 className="text-base font-semibold text-primary">Fechamentos por grupo de ação</h2>
        <p className="text-sm text-muted">
          Meta mensal de processos fechados por grupo — alimenta o widget da tela de processos.
        </p>
        <ul className="space-y-2">
          {(goals ?? []).map((item) => (
            <li key={item.action_group_id} className="flex items-center gap-3">
              <span className="w-56 truncate text-sm text-primary">{item.action_group_name}</span>
              <Input
                type="number"
                min={0}
                className="w-28"
                aria-label={`Meta de ${item.action_group_name}`}
                value={targets[item.action_group_id] ?? "0"}
                onChange={(event) =>
                  setTargets((current) => ({
                    ...current,
                    [item.action_group_id]: event.target.value,
                  }))
                }
              />
            </li>
          ))}
        </ul>
        <Button
          type="button"
          onClick={() => saveClosures.mutate()}
          disabled={saveClosures.isPending}
        >
          Salvar metas de fechamento
        </Button>
      </section>

      <section aria-label="Metas de pontos" className="space-y-3">
        <h2 className="text-base font-semibold text-primary">Pontos por colaborador</h2>
        <p className="text-sm text-muted">
          Meta mensal de Taskscore. Vazio = sem meta (o painel mostra "—").
        </p>
        <ul className="space-y-2">
          {(users?.items ?? []).map((item) => (
            <li key={item.id} className="flex items-center gap-3">
              <span className="w-56 truncate text-sm text-primary">{item.name}</span>
              <Input
                type="number"
                min={0}
                className="w-28"
                aria-label={`Meta de pontos de ${item.name}`}
                value={pointGoals[item.id] ?? ""}
                onChange={(event) =>
                  setPointGoals((current) => ({ ...current, [item.id]: event.target.value }))
                }
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => savePointGoal.mutate(item.id)}
                disabled={savePointGoal.isPending}
              >
                Salvar
              </Button>
            </li>
          ))}
        </ul>
      </section>

      {feedback && (
        <p role="status" className="text-sm text-accent">
          {feedback}
        </p>
      )}
    </div>
  );
}
