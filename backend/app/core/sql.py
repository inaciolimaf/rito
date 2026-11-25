"""O que o query builder não tem literal para escrever (spec 127).

A 127 tirou a SQL em string do backend. Quase tudo virou `select`/`insert`/`update`
direto, mas uma construção resistiu em cinco lugares — e é justamente a que mais tentava
a f-string, porque o SQLAlchemy não tem literal para ela:

    func.now() - text(f"interval '{days} days'")

O `text()` ali não era preguiça. Somar um `datetime.timedelta` do Python a uma coluna
`timestamptz` faz o SQLAlchemy emitir `INTERVAL` com uma coerção de tipo ambígua, e o
comentário de `listing.py::_idle` registrava isso desde a spec 027. `make_interval` é a
saída: é função regular do Postgres, aceita o número como parâmetro LIGADO e devolve
`interval` sem ambiguidade nenhuma.

O que se ganha não é estética. Enquanto o intervalo era f-string, `stagnation_service`
precisava de um comentário explicando por que aquilo não era injeção («`stagnant_days` já
foi validado como int > 0») — uma garantia que morava na cabeça de quem leu o schema da
etapa, não no código. Agora o número viaja ligado e a pergunta não se faz mais.
"""

from datetime import timedelta

from sqlalchemy import ColumnElement, Interval, func


def days_interval(days: int | ColumnElement[int]) -> ColumnElement[timedelta]:
    """`interval 'N days'`, com `N` ligado — `make_interval(0, 0, 0, N)`.

    Os três zeros são anos, meses e semanas: `make_interval` só aceita notação
    posicional pelo `func` do SQLAlchemy (a nomeada, `days => N`, é sintaxe do
    Postgres que o builder não emite).
    """
    return func.make_interval(0, 0, 0, days, type_=Interval())
