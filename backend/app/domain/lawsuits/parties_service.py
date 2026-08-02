"""Partes do processo (spec 023) — caso de uso separado de `LawsuitService` na
refatoração 030 (SRP: um service por caso de uso, nenhum acima de ~300 linhas)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customers.repository import CustomerRepository
from app.domain.lawsuits.exceptions import (
    DuplicatePartyError,
    LastPartyError,
    PartyCustomerNotFoundError,
)
from app.domain.lawsuits.models import Lawsuit, LawsuitParty, PartyPole
from app.domain.lawsuits.repository import LawsuitPartyRepository
from app.domain.lawsuits.schemas import PartyCreateRequest, PartyInput, PartyUpdateRequest


@dataclass
class PartyDetail:
    party: LawsuitParty
    customer_name: str


class PartiesService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.parties = LawsuitPartyRepository(session)
        self.customers = CustomerRepository(session)

    async def list_parties(self, lawsuit_id: uuid.UUID) -> Sequence[PartyDetail]:
        rows = await self.parties.list_for_lawsuit(lawsuit_id)
        return [PartyDetail(party=party, customer_name=name) for party, name in rows]

    async def add_party(self, lawsuit: Lawsuit, payload: PartyCreateRequest) -> PartyDetail:
        customer_name = await self._customer_name(payload.customer_id)
        await self._ensure_not_duplicate(
            lawsuit_id=lawsuit.id, customer_id=payload.customer_id, pole=payload.pole
        )
        party = await self.parties.create(
            LawsuitParty(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit.id,
                customer_id=payload.customer_id,
                pole=payload.pole,
                is_client=payload.is_client,
            )
        )
        return PartyDetail(party=party, customer_name=customer_name)

    async def update_party(self, party: LawsuitParty, payload: PartyUpdateRequest) -> PartyDetail:
        if payload.pole != party.pole:
            await self._ensure_not_duplicate(
                lawsuit_id=party.lawsuit_id,
                customer_id=party.customer_id,
                pole=payload.pole,
                exclude_id=party.id,
            )
        party.pole = payload.pole
        if payload.is_client is not None:
            party.is_client = payload.is_client
        customer_name = await self._customer_name(party.customer_id)
        return PartyDetail(party=party, customer_name=customer_name)

    async def remove_party(self, party: LawsuitParty) -> None:
        # Regra 1: o processo precisa ficar com no mínimo 1 parte.
        if await self.parties.count_for_lawsuit(party.lawsuit_id) <= 1:
            raise LastPartyError
        await self.parties.delete(party)

    async def validate_party_inputs(self, parties: Sequence[PartyInput]) -> None:
        """Validação do POST de processo: sem duplicata no payload e todo contato existe."""
        seen: set[tuple[uuid.UUID, str]] = set()
        for party_input in parties:
            key: tuple[uuid.UUID, str] = (party_input.customer_id, party_input.pole)
            if key in seen:
                raise DuplicatePartyError
            seen.add(key)
            if await self.customers.get_by_id(party_input.customer_id) is None:
                raise PartyCustomerNotFoundError

    async def create_party(self, lawsuit_id: uuid.UUID, party_input: PartyInput) -> None:
        await self.parties.create(
            LawsuitParty(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit_id,
                customer_id=party_input.customer_id,
                pole=party_input.pole,
                is_client=party_input.is_client,
            )
        )

    async def _customer_name(self, customer_id: uuid.UUID) -> str:
        customer = await self.customers.get_by_id(customer_id)
        if customer is None:
            raise PartyCustomerNotFoundError
        return customer.name

    async def _ensure_not_duplicate(
        self,
        *,
        lawsuit_id: uuid.UUID,
        customer_id: uuid.UUID,
        pole: PartyPole,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        duplicate = await self.parties.find_duplicate(
            lawsuit_id=lawsuit_id, customer_id=customer_id, pole=pole, exclude_id=exclude_id
        )
        if duplicate is not None:
            raise DuplicatePartyError
