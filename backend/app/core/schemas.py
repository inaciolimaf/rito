from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# Dinheiro no banco é Decimal (CLAUDE.md §9); JSON não tem esse tipo — serializa como
# float pro corpo da resposta. Extraído pra cá na spec 055 (regra dos 3 usos: lawsuits,
# crm e financial já precisavam do mesmo alias).
JsonDecimal = Annotated[Decimal, PlainSerializer(lambda value: float(value), return_type=float)]
