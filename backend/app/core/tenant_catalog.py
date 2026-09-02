"""Taxonomia padrão de um escritório novo (spec 099, regra 8).

Até a 099 não havia provisionamento de tenant: as migrations 014/015/016/031/054
semeavam a taxonomia para os tenants **que existiam no momento em que rodaram**, e cada
uma anotou a mesma limitação ("sem spec de provisionamento de tenant ainda"). Um
escritório criado depois nascia sem grupo de ação, sem etapa e sem tipo de tarefa — ou
seja, sem conseguir cadastrar um processo.

## Por que as listas são LIDAS das migrations

A alternativa era copiá-las para cá. Copiar 59 etapas e 24 tipos de ação cria duas
verdades que divergem no primeiro dia em que alguém acrescentar uma etapa num lugar só —
e a divergência é invisível, porque cada metade continua consistente consigo mesma. As
migrations são história congelada (CLAUDE.md §9: nunca editar migration commitada), o
que as torna uma fonte estável; ler delas custa um `importlib` e elimina a cópia.

O risco disso é uma migration ser apagada num squash futuro. É por isso que
`tests/unit/test_tenant_catalog.py` afirma os TAMANHOS esperados: um catálogo que
esvazia falha alto, em vez de provisionar escritórios vazios em silêncio.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _migration(nome: str) -> ModuleType:
    """Carrega uma migration como módulo. O nome começa com dígito, então `import` não
    serve — `spec_from_file_location` é o caminho normal para isso."""
    caminho = _VERSIONS / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(f"_rito_seed_{nome}", caminho)
    if spec is None or spec.loader is None:
        # Checagem de sistema de arquivos, não invariante: a migration pode não existir
        # numa árvore incompleta. `assert` some sob `python -O` e o erro viraria um
        # `AttributeError` em `spec.loader` (spec 115).
        raise FileNotFoundError(f"migration {nome} não encontrada em {caminho}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def action_groups() -> tuple[str, ...]:
    return tuple(_migration("014_action_groups_types")._GROUPS)


def lawsuit_types() -> tuple[tuple[str, str], ...]:
    """(nome do tipo, nome do grupo)."""
    return tuple(_migration("014_action_groups_types")._TYPES_BY_GROUP)


def stages() -> tuple[tuple[str, str], ...]:
    """(nome da etapa, nome da fase)."""
    return tuple(_migration("015_steps_stages")._STAGES_BY_STEP)


def customer_origins() -> tuple[str, ...]:
    return tuple(_migration("016_customer_origins")._ORIGINS)


def financial_categories() -> tuple[tuple[str, str, int], ...]:
    """(nome, tipo, id do grupo do DRE). Os grupos do DRE são catálogo GLOBAL — vêm da
    própria migration 054 e não pertencem a escritório nenhum."""
    return tuple(_migration("054_chart_of_accounts")._CATEGORIES)


def task_types() -> tuple[tuple[str, int, bool], ...]:
    """(nome, pontuação, é sistêmica). Os nomes sistêmicos não podem ser renomeados nem
    excluídos (spec 031) — daí a terceira posição."""
    from app.domain.task_types.catalog import (
        DEFAULT_TASK_NAMES,
        OBSERVED_REWARDS,
        SYSTEM_TASK_NAMES,
    )

    sistemicas = set(SYSTEM_TASK_NAMES)
    return tuple(
        (nome, OBSERVED_REWARDS.get(nome, 0), nome in sistemicas)
        for nome in (*DEFAULT_TASK_NAMES, *SYSTEM_TASK_NAMES)
    )
