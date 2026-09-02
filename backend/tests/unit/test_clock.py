"""O relógio por escritório (spec 114, regras 3, 4 e 6).

Nenhum teste aqui congela o tempo nem lê o relógio do sistema para afirmar resultado. A
determinação vem da geografia: `Pacific/Kiritimati` (UTC+14) e `Pacific/Niue` (UTC−11)
estão **25 horas** apart, mais que um dia inteiro, então a data dos dois é diferente em
todo instante do ano. Um teste que só passa entre meia-noite e duas da manhã seria pior
que teste nenhum — é exatamente o defeito que a dívida 30 descreve.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.clock import Clock
from app.domain.account.models import DEFAULT_TIMEZONE


def test_today_e_o_dia_da_conta_e_nao_o_do_processo() -> None:
    # 25 horas de diferença: não existe instante em que estes dois estejam no mesmo dia.
    assert Clock("Pacific/Kiritimati").today() != Clock("Pacific/Niue").today()


def test_today_confere_com_o_fuso_declarado() -> None:
    for nome in ("America/Sao_Paulo", "America/Rio_Branco", "Europe/Lisbon"):
        relogio = Clock(nome)
        # `datetime.now(tz)` é a definição de «que dia é lá»; o relógio não pode discordar
        # dela por mais que o intervalo entre as duas chamadas.
        assert relogio.today() in {
            datetime.now(tz=ZoneInfo(nome)).date(),
            relogio.now().date(),
        }


def test_conta_sem_fuso_cai_no_padrao() -> None:
    # Conta ainda não criada (primeiro login de um tenant novo) chega como None. O que
    # NÃO pode acontecer é cair no fuso do servidor, que é o bug que a spec conserta.
    assert Clock(None).timezone == ZoneInfo(DEFAULT_TIMEZONE)
    assert Clock().timezone == ZoneInfo(DEFAULT_TIMEZONE)


def test_now_e_sempre_aware() -> None:
    agora = Clock("America/Rio_Branco").now()
    # `datetime.now()` sem tz é a outra metade do mesmo bug (DTZ005). Um datetime naive
    # comparado com um aware levanta TypeError em produção, não no teste.
    assert agora.tzinfo is not None
    assert agora.utcoffset() is not None


def test_today_devolve_date_e_nao_datetime() -> None:
    hoje = Clock("Europe/Lisbon").today()
    assert isinstance(hoje, date)
    assert not isinstance(hoje, datetime)
