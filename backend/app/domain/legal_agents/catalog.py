"""Os 19 agentes de petição por área (spec 087 §4).

O prompt de sistema de cada um é montado a partir de um molde comum: o que muda entre
áreas é o vocabulário, a estrutura da peça e a legislação de referência — o que NÃO
muda são as proibições, e é por isso que elas ficam numa constante só, aplicada a
todos (regra 6).

O catálogo é código porque é conteúdo de produto versionado: mudar o prompt de um
agente é uma decisão revisável em pull request, não um `UPDATE` no banco. O escritório
pode sobrescrever o prompt (regra 10) — e é justamente por isso que o original precisa
estar preservado em algum lugar confiável.
"""

from dataclasses import dataclass

from app.ai.prompts import SAFETY_RULES

# Regra 6: a proibição vale para todos os agentes, sem exceção e sem "salvo se".
# Spec 090, alvo 3: as proibições são as MESMAS de todo prompt do produto — repetidas
# com palavras diferentes, divergiriam na primeira correção.
GUARDRAILS = (
    SAFETY_RULES + "\n5. Este texto é MINUTA: escreva para ser revisado por um "
    "advogado, não para ser protocolado como está."
)

_BASE = (
    "Você é um assistente de redação jurídica de um escritório de advocacia "
    "brasileiro, especializado em {area}. Produza a minuta em português do Brasil, "
    "em HTML simples (h1, h2, p, ul, li, strong), pronta para abrir no editor de "
    "documentos.\n\n"
    "Estrutura esperada da peça: {estrutura}.\n"
    "Fundamentação de referência da área: {fundamentacao}.\n\n"
    "{guardrails}"
)


@dataclass(frozen=True)
class AgentSeed:
    code: str
    name: str
    practice_area: str
    structure: str
    legal_basis: str

    def system_prompt(self) -> str:
        return _BASE.format(
            area=self.practice_area,
            estrutura=self.structure,
            fundamentacao=self.legal_basis,
            guardrails=GUARDRAILS,
        )


_PETICAO_PADRAO = (
    "endereçamento, qualificação das partes, dos fatos, do direito, dos pedidos, "
    "do valor da causa e das provas"
)

AGENT_SEEDS: tuple[AgentSeed, ...] = (
    AgentSeed(
        "consu-1",
        "Agente Consumidor",
        "Direito do Consumidor",
        _PETICAO_PADRAO,
        "CDC (Lei 8.078/90) e CPC",
    ),
    AgentSeed(
        "assis-1",
        "Agente Assistencial",
        "Direito Assistencial",
        _PETICAO_PADRAO,
        "LOAS (Lei 8.742/93) e Lei 8.213/91",
    ),
    AgentSeed(
        "trib-1",
        "Agente Tributário",
        "Direito Tributário",
        _PETICAO_PADRAO,
        "CTN e legislação tributária federal, estadual e municipal",
    ),
    AgentSeed(
        "trans-1",
        "Agente Trânsito",
        "Direito de Trânsito",
        _PETICAO_PADRAO,
        "CTB (Lei 9.503/97) e resoluções do CONTRAN",
    ),
    AgentSeed(
        "banc-1",
        "Agente Bancário",
        "Direito Bancário",
        _PETICAO_PADRAO,
        "CDC, CC e regulamentação do Banco Central",
    ),
    AgentSeed(
        "trab-1",
        "Agente Trabalhista",
        "Direito do Trabalho",
        "endereçamento, qualificação, dos fatos, do direito, dos pedidos com "
        "liquidação, do valor da causa e do requerimento de provas",
        "CLT e Constituição Federal",
    ),
    AgentSeed(
        "ambi-1",
        "Agente Ambiental",
        "Direito Ambiental",
        _PETICAO_PADRAO,
        "Lei 6.938/81, Lei 9.605/98 e Código Florestal",
    ),
    AgentSeed(
        "imob-1",
        "Agente Imobiliário",
        "Direito Imobiliário",
        _PETICAO_PADRAO,
        "Código Civil, Lei do Inquilinato (8.245/91) e Lei 6.766/79",
    ),
    AgentSeed(
        "penal-1",
        "Agente Penal",
        "Direito Penal",
        "endereçamento, qualificação, dos fatos, do direito, do pedido e do rol de testemunhas",
        "Código Penal e Código de Processo Penal",
    ),
    AgentSeed(
        "civel-1",
        "Agente Cível Generalista",
        "Direito Cível",
        _PETICAO_PADRAO,
        "Código Civil e CPC",
    ),
    AgentSeed(
        "respc-1",
        "Agente Responsabilidade Civil",
        "Responsabilidade Civil",
        _PETICAO_PADRAO,
        "arts. 186, 187 e 927 do Código Civil",
    ),
    AgentSeed(
        "fam-1",
        "Agente Família",
        "Direito de Família",
        _PETICAO_PADRAO,
        "Código Civil (Livro IV) e ECA, quando houver menor",
    ),
    AgentSeed(
        "digi-1",
        "Agente Digital",
        "Direito Digital",
        _PETICAO_PADRAO,
        "LGPD (13.709/18) e Marco Civil da Internet (12.965/14)",
    ),
    AgentSeed(
        "contr-1",
        "Agente Contratual",
        "Direito Contratual",
        _PETICAO_PADRAO,
        "Código Civil (Livro I, Título V)",
    ),
    AgentSeed(
        "admin-1",
        "Agente Administrativo",
        "Direito Administrativo",
        _PETICAO_PADRAO,
        "Lei 14.133/21, Lei 9.784/99 e Constituição Federal",
    ),
    AgentSeed(
        "empre-1",
        "Agente Empresarial",
        "Direito Empresarial",
        _PETICAO_PADRAO,
        "Código Civil (Livro II) e Lei 11.101/05",
    ),
    AgentSeed(
        "previ-1",
        "Agente Previdenciário",
        "Direito Previdenciário",
        _PETICAO_PADRAO,
        "Lei 8.213/91, Decreto 3.048/99 e EC 103/19",
    ),
    AgentSeed(
        "propi-1",
        "Agente Propriedade Intelectual",
        "Propriedade Intelectual",
        _PETICAO_PADRAO,
        "Lei 9.279/96 e Lei 9.610/98",
    ),
    AgentSeed(
        "saude-1",
        "Agente Saúde",
        "Direito à Saúde",
        _PETICAO_PADRAO,
        "Constituição Federal (art. 196), Lei 8.080/90 e Lei 9.656/98",
    ),
)

AGENT_CODES = tuple(seed.code for seed in AGENT_SEEDS)
