"""Motor de automação: gatilho → ação → tempo (spec 092).

O que a 038 fazia num caso só ("mudou de etapa, cria as tarefas do fluxo"), aqui é
configurável pelo escritório. O motor é chamado de dentro dos use cases que já existem —
concluir tarefa, criar processo, mudar etapa — por uma função só: `emit`.

Três decisões guiam o arquivo inteiro:

- **Uma execução sabe onde parou.** `next_position` mais `next_action_at`/`waiting_on_id`
  são o estado; retomar é reler isso, não recomeçar.
- **Passo pulado é passo registrado** (regra 6). "Por que a tarefa não foi criada?" é a
  pergunta que chega ao suporte, e sem o registro do pulo ela não tem resposta.
- **A cadeia tem fim** (regra 7). Uma automação não se dispara, e o evento carrega a
  profundidade consigo — duas automações se alimentando em pingue-pongue param no décimo.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import add_business_days
from app.domain.automations.actions import ConditionNotMet
from app.domain.automations.conditions import evaluate
from app.domain.automations.decision import DecisionRunner, branch_owner_map
from app.domain.automations.models import (
    ActionKind,
    Automation,
    AutomationAction,
    AutomationRun,
    AutomationRunStep,
    DelayKind,
    RunStatus,
    StepStatus,
    TriggerKind,
)
from app.domain.users.models import User
from app.domain.workflows.repository import HolidayRepository

# Regra 7: o teto da cadeia. Dez é folgado para o encadeamento legítimo (intimação vira
# tarefa, tarefa concluída move a etapa, etapa aplica o fluxo) e curto o bastante para um
# laço não custar nada além de um registro.
MAX_CHAIN_DEPTH = 10

# Regra 13: uma automação com mais de 20 passos deixou de ser regra e virou programa —
# e programa se escreve em outro lugar.
MAX_ACTIONS = 20

# De quanto em quanto o `wait_condition` volta a olhar. Condição que ninguém satisfaz não
# pode virar consulta de minuto em minuto.
CONDITION_POLL = timedelta(hours=1)


class AutomationLimitError(Exception):
    """Regra 13: 21ª ação → 422."""


@dataclass
class SimulatedStep:
    """O que aconteceria — sem que nada aconteça (regra 10)."""

    position: int
    action_kind: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    scheduled_for: date | None = None


class AutomationEngine:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        now: datetime | None = None,
        webhook_sender: Any = None,
        ai_runner: Any = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.holidays = HolidayRepository(session)
        # Spec 093: injetado nos testes (nenhuma chamada real de rede) e montado no
        # lifespan em produção. `None` faz a ação usar o transporte padrão.
        self.webhook_sender = webhook_sender
        # Spec 094: injetado nos testes; em produção é montado sob demanda (ver
        # `ai_runner`), porque o motor é chamado de dentro de use cases do domínio, que
        # não têm — e não devem ter — acesso ao provider do app.
        self._ai_runner = ai_runner
        self._now = now
        self._holiday_cache: set[date] | None = None

    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    @property
    def ai_runner(self) -> Any:
        """O runner da 081, montado só quando um nó de decisão existir de fato.

        Sem isto, a decisão por IA só funcionaria pela rota de simulação: os gatilhos
        nascem dentro de `complete()`, `create()` e `change_stage()`, que não conhecem
        `app.state`. Montar sob demanda mantém o custo em zero para as automações que
        não usam IA — que são a maioria.
        """
        if self._ai_runner is None:
            from app.domain.ai.service import AiRunner
            from app.integrations.openrouter.factory import create_llm_provider

            self._ai_runner = AiRunner(self.session, self.tenant_id, create_llm_provider())
        return self._ai_runner

    # ------------------------------------------------------------------ emitir

    async def emit(
        self,
        trigger_kind: str,
        *,
        payload: dict[str, Any],
        subject_type: str | None = None,
        subject_id: uuid.UUID | None = None,
        chain_depth: int = 0,
        source_automation_id: uuid.UUID | None = None,
    ) -> list[AutomationRun]:
        """Ponto de entrada único. Chamado de dentro dos use cases do domínio.

        Sem automação configurada para o gatilho, isto é um SELECT indexado e nada mais —
        é por isso que dá para chamar de dentro de `complete()` sem pesar.
        """
        if chain_depth >= MAX_CHAIN_DEPTH:
            return []
        candidatas = await self._matching(trigger_kind, payload)
        execucoes: list[AutomationRun] = []
        for automation in candidatas:
            # Regra 7: uma automação não dispara a si mesma. O caso não é hipotético —
            # "tarefa concluída cria tarefa" se auto-alimentaria na primeira conclusão.
            if source_automation_id is not None and automation.id == source_automation_id:
                continue
            run = AutomationRun(
                tenant_id=self.tenant_id,
                automation_id=automation.id,
                trigger_payload=payload,
                subject_type=subject_type,
                subject_id=subject_id,
                chain_depth=chain_depth,
                status=RunStatus.RUNNING.value,
                next_position=0,
            )
            self.session.add(run)
            await self.session.flush()
            await self.advance(run, automation=automation)
            execucoes.append(run)
        return execucoes

    async def _matching(self, trigger_kind: str, payload: dict[str, Any]) -> list[Automation]:
        stmt = select(Automation).where(
            Automation.trigger_kind == trigger_kind, Automation.is_active.is_(True)
        )
        automations = list((await self.session.scalars(stmt)).all())
        # Regra 2: `trigger_config` é um filtro de igualdade sobre o payload — "tarefa
        # concluída" pode valer só para um tipo de tarefa.
        return [
            automation
            for automation in automations
            if _config_matches(automation.trigger_config or {}, payload)
        ]

    # ----------------------------------------------------------------- executar

    async def advance(
        self, run: AutomationRun, *, automation: Automation | None = None
    ) -> AutomationRun:
        """Executa da posição atual até o fim, um passo que espere, ou uma falha."""
        if automation is None:
            automation = await self.session.get(Automation, run.automation_id)
        assert automation is not None
        autor = await self.session.get(User, automation.created_by)
        if autor is None:  # pragma: no cover - FK garante
            return await self._fail(run, "Autor da automação não existe mais.")

        acoes = await self._actions_of(automation)
        ja_feitos = await self._steps_of(run)
        # Spec 094: quais posições pertencem a um ramo, e de qual decisão.
        dono_do_ramo = branch_owner_map(acoes)
        for action in acoes:
            if action.position < (run.next_position or 0):
                continue
            # Regra 8: idempotência. Reprocessar não repete o que já rodou.
            if action.position in ja_feitos:
                continue

            pertence = dono_do_ramo.get(action.position)
            if pertence is not None:
                decisao_pos, nome_do_ramo = pertence
                escolhido = (run.scratch or {}).get(str(decisao_pos))
                if escolhido != nome_do_ramo:
                    # Ramo não escolhido: pula e REGISTRA (mesma razão da regra 6 da
                    # 092 — o que não rodou precisa ser explicável).
                    await self._record_step(
                        run,
                        action,
                        StepStatus.SKIPPED,
                        detail={"branch": nome_do_ramo, "chosen": escolhido},
                    )
                    run.next_position = action.position + 1
                    continue

            if not evaluate(action.condition, run.trigger_payload or {}):
                # Regra 6: pulado é registrado. O suporte precisa poder responder
                # "por que a tarefa não foi criada?".
                await self._record_step(
                    run, action, StepStatus.SKIPPED, detail={"condition": action.condition}
                )
                run.next_position = action.position + 1
                continue

            espera = await self._wait_for(run, action)
            if espera is not None:
                run.status = RunStatus.WAITING.value
                run.next_position = action.position
                run.next_action_at = espera
                await self.session.flush()
                return run

            if action.action_kind == ActionKind.LLM_DECISION.value:
                # Spec 094: a decisão NUNCA levanta — pior caso, cai no ramo padrão.
                # Por isso ela roda fora do try/except das outras ações: não há falha
                # de decisão para tratar, só uma escolha registrada.
                outcome = await DecisionRunner(self).decide(
                    run=run, action=action, automation=automation, actor=autor
                )
                run.scratch = {**(run.scratch or {}), str(action.position): outcome.branch}
                await self._record_step(
                    run,
                    action,
                    StepStatus.DONE,
                    detail={
                        "branch": outcome.branch,
                        "confidence": outcome.confidence,
                        "fell_back": outcome.fell_back,
                    },
                )
                run.actions_completed += 1
                run.next_position = action.position + 1
                await self.session.flush()
                continue

            try:
                # SAVEPOINT pelo mesmo motivo da 084: parte das validações só falha no
                # BANCO (FK, constraint), e sem ele a transação abortada levaria junto o
                # registro da própria falha — que é o que o usuário precisa ler.
                async with self.session.begin_nested():
                    detalhe = await self._execute(run, action, automation=automation, actor=autor)
            except ConditionNotMet:
                # `wait_condition` não satisfeita não é falha: a automação "quando o
                # processo for arquivado, avise" pode esperar meses, e é para isso que
                # ela existe.
                run.status = RunStatus.WAITING.value
                run.next_position = action.position
                run.next_action_at = self.now() + CONDITION_POLL
                await self.session.flush()
                return run
            except Exception as exc:  # noqa: BLE001 - erro do domínio vira registro
                # Regra 9: a falha interrompe e fica registrada; o que já rodou permanece.
                await self._record_step(
                    run, action, StepStatus.FAILED, error=f"{type(exc).__name__}: {exc}"
                )
                return await self._fail(run, f"{type(exc).__name__}: {exc}")

            await self._record_step(run, action, StepStatus.DONE, detail=detalhe)
            run.actions_completed += 1
            run.next_position = action.position + 1
            if detalhe.get("created_post_id"):
                run.waiting_on_id = uuid.UUID(str(detalhe["created_post_id"]))
            await self.session.flush()

        run.status = RunStatus.DONE.value
        run.next_position = None
        run.next_action_at = None
        run.finished_at = self.now()
        await self.session.flush()
        return run

    async def _wait_for(self, run: AutomationRun, action: AutomationAction) -> datetime | None:
        """Quando este passo pode rodar. `None` = agora."""
        ja_esperou = run.status == RunStatus.WAITING.value and run.next_position == action.position
        if action.delay_kind == DelayKind.IMMEDIATE.value:
            return None
        if action.delay_kind == DelayKind.AFTER_PREVIOUS.value:
            # Regra 4: encadeia de verdade — só segue quando a tarefa criada pelo passo
            # anterior estiver concluída. É o caso de "protocolar" depois de "revisar".
            if run.waiting_on_id is None:
                return None
            if await self._post_completed(run.waiting_on_id):
                return None
            # Sem prazo: quem acorda esta execução é o gatilho de conclusão da tarefa.
            return self.now() + CONDITION_POLL
        if ja_esperou and (run.next_action_at is None or run.next_action_at <= self.now()):
            return None
        if action.delay_kind == DelayKind.BUSINESS_DAYS.value:
            # Regra 5: dias úteis com os feriados do banco — o mesmo cálculo da 040.
            alvo = add_business_days(
                self.now().date(), int(action.delay_value or 0), await self._holidays()
            )
        else:
            alvo = self.now().date() + timedelta(days=int(action.delay_value or 0))
        return datetime.combine(alvo, self.now().timetz())

    async def _execute(
        self,
        run: AutomationRun,
        action: AutomationAction,
        *,
        automation: Automation,
        actor: User,
    ) -> dict[str, Any]:
        from app.domain.automations.actions import run_action

        return await run_action(
            self,
            run=run,
            action=action,
            automation=automation,
            actor=actor,
        )

    # -------------------------------------------------------------- simulação

    async def simulate(
        self, automation: Automation, payload: dict[str, Any]
    ) -> list[SimulatedStep]:
        """Regra 10: mostra o que aconteceria e NÃO persiste nada.

        A simulação não executa a ação nem em rascunho: um "teste" que grava é a pior
        armadilha possível numa tela chamada Testar.
        """
        passos: list[SimulatedStep] = []
        quando = self.now().date()
        for action in await self._actions_of(automation):
            if not evaluate(action.condition, payload):
                passos.append(
                    SimulatedStep(
                        position=action.position,
                        action_kind=action.action_kind,
                        status=StepStatus.SKIPPED.value,
                        detail={"condition": action.condition},
                    )
                )
                continue
            if action.delay_kind == DelayKind.BUSINESS_DAYS.value:
                quando = add_business_days(
                    quando, int(action.delay_value or 0), await self._holidays()
                )
            elif action.delay_kind == DelayKind.CALENDAR_DAYS.value:
                quando = quando + timedelta(days=int(action.delay_value or 0))
            passos.append(
                SimulatedStep(
                    position=action.position,
                    action_kind=action.action_kind,
                    status=StepStatus.DONE.value,
                    detail=dict(action.action_config or {}),
                    scheduled_for=quando,
                )
            )
        return passos

    # ---------------------------------------------------------------- retomada

    async def resume_due(self, *, limit: int = 100) -> int:
        """Execuções cujo atraso venceu. Chamada pelo worker."""
        stmt = (
            select(AutomationRun)
            .where(
                AutomationRun.status == RunStatus.WAITING.value,
                AutomationRun.next_action_at.is_not(None),
                AutomationRun.next_action_at <= self.now(),
            )
            .order_by(AutomationRun.next_action_at)
            .limit(limit)
        )
        pendentes = list((await self.session.scalars(stmt)).all())
        for run in pendentes:
            await self.advance(run)
        return len(pendentes)

    async def resume_waiting_on(self, post_id: uuid.UUID) -> int:
        """Regra 4: a tarefa foi concluída — quem esperava por ela segue."""
        stmt = select(AutomationRun).where(
            AutomationRun.status == RunStatus.WAITING.value,
            AutomationRun.waiting_on_id == post_id,
        )
        pendentes = list((await self.session.scalars(stmt)).all())
        for run in pendentes:
            run.next_action_at = None
            await self.advance(run)
        return len(pendentes)

    # ----------------------------------------------------------------- apoio

    async def _actions_of(self, automation: Automation) -> list[AutomationAction]:
        stmt = (
            select(AutomationAction)
            .where(AutomationAction.automation_id == automation.id)
            .order_by(AutomationAction.position)
        )
        return list((await self.session.scalars(stmt)).all())

    async def _steps_of(self, run: AutomationRun) -> set[int]:
        stmt = select(AutomationRunStep.position).where(AutomationRunStep.run_id == run.id)
        return set((await self.session.scalars(stmt)).all())

    async def _post_completed(self, post_id: uuid.UUID) -> bool:
        from app.domain.posts.models import PostUser

        stmt = select(PostUser.completed_at).where(PostUser.post_id == post_id)
        linhas = list((await self.session.scalars(stmt)).all())
        return bool(linhas) and all(linha is not None for linha in linhas)

    async def _holidays(self) -> set[date]:
        if self._holiday_cache is None:
            self._holiday_cache = await self.holidays.national_dates()
        return self._holiday_cache

    async def _record_step(
        self,
        run: AutomationRun,
        action: AutomationAction,
        status: StepStatus,
        *,
        detail: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.session.add(
            AutomationRunStep(
                tenant_id=self.tenant_id,
                run_id=run.id,
                position=action.position,
                action_kind=action.action_kind,
                status=status.value,
                detail=detail,
                error=error[:500] if error else None,
            )
        )
        await self.session.flush()

    async def _fail(self, run: AutomationRun, error: str) -> AutomationRun:
        run.status = RunStatus.FAILED.value
        run.error = error[:500]
        run.finished_at = self.now()
        await self.session.flush()
        return run


def _config_matches(config: dict[str, Any], payload: dict[str, Any]) -> bool:
    return all(str(payload.get(chave)) == str(valor) for chave, valor in config.items())


__all__ = [
    "MAX_ACTIONS",
    "MAX_CHAIN_DEPTH",
    "ActionKind",
    "AutomationEngine",
    "AutomationLimitError",
    "SimulatedStep",
    "TriggerKind",
]
