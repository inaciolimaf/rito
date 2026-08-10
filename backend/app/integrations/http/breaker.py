"""Circuit breaker por host (spec 041, regra 5).

Fechado → (N falhas consecutivas) → aberto → (após reset) → meio-aberto → uma
requisição de prova: sucesso fecha, falha reabre. O relógio é injetável para os
testes não dormirem (CLAUDE.md §3 — nunca `sleep` em teste).

O estado é em memória, por processo: cada worker tem o seu, o que é aceitável —
o breaker protege contra host fora do ar, e N workers significam no máximo
N provas por janela de reset. O rate limit (que precisa ser exato) é o que mora
no Redis.
"""

import time
from collections.abc import Callable
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        reset_after_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_after_s = reset_after_s
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    @property
    def state(self) -> CircuitState:
        return self._state

    def allow(self) -> bool:
        """True se a requisição pode sair. Aberto dentro da janela: False sem rede."""
        if self._state is CircuitState.OPEN:
            if self._clock() - self._opened_at < self._reset_after_s:
                return False
            self._state = CircuitState.HALF_OPEN
            self._probe_in_flight = False
        if self._state is CircuitState.HALF_OPEN:
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True
        return True

    def on_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._probe_in_flight = False

    def on_failure(self) -> None:
        self._probe_in_flight = False
        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
