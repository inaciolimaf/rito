"""Tradução do PUT público (parcial) para a requisição do service (completa) — spec 134.

A regra 10 da 095 manda a escrita pública passar pelos services, e a 134 é a spec que a
cumpre. O obstáculo era de forma, não de intenção: o contrato público aceita atualização
PARCIAL (o integrador manda os dois campos que mudaram), e os services do Rito recebem a
requisição INTEIRA, porque é assim que a tela envia. Traduzir uma na outra é o trabalho
deste módulo — e ele fica aqui, e não no router, porque o §5 do `CLAUDE.md` reserva o
router para HTTP.

A tradução é sempre a mesma: o estado atual da entidade preenche a requisição, e o que
veio no corpo sobrescreve. `exclude_unset` é o que separa "não mandou o campo" (fica como
está) de "mandou nulo" (apaga) — a diferença entre não mexer na baixa e estornar o
lançamento.
"""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.domain.financial.models import Transaction
from app.domain.financial.schemas import TransactionUpdateRequest
from app.domain.lawsuits.models import Lawsuit
from app.domain.lawsuits.schemas import LawsuitUpdateRequest
from app.public.schemas import PublicLawsuitUpdate, PublicTransactionUpdate


def _merged(atual: Any, requisicao: type[BaseModel], enviado: dict[str, Any]) -> dict[str, Any]:
    """O estado de `atual` em TODO campo da requisição, com `enviado` por cima.

    Sem filtro de `hasattr` de propósito: campo da requisição interna que não existe na
    entidade estoura aqui, alto e no teste. Filtrar em silêncio faria o campo cair no
    default da requisição — e um default é, quase sempre, apagar o que estava lá.
    """
    return {campo: getattr(atual, campo) for campo in requisicao.model_fields} | enviado


def _validated[T: BaseModel](requisicao: type[T], dados: dict[str, Any]) -> T:
    """Valida com o schema INTERNO e traduz a recusa para 422.

    O schema público é mais frouxo que o interno de propósito (regra 12 da 095: ele não
    muda quando a tela muda), então há valor que passa lá e reprova aqui — `case_value`
    negativo é o exemplo. Sem esta tradução seria um 500: o `ValidationError` cru do
    Pydantic não é `RequestValidationError`, e o handler do projeto só conhece o segundo.

    O `HTTPException` num módulo que não é router é deliberado e é o limite: `app/public/`
    é adaptador de entrega, e esta é a mesma resposta que o FastAPI daria se o campo
    estivesse declarado no schema público.
    """
    try:
        return requisicao.model_validate(dados)
    except ValidationError as exc:
        # Só `loc`/`msg`/`type`: o `ctx` do Pydantic carrega o objeto da exceção, que não
        # é serializável — e o `input` devolveria ao cliente o estado inteiro da entidade.
        erros = [
            {"loc": [str(parte) for parte in erro["loc"]], "msg": erro["msg"], "type": erro["type"]}
            for erro in exc.errors()
        ]
        raise HTTPException(
            status_code=422,
            detail={"detail": "Um ou mais campos são inválidos.", "errors": erros},
        ) from exc


def transaction_update_request(
    transaction: Transaction, payload: PublicTransactionUpdate
) -> TransactionUpdateRequest:
    """O lançamento como está + o que o integrador mandou.

    Sem isto, `PUT /transactions/{id}` escrevia atributo no modelo, e a MESMA data era
    422 pela tela e 200 pela API: o `FuturePaymentDateError` mora no service, e o service
    não era chamado. Passar por aqui devolve à API pública as validações de referência, a
    normalização da descrição e a competência derivada — tudo o que a tela já tinha.
    """
    dados = _merged(transaction, TransactionUpdateRequest, payload.model_dump(exclude_unset=True))
    return _validated(TransactionUpdateRequest, dados)


def lawsuit_update_request(lawsuit: Lawsuit, payload: PublicLawsuitUpdate) -> LawsuitUpdateRequest:
    """O processo como está + o que o integrador mandou.

    `stage_id` entra na requisição como qualquer outro campo: quem grava o histórico é o
    `BoardService`, chamado por `LawsuitService.update` — e ele já sabe não fazer nada
    quando a etapa não mudou.
    """
    dados = _merged(lawsuit, LawsuitUpdateRequest, payload.model_dump(exclude_unset=True))
    return _validated(LawsuitUpdateRequest, dados)
