"""Catálogo de features de IA (spec 081).

O registro é código de propósito: cada feature nasce numa spec da fase 8, e a UI de
configuração precisa listar as que existem — inclusive as que ainda não têm linha em
`ai_feature_config`. O que NÃO está aqui é o modelo: esse vem sempre da configuração
do tenant ou do padrão do ambiente (regra 2).
"""

from dataclasses import dataclass
from typing import Literal

# Spec 090, alvo 2: "econômica" é a feature em que o modelo mais caro não muda o
# resultado — classificar um ato processual e resumir três parágrafos. O escritório
# continua podendo trocar o modelo na UI; isto é só o padrão de quem nunca trocou.
FeatureTier = Literal["padrao", "economico"]


@dataclass(frozen=True)
class AiFeature:
    key: str
    label: str
    description: str
    tier: FeatureTier = "padrao"


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
        tier="economico",
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
        key="document_extraction",
        label="Extração de documentos",
        description="Campos estruturados a partir de RG, contrato ou procuração (spec 091).",
    ),
    AiFeature(
        key="automation_decision",
        label="Decisão em automação",
        description="Escolha do ramo de uma automação a partir do contexto (spec 094).",
    ),
    AiFeature(
        key="analytics",
        label="IA analítica",
        description="Perguntas em linguagem natural sobre os indicadores (spec 089).",
    ),
)

FEATURE_KEYS: frozenset[str] = frozenset(feature.key for feature in AI_FEATURES)
FEATURES_BY_KEY: dict[str, AiFeature] = {feature.key: feature for feature in AI_FEATURES}
