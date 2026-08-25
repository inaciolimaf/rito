"""Catálogo de features de IA (spec 081).

O registro é código de propósito: cada feature nasce numa spec da fase 8, e a UI de
configuração precisa listar as que existem — inclusive as que ainda não têm linha em
`ai_feature_config`. O que NÃO está aqui é o modelo: esse vem sempre da configuração
do tenant ou do padrão do ambiente (regra 2).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AiFeature:
    key: str
    label: str
    description: str


AI_FEATURES: tuple[AiFeature, ...] = (
    AiFeature(
        key="copilot",
        label="Copiloto",
        description="Assistente global do sistema (spec 085).",
    ),
    AiFeature(
        key="publication_summary",
        label="Resumo de intimações",
        description="Resumo e classificação de intimação recebida (spec 086).",
    ),
    AiFeature(
        key="petition_draft",
        label="Minuta de petição",
        description="Rascunho de peça a partir do processo (spec 087).",
    ),
    AiFeature(
        key="editor_assist",
        label="IA no editor",
        description="Reescrita e continuação dentro do editor de documentos (spec 088).",
    ),
    AiFeature(
        key="analytics",
        label="IA analítica",
        description="Perguntas em linguagem natural sobre os indicadores (spec 089).",
    ),
)

FEATURE_KEYS: frozenset[str] = frozenset(feature.key for feature in AI_FEATURES)
