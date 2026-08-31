"""Engine de variáveis (spec 066) — catálogo fixo (cliente/processo/escritório/
usuário, docs §4.9) + resolução por regex contra um mapa de valores já carregado.

`build_variable_map` faz a ponte com o banco (recebe as entidades já carregadas, não
faz query nenhuma); `resolve_content` é pura — o mapa entra pronto, a substituição é
só regex + string, testável sem banco (regra dos 3 usos não se aplica aqui: a
separação é para permitir teste unitário rápido, não repetição de UI)."""

import re
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


def _resolve_customer(scope: VariableScope, field: str) -> str | None:
    customer = scope.customer
    if customer is None:
        return None
    if field == "nome_completo":
        return customer.name
    if field == "cpf_cnpj":
        return customer.identification
    if field == "rg":
        return customer.document
    if field == "data_nascimento":
        return format_date_br(customer.birthdate) if customer.birthdate else None
    if field == "data_nascimento_extenso":
        return format_date_extenso(customer.birthdate) if customer.birthdate else None
    if field == "estado_civil":
        return scope.customer_marital_status_name
    if field == "nacionalidade":
        return customer.nationality
    if field == "profissao":
        return customer.occupation
    if field == "endereco":
        return _address(
            customer.street, customer.region, customer.city, customer.state, customer.postal_code
        )
    if field == "email":
        return customer.email
    if field == "telefone":
        return customer.cellphone or customer.phone
    if field == "nome_mae":
        return customer.mother_name
    if field == "representante_nome":
        return customer.rep_name
    if field == "representante_cpf_cnpj":
        return customer.rep_identification
    if field == "representante_rg":
        return customer.rep_document
    if field == "representante_endereco":
        return _address(
            customer.rep_street, customer.rep_region, customer.rep_city, customer.rep_state, None
        )
    return None


def _resolve_lawsuit(scope: VariableScope, field: str) -> str | None:
    lawsuit = scope.lawsuit
    if lawsuit is None:
        return None
    if field == "numero_cnj":
        # process_number é guardado só em dígitos (spec 025, regra 9) — a máscara é
        # de apresentação, e um documento é sempre apresentação.
        if not lawsuit.process_number:
            return None
        try:
            return format_cnj(parse_cnj(lawsuit.process_number))
        except CNJValidationError:
            return lawsuit.process_number
    if field == "tipo_acao":
        return scope.lawsuit_type_name
    if field == "tribunal":
        return scope.lawsuit_court_name
    if field == "comarca":
        return lawsuit.county
    if field == "vara":
        return lawsuit.court_division
    if field == "fase":
        return scope.lawsuit_step_name
    if field == "responsavel":
        return scope.lawsuit_responsible_name
    if field == "valor_honorarios":
        return format_money_br(lawsuit.fees_value) if lawsuit.fees_value is not None else None
    if field == "valor_honorarios_extenso":
        return format_money_extenso(lawsuit.fees_value) if lawsuit.fees_value is not None else None
    if field == "valor_causa":
        return format_money_br(lawsuit.case_value) if lawsuit.case_value is not None else None
    if field == "valor_causa_extenso":
        return format_money_extenso(lawsuit.case_value) if lawsuit.case_value is not None else None
    if field == "data_ajuizamento":
        return format_date_br(lawsuit.filing_date) if lawsuit.filing_date else None
    if field == "data_ajuizamento_extenso":
        return format_date_extenso(lawsuit.filing_date) if lawsuit.filing_date else None
    if field == "data_arquivamento":
        return format_date_br(lawsuit.archived_date) if lawsuit.archived_date else None
    if field == "data_arquivamento_extenso":
        return format_date_extenso(lawsuit.archived_date) if lawsuit.archived_date else None
    if field == "resultado":
        return lawsuit.outcome.value if lawsuit.outcome else None
    return None


def _resolve_escritorio(scope: VariableScope, field: str) -> str | None:
    account = scope.account
    if account is None:
        return None
    if field == "razao_social":
        return account.name
    if field == "cnpj":
        return account.identification
    if field == "endereco":
        return _address(
            account.street, account.region, account.city, account.state, account.postal_code
        )
    if field == "telefone":
        return account.phone
    if field == "email":
        return account.email
    if field == "site":
        return account.site
    return None


def _resolve_usuario(scope: VariableScope, field: str) -> str | None:
    user = scope.user
    if field == "nome":
        return user.name
    if field == "cargo":
        return scope.user_occupation_name
    if field == "cpf":
        return user.identification
    if field == "oab":
        return user.number_oab
    if field == "celular":
        return user.cellphone
    return None


_RESOLVERS = {
    "cliente": _resolve_customer,
    "processo": _resolve_lawsuit,
    "escritorio": _resolve_escritorio,
    "usuario": _resolve_usuario,
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
