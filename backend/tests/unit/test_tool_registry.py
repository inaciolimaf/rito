"""Registry de ferramentas (spec 083, regras 9 e 12).

Sem banco: o que se verifica aqui é o contrato que o modelo recebe — nome, descrição e
schema — e que ele é derivado do Pydantic, não escrito à mão.
"""

import pytest
from pydantic import BaseModel

from app.ai.tools.base import ToolContext, ToolError, all_tools, get_tool, tool

EXPECTED_TOOLS = {
    "get_bi_metrics",
    "get_current_context",
    "get_customer",
    "get_financial_summary",
    "get_inbox",
    "get_lawsuit",
    "get_lawsuit_financials",
    "get_lawsuit_timeline",
    "get_productivity",
    "get_publication",
    "list_taxonomies",
    "search_customers",
    "search_lawsuits",
    "search_publications",
    "search_tasks",
    "search_transactions",
}


def test_registry_descobre_as_16_ferramentas_por_decorator() -> None:
    """Regra 12: ferramenta nova aparece sozinha — não há lista para manter."""
    assert {definition.name for definition in all_tools()} == EXPECTED_TOOLS


def test_schema_json_e_derivado_do_pydantic() -> None:
    """Regra 9: uma fonte de verdade para validar e para descrever ao modelo."""
    definition = get_tool("search_lawsuits")
    schema = definition.json_schema()

    assert schema["type"] == "object"
    assert set(schema["properties"]) == {
        "query",
        "customer_id",
        "stage_id",
        "responsible_id",
        "process_number",
        "limit",
    }
    # O teto de linhas está no schema, não só no código: o modelo já pede dentro do
    # limite em vez de tomar erro depois.
    assert schema["properties"]["limit"]["maximum"] == 50
    assert definition.to_spec().name == "search_lawsuits"


def test_toda_ferramenta_tem_descricao_util() -> None:
    """A descrição é o que o modelo lê para decidir qual chamar — vazia ou genérica
    demais, ele chuta."""
    for definition in all_tools():
        assert len(definition.description) > 40, definition.name


def test_handler_sem_modelo_de_parametros_e_recusado_no_registro() -> None:
    with pytest.raises(TypeError):

        @tool(name="sem_schema", description="x" * 50)
        async def sem_schema(ctx: ToolContext, params: dict) -> dict:  # type: ignore[type-arg]
            return {}


def test_erro_de_ferramenta_vira_payload_estruturado() -> None:
    """Regra 8: o modelo recebe um objeto que ele consegue interpretar, não um traceback."""
    payload = ToolError("forbidden", "sem acesso financeiro").to_payload()

    assert payload == {"error": {"code": "forbidden", "message": "sem acesso financeiro"}}


def test_modelo_de_parametros_valida_o_teto_de_linhas() -> None:
    definition = get_tool("search_customers")
    params: BaseModel = definition.params_model.model_validate({"limit": 50})

    assert params.limit == 50  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        definition.params_model.model_validate({"limit": 500})
