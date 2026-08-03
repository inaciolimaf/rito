"""As 6 seções da caixa de entrada (spec 036 §7) — definição pura, compartilhada
entre a query SQL (repository) e a documentação/teste.

Regra 1: cada tarefa aparece em UMA seção só — a primeira em que se encaixa na
ordem configurada pelo usuário. O CASE do repository espelha esta ordem; os dois
lados são testados contra os mesmos cenários.
"""

from enum import StrEnum


class InboxSection(StrEnum):
    DEADLINE = "deadline"
    PUBLICATIONS = "publications"
    UNREAD = "unread"
    URGENT = "urgent"
    IMPORTANT = "important"
    OTHERS = "others"


# Regra 2: definição de cada seção (o predicado SQL mora no repository; aqui fica a
# documentação executável — os rótulos da UI e a ordem default).
SECTION_LABELS: dict[InboxSection, str] = {
    InboxSection.DEADLINE: "Prazo fatal",
    InboxSection.PUBLICATIONS: "Intimações",
    InboxSection.UNREAD: "Não lidas",
    InboxSection.URGENT: "Urgentes",
    InboxSection.IMPORTANT: "Importantes",
    InboxSection.OTHERS: "Todas as demais",
}

DEFAULT_SECTION_ORDER: tuple[InboxSection, ...] = tuple(InboxSection)

# Tipo sistêmico que define a seção de intimações (regra 2 — is_system da spec 031).
PUBLICATIONS_TASK_TYPE_NAME = "Intimações Judiciais"

# Prazo fatal entra na seção quando vence em até N dias (regra 2).
DEADLINE_HORIZON_DAYS = 7
