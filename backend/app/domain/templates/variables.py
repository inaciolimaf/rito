"""Engine de variáveis (spec 066) — catálogo fixo (cliente/processo/escritório/
usuário, docs §4.9) + resolução por regex contra um mapa de valores já carregado.

`build_variable_map` faz a ponte com o banco (recebe as entidades já carregadas, não
faz query nenhuma); `resolve_content` é pura — o mapa entra pronto, a substituição é
só regex + string, testável sem banco (regra dos 3 usos não se aplica aqui: a
separação é para permitir teste unitário rápido, não repetição de UI)."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.account.models import Account
from app.domain.customers.models import Customer
from app.domain.lawsuits.cnj import CNJValidationError, format_cnj, parse_cnj
from app.domain.lawsuits.models import Lawsuit
from app.domain.users.models import User

_MONTH_NAMES_PT = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-z_]+)\.([a-z_]+)\s*\}\}")


def format_date_br(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def format_date_extenso(value: date) -> str:
    """Regra 5: "20 de agosto de 2026" → "vinte de agosto de dois mil e vinte e
    seis" — dia 1 usa "primeiro" (convenção jurídica), não "um"."""
    # Spec 104: só as duas funções "por extenso" precisam do num2words.
    from num2words import num2words

    day_words = "primeiro" if value.day == 1 else str(num2words(value.day, lang="pt_BR"))
    month_name = _MONTH_NAMES_PT[value.month - 1]
    year_words = str(num2words(value.year, lang="pt_BR"))
    return f"{day_words} de {month_name} de {year_words}"


def format_money_br(value: Decimal) -> str:
    text = f"{value:,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def format_money_extenso(value: Decimal) -> str:
    """Regra 6: por extenso, com "reais"/"centavos" — `num2words` já devolve isso
    pronto para `lang='pt_BR', to='currency'`."""
    from num2words import num2words  # spec 104

    return str(num2words(float(value), lang="pt_BR", to="currency"))


@dataclass
class VariableScope:
    """Entidades já carregadas do banco — regra 2/3: `customer`/`lawsuit` podem
    faltar (o escopo não foi informado), `account`/`user` sempre existem quando a
    resolução roda (usuário logado, tenant configurado ou não)."""

    customer: Customer | None
    customer_marital_status_name: str | None
    lawsuit: Lawsuit | None
    lawsuit_type_name: str | None
    lawsuit_court_name: str | None
    lawsuit_step_name: str | None
    lawsuit_responsible_name: str | None
    account: Account | None
    user: User
    user_occupation_name: str | None


def _address(
    street: str | None,
    region: str | None,
    city: str | None,
    state: str | None,
    postal_code: str | None,
) -> str | None:
    parts = [part for part in (street, region, city, state) if part]
    if postal_code:
        parts.append(f"CEP {postal_code}")
    return ", ".join(parts) if parts else None


# Um registro por entidade, no lugar de quatro cadeias de `if campo == "x"` (spec 106).
# O ganho não é o número do lint: é que acrescentar variável ao catálogo passa a ser uma
# entrada de tabela, ao lado das outras, em vez de mais um `if` no meio de vinte — e o
# `VARIABLE_CATALOG` logo abaixo já era uma tabela, então as duas metades finalmente têm
# a mesma forma. Cada resolvedor recebe a entidade já validada como não-nula e o escopo,
# porque parte dos campos vem de nomes desnormalizados que moram no escopo, não na linha.

_CustomerField = Callable[[Customer, "VariableScope"], str | None]
_LawsuitField = Callable[[Lawsuit, "VariableScope"], str | None]
_AccountField = Callable[[Account, "VariableScope"], str | None]
_UserField = Callable[[User, "VariableScope"], str | None]


def _cnj_formatado(lawsuit: Lawsuit, _scope: "VariableScope") -> str | None:
    """`process_number` é guardado só em dígitos (spec 025, regra 9) — a máscara é de
    apresentação, e um documento é sempre apresentação. Número inválido sai como está:
    documento em branco seria pior que documento com o número cru."""
    if not lawsuit.process_number:
        return None
    try:
        return format_cnj(parse_cnj(lawsuit.process_number))
    except CNJValidationError:
        return lawsuit.process_number


_CUSTOMER_FIELDS: dict[str, _CustomerField] = {
    "nome_completo": lambda c, _s: c.name,
    "cpf_cnpj": lambda c, _s: c.identification,
    "rg": lambda c, _s: c.document,
    "data_nascimento": lambda c, _s: format_date_br(c.birthdate) if c.birthdate else None,
    "data_nascimento_extenso": (
        lambda c, _s: format_date_extenso(c.birthdate) if c.birthdate else None
    ),
    "estado_civil": lambda _c, s: s.customer_marital_status_name,
    "nacionalidade": lambda c, _s: c.nationality,
    "profissao": lambda c, _s: c.occupation,
    "endereco": lambda c, _s: _address(c.street, c.region, c.city, c.state, c.postal_code),
    "email": lambda c, _s: c.email,
    "telefone": lambda c, _s: c.cellphone or c.phone,
    "nome_mae": lambda c, _s: c.mother_name,
    "representante_nome": lambda c, _s: c.rep_name,
    "representante_cpf_cnpj": lambda c, _s: c.rep_identification,
    "representante_rg": lambda c, _s: c.rep_document,
    "representante_endereco": (
        lambda c, _s: _address(c.rep_street, c.rep_region, c.rep_city, c.rep_state, None)
    ),
}

_LAWSUIT_FIELDS: dict[str, _LawsuitField] = {
    "numero_cnj": _cnj_formatado,
    "tipo_acao": lambda _l, s: s.lawsuit_type_name,
    "tribunal": lambda _l, s: s.lawsuit_court_name,
    "comarca": lambda lawsuit, _s: lawsuit.county,
    "vara": lambda lawsuit, _s: lawsuit.court_division,
    "fase": lambda _l, s: s.lawsuit_step_name,
    "responsavel": lambda _l, s: s.lawsuit_responsible_name,
    "valor_honorarios": (
        lambda lawsuit, _s: (
            format_money_br(lawsuit.fees_value) if lawsuit.fees_value is not None else None
        )
    ),
    "valor_honorarios_extenso": (
        lambda lawsuit, _s: (
            format_money_extenso(lawsuit.fees_value) if lawsuit.fees_value is not None else None
        )
    ),
    "valor_causa": (
        lambda lawsuit, _s: (
            format_money_br(lawsuit.case_value) if lawsuit.case_value is not None else None
        )
    ),
    "valor_causa_extenso": (
        lambda lawsuit, _s: (
            format_money_extenso(lawsuit.case_value) if lawsuit.case_value is not None else None
        )
    ),
    "data_ajuizamento": (
        lambda lawsuit, _s: (format_date_br(lawsuit.filing_date) if lawsuit.filing_date else None)
    ),
    "data_ajuizamento_extenso": (
        lambda lawsuit, _s: (
            format_date_extenso(lawsuit.filing_date) if lawsuit.filing_date else None
        )
    ),
    "data_arquivamento": (
        lambda lawsuit, _s: (
            format_date_br(lawsuit.archived_date) if lawsuit.archived_date else None
        )
    ),
    "data_arquivamento_extenso": (
        lambda lawsuit, _s: (
            format_date_extenso(lawsuit.archived_date) if lawsuit.archived_date else None
        )
    ),
    "resultado": lambda lawsuit, _s: lawsuit.outcome.value if lawsuit.outcome else None,
}

_ACCOUNT_FIELDS: dict[str, _AccountField] = {
    "razao_social": lambda a, _s: a.name,
    "cnpj": lambda a, _s: a.identification,
    "endereco": lambda a, _s: _address(a.street, a.region, a.city, a.state, a.postal_code),
    "telefone": lambda a, _s: a.phone,
    "email": lambda a, _s: a.email,
    "site": lambda a, _s: a.site,
}

_USER_FIELDS: dict[str, _UserField] = {
    "nome": lambda u, _s: u.name,
    "cargo": lambda _u, s: s.user_occupation_name,
    "cpf": lambda u, _s: u.identification,
    "oab": lambda u, _s: u.number_oab,
    "celular": lambda u, _s: u.cellphone,
}


def _resolve_customer(scope: VariableScope, field: str) -> str | None:
    if scope.customer is None:
        return None
    resolvedor = _CUSTOMER_FIELDS.get(field)
    return resolvedor(scope.customer, scope) if resolvedor else None


def _resolve_lawsuit(scope: VariableScope, field: str) -> str | None:
    if scope.lawsuit is None:
        return None
    resolvedor = _LAWSUIT_FIELDS.get(field)
    return resolvedor(scope.lawsuit, scope) if resolvedor else None


def _resolve_account(scope: VariableScope, field: str) -> str | None:
    if scope.account is None:
        return None
    resolvedor = _ACCOUNT_FIELDS.get(field)
    return resolvedor(scope.account, scope) if resolvedor else None


def _resolve_user(scope: VariableScope, field: str) -> str | None:
    resolvedor = _USER_FIELDS.get(field)
    return resolvedor(scope.user, scope) if resolvedor else None


_RESOLVERS = {
    "cliente": _resolve_customer,
    "processo": _resolve_lawsuit,
    "escritorio": _resolve_account,
    "usuario": _resolve_user,
}

# Regra 1: catálogo exposto pro seletor do front — (namespace, campo, rótulo).
VARIABLE_CATALOG: list[tuple[str, str, str]] = [
    ("cliente", "nome_completo", "Nome completo"),
    ("cliente", "cpf_cnpj", "CPF/CNPJ"),
    ("cliente", "rg", "RG"),
    ("cliente", "data_nascimento", "Data de nascimento"),
    ("cliente", "data_nascimento_extenso", "Data de nascimento (por extenso)"),
    ("cliente", "estado_civil", "Estado civil"),
    ("cliente", "nacionalidade", "Nacionalidade"),
    ("cliente", "profissao", "Profissão"),
    ("cliente", "endereco", "Endereço"),
    ("cliente", "email", "E-mail"),
    ("cliente", "telefone", "Telefone"),
    ("cliente", "nome_mae", "Nome da mãe"),
    ("cliente", "representante_nome", "Nome do representante"),
    ("cliente", "representante_cpf_cnpj", "CPF/CNPJ do representante"),
    ("cliente", "representante_rg", "RG do representante"),
    ("cliente", "representante_endereco", "Endereço do representante"),
    ("processo", "numero_cnj", "Número CNJ"),
    ("processo", "tipo_acao", "Tipo de ação"),
    ("processo", "tribunal", "Tribunal"),
    ("processo", "comarca", "Comarca"),
    ("processo", "vara", "Vara"),
    ("processo", "fase", "Fase"),
    ("processo", "responsavel", "Responsável"),
    ("processo", "valor_honorarios", "Valor dos honorários"),
    ("processo", "valor_honorarios_extenso", "Valor dos honorários (por extenso)"),
    ("processo", "valor_causa", "Valor da causa"),
    ("processo", "valor_causa_extenso", "Valor da causa (por extenso)"),
    ("processo", "data_ajuizamento", "Data do ajuizamento"),
    ("processo", "data_ajuizamento_extenso", "Data do ajuizamento (por extenso)"),
    ("processo", "data_arquivamento", "Data do arquivamento"),
    ("processo", "data_arquivamento_extenso", "Data do arquivamento (por extenso)"),
    ("processo", "resultado", "Resultado"),
    ("escritorio", "razao_social", "Razão social"),
    ("escritorio", "cnpj", "CNPJ"),
    ("escritorio", "endereco", "Endereço"),
    ("escritorio", "telefone", "Telefone"),
    ("escritorio", "email", "E-mail"),
    ("escritorio", "site", "Site"),
    ("usuario", "nome", "Nome"),
    ("usuario", "cargo", "Cargo"),
    ("usuario", "cpf", "CPF"),
    ("usuario", "oab", "OAB"),
    ("usuario", "celular", "Celular"),
]


def build_variable_map(scope: VariableScope) -> dict[str, str | None]:
    return {
        f"{namespace}.{field}": _RESOLVERS[namespace](scope, field)
        for namespace, field, _label in VARIABLE_CATALOG
    }


def resolve_content(html: str, variable_map: dict[str, str | None]) -> tuple[str, list[str]]:
    """Regra 1/4: substitui `{{namespace.campo}}` reconhecido; o que não está no mapa
    (nome desconhecido) ou tem valor `None` (sem escopo/dado) vira `<mark>` — nunca
    silencioso, nunca quebra a resolução das outras ocorrências."""
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        token = f"{match.group(1)}.{match.group(2)}"
        value = variable_map.get(token)
        if value is None:
            missing.append(token)
            return f'<mark data-missing="true">{match.group(0)}</mark>'
        return value

    resolved = _VARIABLE_PATTERN.sub(_replace, html)
    return resolved, missing
