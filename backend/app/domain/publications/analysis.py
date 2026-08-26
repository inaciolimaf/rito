"""Análise de intimação por IA (spec 086).

A divisão de trabalho aqui é a coisa mais importante da spec: **o modelo lê, o código
conta**. Extrair "prazo de 15 dias úteis" de um texto jurídico é linguagem, e o modelo
faz bem; contar 15 dias úteis pulando feriado é aritmética, e vai para
`deadline.py` — testada em tabela, sem depender de o modelo estar num dia bom.

E nada do que sai daqui é prazo do escritório enquanto um humano não confirmar (regra 1).
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import load_prompt
from app.core.repository import BaseRepository
from app.domain.account.repository import AccountRepository
from app.domain.ai.service import AiRunner
from app.domain.publications.analysis_models import PublicationAnalysis
from app.domain.publications.deadline import compute_deadline
from app.domain.publications.models import Publication
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User
from app.domain.workflows.repository import HolidayRepository
from app.integrations.openrouter.types import Message

logger = logging.getLogger("rito.ai.publications")

FEATURE_KEY = "publication_summary"
FALLBACK_TASK_TYPE_NAME = "Analisar intimação"
# Regra 6: resumo curto — o inteiro teor continua ali do lado.
MAX_SUMMARY_PARAGRAPHS = 3
# Regra 12: estimativa grosseira de tokens para o aviso de custo (≈4 caracteres/token).
CHARS_PER_TOKEN = 4

# Regra 8: o tipo de ato casa com o catálogo do escritório por palavra-chave. Sem
# correspondência, cai no fallback — nunca num tipo "parecido".
ACT_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sentenca": ("sentença", "sentenca"),
    "despacho": ("despacho",),
    "decisao": ("decisão", "decisao", "liminar"),
    "intimacao_prazo": ("contestação", "contestacao", "manifestação", "manifestacao", "prazo"),
    "audiencia": ("audiência", "audiencia"),
    "recurso": ("recurso", "apelação", "apelacao", "agravo"),
    "pericia": ("perícia", "pericia"),
}

_SYSTEM_PROMPT = load_prompt("publication_analysis")


@dataclass(frozen=True)
class ParsedAnalysis:
    """O que o modelo devolveu, já domado: sem data calculada e sem sugestão."""

    summary: str
    act_type: str | None
    requires_action: bool
    deadline_days: int | None
    deadline_kind: str | None
    confidence: float | None
    reasoning: str | None


class AnalysisNotFoundError(Exception):
    """Revisar algo que ninguém analisou → 404."""


def parse_model_output(raw: str | None) -> ParsedAnalysis:
    """Lê o JSON do modelo com desconfiança.

    Modelo às vezes embrulha o JSON em ```json, às vezes devolve texto puro. Nada disso
    pode virar exceção: o pior caso aceitável é uma análise sem prazo (regra 5), nunca
    uma intimação que some da fila porque o parser quebrou.
    """
    texto = (raw or "").strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
    inicio, fim = texto.find("{"), texto.rfind("}")
    payload: dict[str, Any] = {}
    if inicio >= 0 and fim > inicio:
        try:
            candidato = json.loads(texto[inicio : fim + 1])
            payload = candidato if isinstance(candidato, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Análise de intimação veio em formato ilegível.")
    resumo = str(payload.get("summary") or texto or "Não foi possível resumir a intimação.")
    paragrafos = [p for p in resumo.split("\n\n") if p.strip()][:MAX_SUMMARY_PARAGRAPHS]
    dias = payload.get("deadline_days")
    especie = payload.get("deadline_kind")
    confianca = payload.get("confidence")
    return ParsedAnalysis(
        summary="\n\n".join(paragrafos) or resumo,
        act_type=str(payload["act_type"]) if payload.get("act_type") else None,
        requires_action=bool(payload.get("requires_action", False)),
        deadline_days=(
            int(dias) if isinstance(dias, int | float | str) and str(dias).isdigit() else None
        ),
        deadline_kind=str(especie) if especie in ("uteis", "corridos") else None,
        confidence=float(confianca) if isinstance(confianca, int | float) else None,
        reasoning=str(payload["reasoning"]) if payload.get("reasoning") else None,
    )


class PublicationAnalysisRepository(BaseRepository[PublicationAnalysis]):
    model = PublicationAnalysis

    async def get_for_publication(self, publication_id: uuid.UUID) -> PublicationAnalysis | None:
        stmt = select(PublicationAnalysis).where(
            PublicationAnalysis.publication_id == publication_id
        )
        return (await self.session.scalars(stmt)).first()

    async def publications_without_analysis(self, limit: int) -> list[Publication]:
        """Regra 10: a leitura automática processa o que ainda não foi analisado."""
        analisadas = select(PublicationAnalysis.publication_id)
        stmt = (
            select(Publication)
            .where(Publication.is_active.is_(True), Publication.id.not_in(analisadas))
            .order_by(Publication.availability_date.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())


class PublicationAnalysisService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, runner: AiRunner) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.runner = runner
        self.analyses = PublicationAnalysisRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.holidays = HolidayRepository(session)
        self.accounts = AccountRepository(session)

    async def analyze(
        self, publication: Publication, *, user: User | None = None
    ) -> PublicationAnalysis:
        """Regra 13: reanalisar substitui o conteúdo e PRESERVA as correções humanas
        anteriores — elas são o histórico de qualidade do modelo, não rascunho."""
        anterior = await self.analyses.get_for_publication(publication.id)
        response = await self.runner.run(
            feature_key=FEATURE_KEY,
            messages=[
                Message(role="system", content=_SYSTEM_PROMPT),
                Message(role="user", content=_publication_prompt(publication)),
            ],
            user_id=user.id if user else None,
            # Spec 090, alvo 2: a PRIMEIRA análise pode vir do cache — clique duplo,
            # nova tentativa depois de um erro e a varredura automática mandam o mesmo
            # prompt. Já a REanálise é alguém pedindo outra leitura de propósito: pagar
            # de novo é exatamente o que se quer ali.
            use_cache=anterior is None,
        )
        parsed = parse_model_output(response.content)
        feriados = await self.holidays.national_dates()
        calculado = compute_deadline(
            availability_date=publication.availability_date,
            days=parsed.deadline_days,
            kind=parsed.deadline_kind,  # type: ignore[arg-type]
            holidays=feriados,
        )
        task_type_id = await self._suggest_task_type(parsed.act_type)

        analise = anterior
        if analise is None:
            analise = PublicationAnalysis(
                tenant_id=self.tenant_id,
                publication_id=publication.id,
                summary=parsed.summary,
                model=response.model,
            )
            self.session.add(analise)
        elif analise.human_correction is not None:
            analise.previous_corrections = [
                *(analise.previous_corrections or []),
                {
                    "corrected_at": (analise.reviewed_at or datetime.now(UTC)).isoformat(),
                    "correction": analise.human_correction,
                    "model": analise.model,
                },
            ]

        analise.summary = parsed.summary
        analise.act_type = parsed.act_type
        analise.requires_action = parsed.requires_action
        analise.deadline_days = parsed.deadline_days
        analise.deadline_kind = parsed.deadline_kind
        analise.deadline_date = calculado
        analise.deadline_confidence = (
            Decimal(str(round(parsed.confidence, 2))) if parsed.confidence is not None else None
        )
        analise.suggested_task_type_id = task_type_id
        # Regra 9: o responsável já foi resolvido pelas 4 rotas da spec 045.
        analise.suggested_user_id = publication.routed_to
        analise.reasoning = parsed.reasoning
        analise.model = response.model
        analise.reviewed_by = None
        analise.reviewed_at = None
        analise.human_correction = None
        await self.session.flush()
        return analise

    async def review(
        self,
        publication: Publication,
        *,
        user: User,
        approved: bool,
        deadline_date: date | None,
        task_type_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
    ) -> tuple[PublicationAnalysis, uuid.UUID | None]:
        """Regra 1: é AQUI que a sugestão vira prazo — com nome e hora de quem confirmou.

        Devolve a análise e o id da tarefa criada (nulo quando a revisão foi só para
        registrar que não havia o que fazer).
        """
        analise = await self.analyses.get_for_publication(publication.id)
        if analise is None:
            raise AnalysisNotFoundError

        correcao: dict[str, Any] = {}
        if deadline_date is not None and deadline_date != analise.deadline_date:
            correcao["deadline_date"] = {
                "suggested": analise.deadline_date.isoformat() if analise.deadline_date else None,
                "corrected": deadline_date.isoformat(),
            }
        if task_type_id is not None and task_type_id != analise.suggested_task_type_id:
            correcao["task_type_id"] = {
                "suggested": (
                    str(analise.suggested_task_type_id) if analise.suggested_task_type_id else None
                ),
                "corrected": str(task_type_id),
            }
        if user_id is not None and user_id != analise.suggested_user_id:
            correcao["user_id"] = {
                "suggested": str(analise.suggested_user_id) if analise.suggested_user_id else None,
                "corrected": str(user_id),
            }
        if not approved:
            correcao["rejected"] = True

        analise.reviewed_by = user.id
        analise.reviewed_at = datetime.now(UTC)
        # Regra 11: correção vazia é informação também — significa "a IA acertou".
        analise.human_correction = correcao
        await self.session.flush()

        if not approved:
            return analise, None
        post_id = await self._create_task(
            publication,
            user=user,
            deadline_date=deadline_date or analise.deadline_date,
            task_type_id=task_type_id or analise.suggested_task_type_id,
            assignee_id=user_id or analise.suggested_user_id or user.id,
        )
        return analise, post_id

    async def estimate_cost(self, publications: list[Publication]) -> dict[str, Any]:
        """Regra 12: antes de analisar um lote, o escritório vê o tamanho da conta."""
        caracteres = sum(len(item.body or "") for item in publications)
        tokens = caracteres // CHARS_PER_TOKEN + len(publications) * 200
        return {
            "count": len(publications),
            "estimated_prompt_tokens": tokens,
            "note": (
                "Estimativa aproximada: cada análise consome o texto da intimação mais o "
                "prompt de instrução. O custo final aparece no painel de consumo de IA."
            ),
        }

    async def auto_read_enabled(self) -> bool:
        # O RLS já limita ao escritório da sessão — `get_current` é literalmente "a
        # conta deste tenant".
        account = await self.accounts.get_current()
        return bool(account and account.ai_auto_read_publications)

    async def _suggest_task_type(self, act_type: str | None) -> uuid.UUID | None:
        """Regra 8: casa o ato com o catálogo DO ESCRITÓRIO; sem correspondência, o
        fallback explícito — sugerir um tipo "parecido" seria pior que não sugerir."""
        catalogo = await self.task_types.list_filtered(step_id=None, is_active=True, query=None)
        if not catalogo:
            return None
        palavras = ACT_TYPE_KEYWORDS.get(act_type or "", ())
        for tipo in catalogo:
            nome = tipo.name.lower()
            if any(palavra in nome for palavra in palavras):
                return tipo.id
        for tipo in catalogo:
            if FALLBACK_TASK_TYPE_NAME.lower() in tipo.name.lower():
                return tipo.id
        return None

    async def _create_task(
        self,
        publication: Publication,
        *,
        user: User,
        deadline_date: date | None,
        task_type_id: uuid.UUID | None,
        assignee_id: uuid.UUID,
    ) -> uuid.UUID | None:
        from app.domain.posts.creation import CreatePostUseCase
        from app.domain.posts.schemas import PostCreateRequest

        if publication.lawsuit_id is None or task_type_id is None:
            # Intimação sem processo vinculado não tem onde pendurar a tarefa; a revisão
            # fica registrada e o vínculo é feito à mão (spec 045).
            return None
        use_case = CreatePostUseCase(session=self.session, tenant_id=self.tenant_id)
        detail = await use_case.create(
            PostCreateRequest.model_validate(
                {
                    "lawsuit_id": publication.lawsuit_id,
                    "task_type_id": task_type_id,
                    "user_ids": [assignee_id],
                    "deadline_date": deadline_date,
                    "scheduled_date": deadline_date,
                    "comments": f"Prazo confirmado a partir da intimação de "
                    f"{publication.availability_date.isoformat()}.",
                }
            ),
            user,
        )
        return detail.post.id


def _publication_prompt(publication: Publication) -> str:
    return (
        f"Data de disponibilização: {publication.availability_date.isoformat()}\n"
        f"Tribunal: {publication.court_code}\n"
        f"Processo: {publication.process_number or 'não informado'}\n"
        f"Tipo de comunicação: {publication.communication_type or 'não informado'}\n\n"
        f"Inteiro teor:\n{publication.body}"
    )
