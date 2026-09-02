"""O «hoje» dos testes, que precisa ser o mesmo «hoje» do escritório (spec 114).

Antes desta spec, app e teste concordavam por acidente: os dois chamavam `date.today()`
e liam o relógio do processo. Depois dela, o app passou a ler o fuso da conta — e o
tenant que as fixtures criam nasce em `DEFAULT_TIMEZONE` (`America/Sao_Paulo`, spec 011).

Um teste que continuasse em `date.today()` passaria a discordar do app por três horas
todo fim de noite, que é exatamente a **dívida 30**: a suíte ficava vermelha depois das
21h de Brasília porque o processo (UTC) já tinha virado o dia e o escritório não. Usar
este helper faz teste e aplicação responderem a mesma coisa em qualquer hora do dia.

Quem só precisa de *uma data qualquer* — âncora de subtração, valor de campo que ninguém
compara com o presente — deve usar um literal, não isto. `hoje()` é para quando o teste
afirma algo **sobre o presente**.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.clock import Clock
from app.domain.account.models import DEFAULT_TIMEZONE


def hoje() -> date:
    """O dia corrente no fuso em que as fixtures criam a conta.

    Não recebe fuso de propósito: teste que precise de outro fuso está afirmando algo
    sobre multi-fuso e deve construir o `Clock` explicitamente, como faz
    `test_clock_tenant.py`.
    """
    return Clock(DEFAULT_TIMEZONE).today()


def dia_do_escritorio(instante: datetime) -> date:
    """O dia em que `instante` cai, no fuso do escritório.

    O par de `hoje()` para quando o teste injeta um instante em vez de usar o presente —
    é o caso dos testes de caos, que simulam relógio adiantado ou atrasado. Antes da spec
    114 esses testes comparavam com `instante.date()`, o dia UTC; o app agora converte
    para o fuso da conta antes de decidir o dia, e o teste tem que fazer a mesma conta.
    """
    return instante.astimezone(ZoneInfo(DEFAULT_TIMEZONE)).date()
