"""API pública v1 (spec 095 §5).

Vinte e dois endpoints sobre os MESMOS services da API interna (regra 10). Nenhum
atalho: o que reprova um usuário na tela reprova o integrador aqui, e o RLS continua
sendo quem isola — o tenant só chega por um caminho diferente (o token, não o JWT).

O arquivo é longo de propósito. A alternativa seria um router genérico dirigido por
configuração, e aí o contrato público — que é o produto desta spec — passaria a ser um
efeito colateral de um dicionário.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.deps import get_file_storage
from app.core.listing import Page
from app.core.repository import decode_cursor, encode_cursor
from app.domain.account.repository import AccountRepository
from app.domain.customers.models import Customer
from app.domain.customers.repository import CustomerQuery, CustomerRepository
from app.domain.customers.schemas import CustomerCreateRequest
from app.domain.customers.service import CustomerService
from app.domain.documents.models import Document
from app.domain.financial.models import Transaction
from app.domain.lawsuits.models import Lawsuit, LawsuitMovement, LawsuitStageHistory
from app.domain.lawsuits.movements_service import MovementsService
from app.domain.lawsuits.schemas import LawsuitCreateRequest, MovementCreateRequest
from app.domain.lawsuits.service import LawsuitService
from app.domain.posts.creation import CreatePostUseCase
from app.domain.posts.models import Post
from app.domain.posts.schemas import PostCreateRequest
from app.domain.publications.models import Publication
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage
from app.public.deps import ApiCaller, enforce_rate_limit, get_public_session, require_scope
from app.public.pagination import limit_param
from app.public.schemas import (
    PublicCustomer,
    PublicCustomerCreate,
    PublicCustomerPage,
    PublicDocument,
    PublicDocumentPage,
    PublicLawsuit,
    PublicLawsuitCreate,
    PublicLawsuitPage,
    PublicLawsuitUpdate,
    PublicMovement,
    PublicMovementCreate,
    PublicPost,
    PublicPostCreate,
    PublicPostPage,
    PublicPublication,
    PublicPublicationPage,
    PublicReference,
    PublicSettings,
    PublicStageChange,
    PublicTransaction,
    PublicTransactionCreate,
    PublicTransactionPage,
    PublicTransactionUpdate,
)

router = APIRouter(
    prefix="/api/public/v1",
    tags=["public-api"],
    # O limite vale para TODA rota pública — inclusive as que ainda não existem, porque
    # é dependência do router e não de cada função.
    dependencies=[Depends(enforce_rate_limit)],
)

_DOWNLOAD_EXPIRY_SECONDS = 5 * 60
PUBLIC_PREFIX = "/api/public/v1"


async def _acting_user(session: AsyncSession, caller: ApiCaller) -> User:
    """Quem "assina" a escrita feita pela API.

    É o usuário que criou o token. A alternativa — escrever sem autor — deixaria buracos
    em toda tela que mostra "criado por", e um autor genérico do sistema mentiria sobre
    quem autorizou aquilo.
    """
    user = await session.get(User, caller.acting_user_id)
    if user is None:  # pragma: no cover - FK garante
        raise HTTPException(status_code=401, detail="O usuário dono deste token não existe mais.")
    return user


def _page[T](
    items: list[T], *, limit: int, cursor_of: Any, total: int | None = None
) -> dict[str, Any]:
    proximo = cursor_of(items[-1]) if len(items) == limit and items else None
    return {"items": items, "next_cursor": proximo, "total": total}


def _created_cursor(row: Any) -> str:
    return encode_cursor(row.created_at.isoformat(), row.id)


def _decode(cursor: str | None) -> tuple[str, uuid.UUID] | None:
    return decode_cursor(cursor) if cursor else None


# Fora do `router` de propósito: ele exige token e limite em toda rota, e a documentação
# do contrato precisa ser legível ANTES de alguém ter um token — senão não dá para gerar
# o cliente antes de pedir acesso.
docs_router = APIRouter(prefix=PUBLIC_PREFIX, include_in_schema=False)


@docs_router.get("/openapi.json")
async def public_openapi(request: Request) -> dict[str, Any]:
    """Regra 11: OpenAPI gerado do código, com SÓ as rotas públicas.

    Servir o schema inteiro do app exporia os nomes de trezentos endpoints internos a
    quem tem um token de integração — informação que não ajuda o integrador e ajuda
    quem estiver mapeando o sistema.
    """
    completo = request.app.openapi()
    caminhos = {
        rota: metodos
        for rota, metodos in completo["paths"].items()
        if rota.startswith(PUBLIC_PREFIX)
    }
    todos = completo.get("components", {}).get("schemas", {})
    componentes = {nome: todos[nome] for nome in _closure(caminhos, todos)}
    return {
        "openapi": completo["openapi"],
        "info": {
            "title": "Rito — API pública",
            "version": "v1",
            "description": (
                "API REST do Rito para integradores. Autenticação por token de "
                "escritório em `Authorization: Bearer <token>`. Limites: 30 GET por "
                "minuto e 500 escritas por dia, por rota."
            ),
        },
        "paths": caminhos,
        "components": {
            "schemas": componentes,
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            },
        },
        "security": [{"bearerAuth": []}],
    }


def _closure(paths: dict[str, Any], schemas: dict[str, Any]) -> set[str]:
    """Fecho TRANSITIVO dos `$ref`.

    Um schema referencia outro (`PublicCustomerPage` → `PublicCustomer` → …), e mandar só
    o primeiro nível produz um documento que nenhum gerador de cliente consegue ler —
    ele para no primeiro `$ref` que não resolve. O laço roda até parar de crescer.
    """
    encontrados = _refs_in(paths)
    while True:
        novos = {
            nome
            for encontrado in encontrados
            if encontrado in schemas
            for nome in _refs_in(schemas[encontrado])
        } - encontrados
        if not novos:
            return {nome for nome in encontrados if nome in schemas}
        encontrados |= novos


def _refs_in(node: Any) -> set[str]:
    if isinstance(node, dict):
        referencia = node.get("$ref")
        proprio = (
            {referencia.rsplit("/", 1)[1]}
            if isinstance(referencia, str) and referencia.startswith("#/components/schemas/")
            else set()
        )
        return proprio.union(*(_refs_in(valor) for valor in node.values()), set())
    if isinstance(node, list):
        return set().union(*(_refs_in(item) for item in node), set())
    return set()


# ------------------------------------------------------------------ settings


@router.get("/settings", response_model=PublicSettings)
async def get_settings_reference(
    caller: ApiCaller = Depends(require_scope("read:settings")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicSettings:
    """Os ids que toda integração precisa antes de escrever qualquer coisa."""
    from app.domain.action_groups.models import LawsuitType
    from app.domain.customer_origins.models import CustomerOrigin
    from app.domain.financial.models import BankAccount, CostCenter, FinancialCategory
    from app.domain.stages.models import Stage
    from app.domain.task_types.models import TaskType

    async def _refs(model: Any, label: str = "name") -> list[PublicReference]:
        linhas = (await session.scalars(select(model))).all()
        return [PublicReference(id=item.id, name=str(getattr(item, label))) for item in linhas]

    return PublicSettings(
        tenant_id=caller.tenant_id,
        users=await _refs(User),
        customer_origins=await _refs(CustomerOrigin),
        task_types=await _refs(TaskType),
        stages=await _refs(Stage),
        lawsuit_types=await _refs(LawsuitType),
        financial_categories=await _refs(FinancialCategory),
        cost_centers=await _refs(CostCenter),
        bank_accounts=await _refs(BankAccount),
    )


# ----------------------------------------------------------------- customers


def _to_customer(customer: Customer) -> PublicCustomer:
    return PublicCustomer(
        id=customer.id,
        name=customer.name,
        type=customer.type.value,
        identification=customer.identification,
        email=customer.email,
        cellphone=customer.cellphone,
        phone=customer.phone,
        city=customer.city,
        state=customer.state,
        origin_id=customer.origin_id,
        birthdate=customer.birthdate,
        is_archived=customer.is_archived,
        created_at=customer.created_at,
    )


@router.get("/customers", response_model=PublicCustomerPage)
async def list_customers(
    query: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:customers")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicCustomerPage:
    items, total = await CustomerRepository(session).list_filtered(
        today=Clock(await AccountRepository(session).timezone()).today(),
        filters=CustomerQuery(query=query),
        page=Page(cursor=_decode(cursor), limit=limit),
    )
    pagina = _page(
        [_to_customer(item) for item in items],
        limit=limit,
        cursor_of=lambda _row: encode_cursor(items[-1].created_at.isoformat(), items[-1].id),
        total=total,
    )
    return PublicCustomerPage(**pagina)


@router.post("/customers", response_model=PublicCustomer, status_code=201)
async def create_customer(
    payload: PublicCustomerCreate,
    caller: ApiCaller = Depends(require_scope("write:customers")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicCustomer:
    """Regra 10: mesmo service do humano — CPF duplicado reprova aqui também."""
    from app.domain.customers.exceptions import CustomerIdentificationAlreadyExistsError

    service = CustomerService(session=session, tenant_id=caller.tenant_id)
    try:
        criado = await service.create(
            CustomerCreateRequest.model_validate(payload.model_dump(exclude_none=True))
        )
    except CustomerIdentificationAlreadyExistsError as exc:
        # Regra 10: a mesma recusa que a tela dá, com o mesmo código — o integrador
        # precisa distinguir "já existe" de "deu erro".
        raise HTTPException(
            status_code=409, detail="Já existe um contato com este CPF/CNPJ."
        ) from exc
    return _to_customer(criado)


@router.get("/customers/birthdays", response_model=PublicCustomerPage)
async def list_birthdays(
    month: int = Query(default=0, ge=0, le=12),
    caller: ApiCaller = Depends(require_scope("read:customers")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicCustomerPage:
    """Aniversariantes do mês — o caso de uso que existe em todo escritório: a mensagem
    de parabéns disparada por fora do Rito."""
    # Uma query a mais aqui é legítima: a API pública não está no orçamento do §11, e o
    # fuso não tem como vir de carona — `api_token_lookup` é função SECURITY DEFINER e
    # mudá-la pediria migration, que a spec 114 §5 não autoriza.
    alvo = month or Clock(await AccountRepository(session).timezone()).today().month
    items, total = await CustomerRepository(session).list_filtered(
        today=Clock(await AccountRepository(session).timezone()).today(),
        # `"month:<n>"` NÃO é reconhecido pelo filtro, que só aceita "day" ou "month" —
        # esta rota devolve todos os contatos, não os aniversariantes. É a dívida 34,
        # anterior a esta spec e preservada aqui porque 116 é refatoração. Não copie.
        filters=CustomerQuery(birthdays=f"month:{alvo}"),
        page=Page(limit=1000),
    )
    return PublicCustomerPage(
        items=[_to_customer(item) for item in items], next_cursor=None, total=total
    )


@router.get("/customers/{customer_id}", response_model=PublicCustomer)
async def get_customer(
    customer_id: uuid.UUID,
    caller: ApiCaller = Depends(require_scope("read:customers")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicCustomer:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Contato não encontrado.")
    return _to_customer(customer)


# ------------------------------------------------------------------ lawsuits


def _to_lawsuit(lawsuit: Lawsuit) -> PublicLawsuit:
    return PublicLawsuit(
        id=lawsuit.id,
        process_number=lawsuit.process_number,
        protocol_number=lawsuit.protocol_number,
        folder=lawsuit.folder,
        stage_id=lawsuit.stage_id,
        lawsuit_type_id=lawsuit.lawsuit_type_id,
        responsible_id=lawsuit.user_id,
        county=lawsuit.county,
        case_value=lawsuit.case_value,
        is_archived=lawsuit.is_archived,
        created_at=lawsuit.created_at,
        updated_at=lawsuit.updated_at,
    )


@router.get("/lawsuits", response_model=PublicLawsuitPage)
async def list_lawsuits(
    cursor: str | None = Query(default=None),
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicLawsuitPage:
    stmt = select(Lawsuit).order_by(Lawsuit.created_at.desc(), Lawsuit.id.desc()).limit(limit)
    decodificado = _decode(cursor)
    if decodificado is not None:
        marca, ultimo_id = decodificado
        stmt = stmt.where(
            (Lawsuit.created_at < datetime.fromisoformat(marca))
            | ((Lawsuit.created_at == datetime.fromisoformat(marca)) & (Lawsuit.id < ultimo_id))
        )
    linhas = list((await session.scalars(stmt)).all())
    return PublicLawsuitPage(
        items=[_to_lawsuit(item) for item in linhas],
        next_cursor=_created_cursor(linhas[-1]) if len(linhas) == limit else None,
    )


@router.post("/lawsuits", response_model=PublicLawsuit, status_code=201)
async def create_lawsuit(
    payload: PublicLawsuitCreate,
    caller: ApiCaller = Depends(require_scope("write:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicLawsuit:
    service = LawsuitService(session=session, tenant_id=caller.tenant_id)
    dados = payload.model_dump(exclude_none=True)
    customer_id = dados.pop("customer_id")
    detalhe = await service.create(
        LawsuitCreateRequest.model_validate(
            {
                **dados,
                "parties": [{"customer_id": str(customer_id), "pole": "ATIVO", "is_client": True}],
            }
        )
    )
    return _to_lawsuit(detalhe.lawsuit)


@router.get("/last-movements", response_model=list[PublicMovement])
async def list_last_movements(
    limit: int = Query(default=50, ge=1, le=500),
    caller: ApiCaller = Depends(require_scope("read:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> list[PublicMovement]:
    """As últimas movimentações do escritório inteiro — o endpoint que sustenta o painel
    de terceiros mais comum: "o que mexeu hoje?"."""
    stmt = (
        select(LawsuitMovement)
        .order_by(LawsuitMovement.occurred_at.desc(), LawsuitMovement.id.desc())
        .limit(limit)
    )
    return [_to_movement(item) for item in (await session.scalars(stmt)).all()]


@router.get("/lawsuits/{lawsuit_id}", response_model=PublicLawsuit)
async def get_lawsuit(
    lawsuit_id: uuid.UUID,
    caller: ApiCaller = Depends(require_scope("read:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicLawsuit:
    lawsuit = await session.get(Lawsuit, lawsuit_id)
    if lawsuit is None:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    return _to_lawsuit(lawsuit)


@router.put("/lawsuits/{lawsuit_id}", response_model=PublicLawsuit)
async def update_lawsuit(
    lawsuit_id: uuid.UUID,
    payload: PublicLawsuitUpdate,
    caller: ApiCaller = Depends(require_scope("write:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicLawsuit:
    """Atualização parcial dos campos que fazem sentido por integração.

    A mudança de etapa passa pelo `BoardService` — o único caminho que grava histórico e
    dispara automação (specs 051 e 092). Escrever `stage_id` direto pareceria funcionar e
    deixaria o histórico do processo com um buraco.
    """
    from app.domain.lawsuits.board_service import BoardService

    lawsuit = await session.get(Lawsuit, lawsuit_id)
    if lawsuit is None:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    dados = payload.model_dump(exclude_unset=True)
    destino = dados.pop("stage_id", None)
    for campo, valor in dados.items():
        setattr(lawsuit, campo, valor)
    if destino is not None:
        await BoardService(session, caller.tenant_id).change_stage(
            lawsuit, to_stage_id=destino, changed_by=caller.acting_user_id
        )
    await session.flush()
    return _to_lawsuit(lawsuit)


@router.get("/lawsuits/{lawsuit_id}/history", response_model=list[PublicStageChange])
async def get_lawsuit_history(
    lawsuit_id: uuid.UUID,
    caller: ApiCaller = Depends(require_scope("read:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> list[PublicStageChange]:
    stmt = (
        select(LawsuitStageHistory)
        .where(LawsuitStageHistory.lawsuit_id == lawsuit_id)
        .order_by(LawsuitStageHistory.changed_at.desc())
    )
    return [
        PublicStageChange(
            id=item.id,
            from_stage_id=item.from_stage_id,
            to_stage_id=item.to_stage_id,
            changed_by=item.changed_by,
            changed_at=item.changed_at,
        )
        for item in (await session.scalars(stmt)).all()
    ]


def _to_movement(movement: LawsuitMovement) -> PublicMovement:
    return PublicMovement(
        id=movement.id,
        lawsuit_id=movement.lawsuit_id,
        origin=movement.origin.value,
        occurred_at=movement.occurred_at,
        title=movement.title,
        body=movement.body,
    )


@router.get("/lawsuits/{lawsuit_id}/movements", response_model=list[PublicMovement])
async def list_movements(
    lawsuit_id: uuid.UUID,
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> list[PublicMovement]:
    stmt = (
        select(LawsuitMovement)
        .where(LawsuitMovement.lawsuit_id == lawsuit_id)
        .order_by(LawsuitMovement.occurred_at.desc())
        .limit(limit)
    )
    return [_to_movement(item) for item in (await session.scalars(stmt)).all()]


@router.post("/lawsuits/{lawsuit_id}/movements", response_model=PublicMovement, status_code=201)
async def create_movement(
    lawsuit_id: uuid.UUID,
    payload: PublicMovementCreate,
    caller: ApiCaller = Depends(require_scope("write:lawsuits")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicMovement:
    lawsuit = await session.get(Lawsuit, lawsuit_id)
    if lawsuit is None:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    service = MovementsService(session, caller.tenant_id)
    criada = await service.create_movement(
        lawsuit,
        MovementCreateRequest.model_validate(payload.model_dump()),
        await _acting_user(session, caller),
    )
    return _to_movement(criada)


# --------------------------------------------------------------------- posts


def _to_post(post: Post) -> PublicPost:
    return PublicPost(
        id=post.id,
        lawsuit_id=post.lawsuit_id,
        task_type_id=post.task_type_id,
        scheduled_date=post.scheduled_date,
        deadline_date=post.deadline_date,
        comments=post.comments,
        is_important=post.is_important,
        is_urgent=post.is_urgent,
        created_at=post.created_at,
    )


@router.get("/posts", response_model=PublicPostPage)
async def list_posts(
    lawsuit_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:posts")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicPostPage:
    stmt = select(Post).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit)
    if lawsuit_id is not None:
        stmt = stmt.where(Post.lawsuit_id == lawsuit_id)
    decodificado = _decode(cursor)
    if decodificado is not None:
        marca, ultimo_id = decodificado
        stmt = stmt.where(
            (Post.created_at < datetime.fromisoformat(marca))
            | ((Post.created_at == datetime.fromisoformat(marca)) & (Post.id < ultimo_id))
        )
    linhas = list((await session.scalars(stmt)).all())
    return PublicPostPage(
        items=[_to_post(item) for item in linhas],
        next_cursor=_created_cursor(linhas[-1]) if len(linhas) == limit else None,
    )


@router.post("/posts", response_model=PublicPost, status_code=201)
async def create_post(
    payload: PublicPostCreate,
    caller: ApiCaller = Depends(require_scope("write:posts")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicPost:
    autor = await _acting_user(session, caller)
    dados = payload.model_dump(exclude_none=True)
    dados.setdefault("user_ids", [autor.id])
    detalhe = await CreatePostUseCase(session, caller.tenant_id).create(
        PostCreateRequest.model_validate(dados), autor
    )
    return _to_post(detalhe.post)


# -------------------------------------------------------------- publications


@router.get("/publications", response_model=PublicPublicationPage)
async def list_publications(
    process_number: str | None = Query(default=None),
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:publications")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicPublicationPage:
    stmt = (
        select(Publication)
        .order_by(Publication.availability_date.desc(), Publication.id.desc())
        .limit(limit)
    )
    if process_number:
        stmt = stmt.where(Publication.process_number == process_number)
    linhas = (await session.scalars(stmt)).all()
    return PublicPublicationPage(
        items=[
            PublicPublication(
                id=item.id,
                process_number=item.process_number,
                court_code=item.court_code,
                availability_date=item.availability_date,
                communication_type=item.communication_type,
                body=item.body,
                is_active=item.is_active,
            )
            for item in linhas
        ],
        next_cursor=None,
    )


# -------------------------------------------------------------- transactions


def _to_transaction(transaction: Transaction) -> PublicTransaction:
    return PublicTransaction(
        id=transaction.id,
        kind=(
            transaction.kind.value if hasattr(transaction.kind, "value") else str(transaction.kind)
        ),
        amount=transaction.amount,
        due_date=transaction.due_date,
        payment_date=transaction.payment_date,
        competence=transaction.competence,
        description=transaction.description,
        customer_id=transaction.customer_id,
        lawsuit_id=transaction.lawsuit_id,
        category_id=transaction.category_id,
    )


@router.get("/transactions", response_model=PublicTransactionPage)
async def list_transactions(
    lawsuit_id: uuid.UUID | None = Query(default=None),
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:transactions")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicTransactionPage:
    stmt = (
        select(Transaction)
        .order_by(Transaction.due_date.desc(), Transaction.id.desc())
        .limit(limit)
    )
    if lawsuit_id is not None:
        stmt = stmt.where(Transaction.lawsuit_id == lawsuit_id)
    linhas = (await session.scalars(stmt)).all()
    return PublicTransactionPage(items=[_to_transaction(item) for item in linhas], next_cursor=None)


@router.post("/transactions", response_model=PublicTransaction, status_code=201)
async def create_transaction(
    payload: PublicTransactionCreate,
    caller: ApiCaller = Depends(require_scope("write:transactions")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicTransaction:
    from app.domain.financial.schemas import TransactionCreateRequest
    from app.domain.financial.service import TransactionService

    service = TransactionService(session=session, tenant_id=caller.tenant_id)
    linha = await service.create(
        TransactionCreateRequest.model_validate(payload.model_dump(exclude_none=True)),
        await _acting_user(session, caller),
        today=Clock(await AccountRepository(session).timezone()).today(),
    )
    return _to_transaction(linha.transaction)


@router.get("/transactions/{transaction_id}", response_model=PublicTransaction)
async def get_transaction(
    transaction_id: uuid.UUID,
    caller: ApiCaller = Depends(require_scope("read:transactions")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicTransaction:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")
    return _to_transaction(transaction)


@router.put("/transactions/{transaction_id}", response_model=PublicTransaction)
async def update_transaction(
    transaction_id: uuid.UUID,
    payload: PublicTransactionUpdate,
    caller: ApiCaller = Depends(require_scope("write:transactions")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicTransaction:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(transaction, campo, valor)
    await session.flush()
    return _to_transaction(transaction)


# ----------------------------------------------------------------- documents


@router.get("/documents", response_model=PublicDocumentPage)
async def list_documents(
    scope_id: uuid.UUID | None = Query(default=None),
    limit: int = limit_param(),
    caller: ApiCaller = Depends(require_scope("read:documents")),
    session: AsyncSession = Depends(get_public_session),
) -> PublicDocumentPage:
    stmt = select(Document).order_by(Document.created_at.desc()).limit(limit)
    if scope_id is not None:
        stmt = stmt.where(Document.scope_id == scope_id)
    linhas = (await session.scalars(stmt)).all()
    return PublicDocumentPage(
        items=[
            PublicDocument(
                id=item.id,
                scope_type=item.scope_type.value,
                scope_id=item.scope_id,
                filename=item.filename,
                content_type=item.content_type,
                size_bytes=item.size_bytes,
                created_at=item.created_at,
            )
            for item in linhas
        ],
        next_cursor=None,
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    caller: ApiCaller = Depends(require_scope("read:documents")),
    session: AsyncSession = Depends(get_public_session),
    storage: FileStorage = Depends(get_file_storage),
) -> Response:
    """Devolve 302 para uma URL assinada de vida curta.

    O arquivo não passa pelo servidor da API: streamar o binário aqui gastaria banda e
    memória do Rito para entregar algo que o object storage entrega melhor — e a URL
    expira em cinco minutos, como no download da UI (spec 035, regra 6).
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    url = storage.signed_url(document.storage_key, expires_in_seconds=_DOWNLOAD_EXPIRY_SECONDS)
    return Response(status_code=302, headers={"Location": url})
