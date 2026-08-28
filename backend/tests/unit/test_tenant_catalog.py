"""Spec 099, regra 8 — o catálogo do escritório novo não pode esvaziar em silêncio.

`app/core/tenant_catalog.py` LÊ as listas das migrations que as semearam, para não
manter uma segunda cópia que diverge. O risco disso é uma migration ser apagada num
squash futuro: o catálogo viraria vazio e passaríamos a provisionar escritórios sem
etapa nenhuma, sem erro nenhum. Estes tamanhos são o alarme.
"""

from app.core import tenant_catalog


def test_os_tamanhos_do_catalogo_sao_os_do_levantamento() -> None:
    assert len(tenant_catalog.action_groups()) == 6
    assert len(tenant_catalog.stages()) == 59
    assert len(tenant_catalog.customer_origins()) == 8
    assert len(tenant_catalog.lawsuit_types()) > 0
    assert len(tenant_catalog.financial_categories()) > 0
    assert len(tenant_catalog.task_types()) > 0


def test_todo_tipo_de_acao_aponta_para_um_grupo_que_existe() -> None:
    """Se um tipo referenciar grupo inexistente, o JOIN do provisionamento o descarta em
    silêncio — o escritório nasce com menos tipos e ninguém percebe."""
    grupos = set(tenant_catalog.action_groups())

    orfaos = [tipo for tipo, grupo in tenant_catalog.lawsuit_types() if grupo not in grupos]

    assert orfaos == []


def test_toda_etapa_aponta_para_uma_das_9_fases() -> None:
    fases = {fase for _etapa, fase in tenant_catalog.stages()}

    assert len(fases) == 9


def test_nenhum_nome_do_catalogo_tem_aspa_simples() -> None:
    """O provisionamento monta `VALUES ('nome')` por interpolação — os nomes vêm de
    constante do repositório, nunca de entrada de usuário, mas uma aspa acrescentada por
    descuido quebraria a SQL. O teste é a rede embaixo dessa escolha."""
    nomes = [
        *tenant_catalog.action_groups(),
        *(t for t, _g in tenant_catalog.lawsuit_types()),
        *(e for e, _f in tenant_catalog.stages()),
        *tenant_catalog.customer_origins(),
        *(c for c, _t, _g in tenant_catalog.financial_categories()),
        *(n for n, _p, _s in tenant_catalog.task_types()),
    ]

    assert [nome for nome in nomes if "'" in nome] == []
