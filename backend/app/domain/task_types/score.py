"""Matriz de pontuação Taskscore (spec 031 §4): complexidade × tempo médio → pontos
sugeridos. Determinística e pura (sem banco, sem framework) — a sugestão é editável,
vence o valor informado (regra 2)."""

from app.domain.task_types.models import TaskComplexity, TaskDuration

# Ancorada nos dois exemplos oficiais do ADVBOX: simples/15 min = 8 pts, alta/1 h = 150 pts.
_REWARDS: tuple[tuple[int, ...], ...] = (
    #         8min  15min 30min  1h   +2h
    (5, 8, 15, 30, 60),  # SIMPLES
    (10, 15, 30, 60, 120),  # MEDIA
    (15, 25, 45, 90, 180),  # MEDIA_ALTA
    (20, 35, 70, 150, 280),  # ALTA
    (30, 50, 100, 200, 400),  # ALTISSIMA
)

REWARD_MATRIX: dict[tuple[TaskComplexity, TaskDuration], int] = {
    (complexity, duration): _REWARDS[complexity_index][duration_index]
    for complexity_index, complexity in enumerate(TaskComplexity)
    for duration_index, duration in enumerate(TaskDuration)
}


def suggest_reward(complexity: TaskComplexity, duration: TaskDuration) -> int:
    return REWARD_MATRIX[(complexity, duration)]
