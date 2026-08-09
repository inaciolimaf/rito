import { apiRequest } from "@/lib/api";

/** Camada de API da spec 039 — metas, ranking e painel Taskscore. */

export interface ClosureGoalItem {
  action_group_id: string;
  action_group_name: string;
  monthly_target: number;
}

export interface ScoreSummary {
  user_id: string;
  user_name: string;
  points: number;
  tasks_completed: number;
  on_time: number;
  late: number;
  assigned: number;
  engagement: number | null;
  points_goal: number | null;
  /** null = sem meta → a UI mostra "—" (regra 3). */
  goal_pct: number | null;
}

export interface MyScoreResponse {
  period: string;
  summary: ScoreSummary;
}

export interface RankingResponse {
  period: string;
  sort: string;
  items: ScoreSummary[];
}

export interface ScoreChartResponse {
  granularity: "monthly" | "daily";
  current: number;
  previous: number;
  goal: number | null;
  days: { label: string; value: number }[];
}

export type RankingSort = "points" | "volume" | "late" | "engagement";

export async function getClosureGoals(): Promise<ClosureGoalItem[]> {
  const body = await apiRequest<{ items: ClosureGoalItem[] }>("/api/v1/goals/closures");
  return body.items;
}

export async function putClosureGoals(
  items: { action_group_id: string; monthly_target: number }[],
): Promise<ClosureGoalItem[]> {
  const body = await apiRequest<{ items: ClosureGoalItem[] }>("/api/v1/goals/closures", {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
  return body.items;
}

export async function setPointsGoal(userId: string, pointsGoal: number | null): Promise<void> {
  await apiRequest(`/api/v1/users/${userId}/points-goal`, {
    method: "PUT",
    body: JSON.stringify({ points_goal: pointsGoal }),
  });
}

export async function getMyScore(period?: string): Promise<MyScoreResponse> {
  const query = period ? `?period=${encodeURIComponent(period)}` : "";
  return apiRequest<MyScoreResponse>(`/api/v1/taskscore/me${query}`);
}

export async function getRanking(sort: RankingSort, period?: string): Promise<RankingResponse> {
  const params = new URLSearchParams({ sort });
  if (period) params.set("period", period);
  return apiRequest<RankingResponse>(`/api/v1/taskscore/ranking?${params.toString()}`);
}

export async function getScoreChart(
  granularity: "monthly" | "daily",
  userId?: string,
): Promise<ScoreChartResponse> {
  const params = new URLSearchParams({ granularity });
  if (userId) params.set("user_id", userId);
  return apiRequest<ScoreChartResponse>(`/api/v1/taskscore/chart?${params.toString()}`);
}
