"""`docs/GATES.md` lista todo gate que existe (spec 120, §10).

Um registro de gates que ninguém verifica apodrece em duas specs — e apodrece do jeito
pior: continua parecendo completo. O arquivo existe porque, depois de vinte specs de
qualidade, ninguém consegue responder «quantos gates o Rito tem» sem ler seis arquivos de
configuração e dezoito meta-testes; se ele ficar desatualizado, volta a não responder.

O teste é o mesmo idioma do `test_cabecalho_de_cada_spec_concorda_com_o_roadmap` (spec
100): duas fontes para o mesmo fato, uma delas verificada contra a outra.

**O que este teste NÃO faz:** conferir que a descrição de cada gate está certa. Ele confere
que cada gate tem LINHA. Descrição errada é problema de revisão; gate ausente é problema de
inventário, e é o que apodrece sozinho.
"""

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RAIZ = BACKEND.parent
GATES = RAIZ / "docs" / "GATES.md"


def _texto() -> str:
    return GATES.read_text()


def test_arquivo_existe_e_nao_esta_vazio() -> None:
    assert GATES.exists(), "docs/GATES.md sumiu — a spec 120 o entregou"
    assert len(_texto()) > 2000, "docs/GATES.md ficou curto demais para listar os gates"


def test_toda_regra_do_select_do_ruff_tem_linha() -> None:
    """Cada família no `select` do `pyproject.toml` aparece no registro.

    É o inventário mais volátil dos três: ligar regra nova é uma linha de config, e é
    exatamente o tipo de mudança que ninguém lembra de documentar.
    """
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    regras = config["tool"]["ruff"]["lint"]["select"]
    texto = _texto()
    faltando = [regra for regra in regras if f"`{regra}`" not in texto]
    assert faltando == [], (
        "regra do Ruff ligada e ausente de docs/GATES.md — um gate que ninguém sabe que "
        "existe é um gate que ninguém defende:\n  " + "\n  ".join(faltando)
    )


def test_todo_teto_numerico_do_ruff_tem_linha_com_o_VALOR_atual() -> None:
    """E com o valor de hoje, não com o de quando o registro foi escrito.

    Conferir o número, e não só o nome, é o que faz este teste pegar o caso que importa:
    alguém mexe no teto e a página continua anunciando o antigo.
    """
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    lint = config["tool"]["ruff"]["lint"]
    tetos = {
        "max-complexity": lint["mccabe"]["max-complexity"],
        "max-branches": lint["pylint"]["max-branches"],
        "max-returns": lint["pylint"]["max-returns"],
        "max-statements": lint["pylint"]["max-statements"],
        "max-args": lint["pylint"]["max-args"],
    }
    texto = _texto()
    divergentes = [
        f"{nome} = {valor} (o registro não mostra `**{valor}**`)"
        for nome, valor in tetos.items()
        if f"`{nome}`" not in texto or f"**{valor}**" not in texto
    ]
    assert divergentes == [], "docs/GATES.md desatualizado:\n  " + "\n  ".join(divergentes)


def test_piso_de_cobertura_do_backend_confere() -> None:
    """O piso que o CI aplica é o do `pyproject.toml`; o registro tem que repeti-lo certo."""
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    piso = config["tool"]["coverage"]["report"]["fail_under"]
    assert (
        f"**{piso}%**" in _texto()
    ), f"piso de cobertura do backend é {piso}% e docs/GATES.md não diz isso"


def test_todo_meta_teste_tem_linha() -> None:
    """Cada arquivo de `tests/meta/` aparece no registro pelo nome.

    Meta-teste é gate que não mora em arquivo de configuração — some do radar mais fácil
    que uma regra de lint, porque nada além dele mesmo o anuncia.
    """
    arquivos = sorted(
        p.name for p in (BACKEND / "tests" / "meta").glob("test_*.py") if p.name != "__init__.py"
    )
    texto = _texto()
    faltando = [nome for nome in arquivos if nome not in texto]
    assert faltando == [], "meta-teste sem linha em docs/GATES.md:\n  " + "\n  ".join(faltando)


def test_toda_regra_propria_de_eslint_tem_linha() -> None:
    """As regras escritas à mão em `frontend/eslint-rules/` são gates do projeto, não do
    ecossistema — se não estiverem aqui, ninguém fora de quem as escreveu vai saber."""
    regras = sorted(p.stem for p in (RAIZ / "frontend" / "eslint-rules").glob("*.js"))
    texto = _texto()
    faltando = [nome for nome in regras if nome not in texto]
    assert faltando == [], "regra própria de ESLint sem linha em docs/GATES.md:\n  " + "\n  ".join(
        faltando
    )


def test_todo_per_file_ignores_esta_declarado() -> None:
    """Exceção por arquivo é o furo mais discreto de um gate: some do relatório e não
    aparece em nenhum lugar, exceto no `pyproject.toml`."""
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    excecoes = config["tool"]["ruff"]["lint"]["per-file-ignores"]
    texto = _texto()
    faltando = [padrao for padrao in excecoes if f"`{padrao}`" not in texto]
    assert faltando == [], "`per-file-ignores` não declarado em docs/GATES.md:\n  " + "\n  ".join(
        faltando
    )


def test_o_registro_nao_promete_gate_que_nao_existe() -> None:
    """O outro sentido: o registro citando meta-teste que já foi apagado.

    Um inventário que lista o que não existe é pior que um incompleto — ele dá confiança
    em proteção que não está lá.
    """
    citados = set(re.findall(r"`(test_\w+\.py)`", _texto()))
    existentes = {p.name for p in (BACKEND / "tests" / "meta").glob("test_*.py")}
    fantasmas = sorted(citados - existentes)
    assert fantasmas == [], "docs/GATES.md cita meta-teste que não existe mais:\n  " + "\n  ".join(
        fantasmas
    )
