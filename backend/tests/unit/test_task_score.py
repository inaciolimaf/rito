import pytest

from app.domain.task_types.models import TaskComplexity, TaskDuration
from app.domain.task_types.score import REWARD_MATRIX, suggest_reward

# A matriz completa da spec 031 §4 — as 25 combinações, linha a linha.
_EXPECTED = {
    TaskComplexity.SIMPLES: [5, 8, 15, 30, 60],
    TaskComplexity.MEDIA: [10, 15, 30, 60, 120],
    TaskComplexity.MEDIA_ALTA: [15, 25, 45, 90, 180],
    TaskComplexity.ALTA: [20, 35, 70, 150, 280],
    TaskComplexity.ALTISSIMA: [30, 50, 100, 200, 400],
}
_DURATIONS = [
    TaskDuration.MIN_8,
    TaskDuration.MIN_15,
    TaskDuration.MIN_30,
    TaskDuration.HOUR_1,
    TaskDuration.HOUR_2_PLUS,
]


@pytest.mark.parametrize(
    ("complexity", "duration"),
    [(c, d) for c in TaskComplexity for d in TaskDuration],
)
def test_matriz_completa(complexity: TaskComplexity, duration: TaskDuration) -> None:
    expected = _EXPECTED[complexity][_DURATIONS.index(duration)]
    assert suggest_reward(complexity, duration) == expected


def test_ancoragem_nos_exemplos_oficiais() -> None:
    # Os dois exemplos do ADVBOX que ancoram a matriz: simples/15min = 8, alta/1h = 150.
    assert suggest_reward(TaskComplexity.SIMPLES, TaskDuration.MIN_15) == 8
    assert suggest_reward(TaskComplexity.ALTA, TaskDuration.HOUR_1) == 150
    assert len(REWARD_MATRIX) == 25
