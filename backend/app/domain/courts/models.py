import enum

from sqlalchemy import CHAR, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CourtBase(DeclarativeBase):
    """Base própria (não `app.core.models.Base`) — courts/court_systems são taxonomia
    global do sistema, sem tenant_id/RLS, com PK `SMALLINT` (não o `id` UUID surrogate que
    toda tabela de domínio usa) — mesmo padrão de `app.domain.locations.models.LocationBase`
    (spec 018), mas em base própria para não acoplar os dois domínios."""


class CourtSegment(enum.StrEnum):
    ESTADUAL = "ESTADUAL"
    FEDERAL = "FEDERAL"
    TRABALHO = "TRABALHO"
    ELEITORAL = "ELEITORAL"
    MILITAR = "MILITAR"
    SUPERIOR = "SUPERIOR"
    CONTAS = "CONTAS"
    CONSELHO = "CONSELHO"


class Court(CourtBase):
    __tablename__ = "courts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    segment: Mapped[CourtSegment] = mapped_column(
        SAEnum(CourtSegment, name="court_segment", create_type=False)
    )
    state_code: Mapped[str | None] = mapped_column(CHAR(2), ForeignKey("states.code"))
    datajud_alias: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)


class CourtSystem(CourtBase):
    __tablename__ = "court_systems"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(unique=True)
