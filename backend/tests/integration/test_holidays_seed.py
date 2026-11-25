"""O seed de feriados tem data de validade, e ela precisa avisar antes de vencer.

A tabela `holidays` foi semeada até 2030 pela spec 038 e até 2040 pela 126. Quando ela
acaba, nada quebra: `is_business_day` passa a responder `True` para um feriado, e todo
prazo processual contado a partir dali vence **antes da hora** — continuando a parecer uma
data plausível. É a falha mais silenciosa que este projeto tem, e a 038 já a previu num
comentário. Comentário não avisa ninguém: dez anos depois, quem lê o código não é quem o
escreveu.

## Este teste depende da data em que roda, e isso é DELIBERADO

A spec 129 acabou de consertar o oposto — um teste cuja dependência do relógio era
**acidental** (`test_cartao_mostra_fatura_nao_saldo`, dívida 41), e que por isso virou
vermelho sem nenhuma regressão. A diferença não é o relógio, é a intenção:

- lá, o tempo passando quebrava uma afirmação que continuava verdadeira;
- aqui, o tempo passando torna a afirmação **falsa de verdade** — a tabela realmente fica
  curta demais para contar prazo com segurança.

Um teste que reprova quando o mundo mudou é a definição de teste bom. O que este arquivo
compra é a MARGEM: ele grita três anos antes de a tabela esvaziar, e não no dia.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.workflows.models import Holiday
from tests.clock import hoje

# Três anos de antecedência. O prazo mais longo que o produto conta é de dias corridos com
# prorrogação — meses, não anos —, então três anos não é margem para o CÁLCULO: é margem
# para a ORGANIZAÇÃO. É o tempo de alguém ver o vermelho, achar a fonte oficial dos
# feriados móveis e abrir a migration sem pressa.
COBERTURA_MINIMA_ANOS = 3


async def test_seed_de_feriados_cobre_os_proximos_anos(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        ultimo = (await conn.execute(select(func.max(Holiday.id)))).scalar_one_or_none()

    assert ultimo is not None, (
        "a tabela `holidays` está VAZIA — todo prazo processual passaria a contar feriado "
        "como dia útil e venceria antes da hora"
    )
    # `tests.clock.hoje()` e não `date.today()`: o dia é o do FUSO DO ESCRITÓRIO
    # (spec 114, dívida 32) — e a regra `DTZ` do lint reprova o relógio sem fuso.
    exigido = date(hoje().year + COBERTURA_MINIMA_ANOS, 12, 31)
    assert ultimo >= exigido, (
        f"o seed de feriados vai até {ultimo:%d/%m/%Y} e falta menos de "
        f"{COBERTURA_MINIMA_ANOS} anos para ele acabar (dívida 42).\n"
        "Isto NÃO é um teste quebrado — é o aviso de que a tabela precisa do próximo seed. "
        "Escreva uma migration nova no mesmo formato da `126_prazo_das_intimacoes` "
        "(9 fixos + 4 móveis derivados da Páscoa) antes que ela esvazie: prazo contado "
        "contra tabela vazia vence cedo e continua parecendo uma data plausível."
    )
