"""Invariante de programador que sobrevive ao `python -O` (spec 115).

## O problema com `assert` em produção

`assert x is not None` some inteiro sob `python -O`. Não vira erro, não vira aviso: a
linha deixa de existir. O código segue com `None` na mão e falha metros adiante, num
`AttributeError` que não diz nada sobre o que realmente quebrou — ou, pior, não falha e
grava dado errado.

O projeto tinha 47 desses em `app/`, quase todos com o mesmo formato: estreitar um
`T | None` para `T` depois de uma busca que a regra de negócio garante ter achado algo. São
invariantes verdadeiros, e é exatamente por isso que o `assert` parecia inofensivo.

## Por que uma função, e não um `if` em cada lugar

`if x is None: raise ...` custa duas linhas e um ramo a mais em cada um dos 30 pontos — e
o ramo é intestável por definição, porque a condição não pode acontecer. Trinta ramos
mortos afundariam a cobertura e o gate de complexidade da 106 junto.

`not_none` resolve os três de uma vez: uma linha no ponto de uso, zero ramos novos lá, e o
`mypy` estreita o tipo pelo retorno como estreitava pelo `assert`. O único ramo morto do
projeto inteiro é o desta função, testado uma vez.
"""


class InvariantError(RuntimeError):
    """Uma garantia do próprio código não se sustentou.

    Deliberadamente NÃO é um erro de domínio: nada deve capturá-la. Se ela sobe, o defeito
    é do Rito — vira 500, entra no log e alguém conserta. Um erro de domínio diria ao
    usuário que ele fez algo errado, e ele não fez.
    """


def not_none[T](value: T | None, why: str) -> T:
    """`value`, garantido não-nulo, ou `InvariantError` explicando o que se esperava.

    O `why` descreve a GARANTIA que falhou, não o sintoma: «o RLS já filtrou por tenant»,
    «validado em validate_references». É o que a pessoa de plantão precisa ler para saber
    onde procurar — e é a razão de o parâmetro ser obrigatório.
    """
    if value is None:
        raise InvariantError(why)
    return value
