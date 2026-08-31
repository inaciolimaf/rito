"""Spec 100 — as invariantes que a auditoria final transforma em gate permanente.

Uma auditoria feita à mão vale pelo dia em que foi feita. O que sobrevive a ela é o
teste: cada item desta spec que dava para verificar automaticamente virou um, para a
próxima spec não precisar redescobrir o mesmo problema.
"""

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
TESTS = BACKEND / "tests"
RAIZ = BACKEND.parent
FRONT = RAIZ / "frontend" / "src"
E2E = RAIZ / "e2e" / "tests"

# Um silenciamento justificado tem o porquê na própria linha ou nas linhas logo acima.
# Não é frescura de estilo: `# type: ignore` sem motivo é uma decisão que ninguém
# consegue revisar depois — nem para confirmar que continua válida, nem para removê-la.
LINHAS_DE_CONTEXTO = 4


def arquivos(raiz: Path, *sufixos: str) -> list[Path]:
    return sorted(
        caminho
        for sufixo in sufixos
        for caminho in raiz.rglob(f"*{sufixo}")
        if "__pycache__" not in caminho.parts and "node_modules" not in caminho.parts
    )


# Os marcadores em si não são justificativa — `# type: ignore[attr-defined]` explica o
# QUE está sendo silenciado, nunca o porquê. São removidos antes de procurar a prosa.
_MARCADORES = re.compile(r"#\s*(type:\s*ignore(\[[a-z-]+\])?|noqa(:\s*[A-Z0-9, ]+)?)")


def tem_justificativa(linhas: list[str], indice: int) -> bool:
    """Há prosa explicando, na linha ou nas quatro acima?

    O critério é grosseiro de propósito: qualquer comentário com mais de vinte
    caracteres de texto conta. Não dá para verificar automaticamente se a explicação é
    BOA; dá para verificar se alguém foi obrigado a escrever uma, e é isso que impede o
    silenciamento reflexo.
    """
    janela = linhas[max(0, indice - LINHAS_DE_CONTEXTO) : indice + 1]
    for linha in janela:
        _, _, comentario = _MARCADORES.sub("#", linha).partition("#")
        if len(comentario.strip(" -—:")) >= 20:
            return True
    return False


def test_todo_type_ignore_tem_justificativa() -> None:
    """§8: zero `# type: ignore` sem justificativa.

    Não são proibidos — há limitações reais de stub de terceiros. O que é proibido é
    silenciar sem dizer por quê: seis meses depois ninguém sabe se a biblioteca ganhou
    stub e o silenciamento pode sair.
    """
    ofensores: list[str] = []
    for caminho in arquivos(APP, ".py"):
        linhas = caminho.read_text().splitlines()
        for i, linha in enumerate(linhas):
            if "type: ignore" in linha and not tem_justificativa(linhas, i):
                ofensores.append(f"{caminho.relative_to(RAIZ)}:{i + 1}")

    assert ofensores == [], "type: ignore sem justificativa:\n  " + "\n  ".join(ofensores)


def test_nenhum_as_any_no_frontend() -> None:
    """§8. `as any` desliga o TypeScript exatamente onde ele seria útil — na fronteira
    entre o que a API devolve e o que a tela espera."""
    ofensores = [
        f"{caminho.relative_to(RAIZ)}:{i + 1}"
        for caminho in arquivos(FRONT, ".ts", ".tsx")
        for i, linha in enumerate(caminho.read_text().splitlines())
        if re.search(r"\bas\s+any\b", linha)
    ]

    assert ofensores == [], "as any no frontend:\n  " + "\n  ".join(ofensores)


def test_nenhum_todo_ou_fixme_orfao() -> None:
    """§5: cada um vira issue ou some.

    `TODO` que ninguém vai fazer é ruído que treina o leitor a ignorar comentários — e
    o próximo, o que importava, some junto.
    """
    padrao = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b|//\s*(TODO|FIXME|XXX|HACK)\b")
    ofensores = [
        f"{caminho.relative_to(RAIZ)}:{i + 1}"
        for caminho in [*arquivos(APP, ".py"), *arquivos(FRONT, ".ts", ".tsx")]
        for i, linha in enumerate(caminho.read_text().splitlines())
        if padrao.search(linha)
    ]

    assert ofensores == [], "TODO/FIXME órfão:\n  " + "\n  ".join(ofensores)


def test_nenhum_teste_dorme_para_esperar() -> None:
    """§4 e CLAUDE.md §3: nunca `sleep` para ESPERAR.

    Teste que dorme para esperar é lento quando passa e mentiroso quando falha — o
    número que ele escolhe nunca é o certo para todas as máquinas. Espera por condição.

    O que a regra não proíbe é dormir para **simular travamento**: um dublê que nunca
    responde é a única forma de provar que um timeout corta. Esse sleep jamais decorre —
    o timeout o interrompe —, e a distinção entre os dois usos é exatamente o que o
    comentário obrigatório força quem escreve a declarar.
    """
    ofensores: list[str] = []
    for caminho in arquivos(TESTS, ".py"):
        linhas = caminho.read_text().splitlines()
        for i, linha in enumerate(linhas):
            if re.search(r"\b(time\.sleep|asyncio\.sleep)\s*\(", linha) and not tem_justificativa(
                linhas, i
            ):
                ofensores.append(f"{caminho.relative_to(RAIZ)}:{i + 1}")

    assert ofensores == [], "sleep sem justificativa em teste:\n  " + "\n  ".join(ofensores)


def test_nenhum_teste_e_pulado_sem_justificativa() -> None:
    """§4. Teste pulado é teste que não existe, com a aparência de que existe."""
    ofensores: list[str] = []
    for caminho in arquivos(TESTS, ".py"):
        linhas = caminho.read_text().splitlines()
        for i, linha in enumerate(linhas):
            if re.search(r"@pytest\.mark\.skip|pytest\.skip\(", linha) and not tem_justificativa(
                linhas, i
            ):
                ofensores.append(f"{caminho.relative_to(RAIZ)}:{i + 1}")

    assert ofensores == [], "teste pulado sem justificativa:\n  " + "\n  ".join(ofensores)


def test_e2e_dentro_do_teto_de_25_jornadas() -> None:
    """CLAUDE.md §3. O e2e é a suíte mais cara por caso; sem teto ela cresce até ser o
    único poste que importa, e aí ninguém mais roda a suíte inteira localmente."""
    jornadas = sum(
        len(re.findall(r"^\s*test\(", caminho.read_text(), flags=re.M))
        for caminho in arquivos(E2E, ".spec.ts")
    )

    assert jornadas <= 25, f"{jornadas} jornadas e2e — o teto é 25"


def test_toda_rota_declara_permissao() -> None:
    """§3: nenhuma rota nasce aberta.

    O padrão do Rito é a permissão vir por `Depends(require_role(...))` ou
    `require_financial(...)`. Rota sem nenhum dos dois só é legítima quando é pública de
    propósito — e a lista dessas é curta e fechada aqui, para uma rota nova não entrar
    nela por descuido.
    """
    PUBLICAS = {
        # Autenticação: quem chama ainda não tem identidade.
        "app/domain/auth/router.py",
        # Aceite de convite: o usuário só passa a existir depois dela.
        "app/domain/users/router.py",
        # Health e métricas: infraestrutura, não domínio (spec 097).
        "app/core/health.py",
        # API pública: autoriza por token e escopo, não por perfil (spec 095).
        "app/public/router.py",
        # Feed iCal por token de assinatura (spec 037).
        "app/domain/schedule/router.py",
        # Catálogos globais e biblioteca pública, legíveis por qualquer autenticado.
        "app/domain/locations/router.py",
        "app/domain/courts/router.py",
    }
    ofensores: list[str] = []
    for caminho in arquivos(APP, ".py"):
        relativo = str(caminho.relative_to(RAIZ / "backend"))
        if not relativo.endswith("router.py") or relativo in PUBLICAS:
            continue
        arvore = ast.parse(caminho.read_text())
        for no in ast.walk(arvore):
            if not isinstance(no, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            decoradores = " ".join(ast.unparse(d) for d in no.decorator_list)
            if not re.search(r"router\.(get|post|put|patch|delete)", decoradores):
                continue
            assinatura = ast.unparse(no.args)
            if not re.search(r"require_role|require_financial|require_scope", assinatura):
                ofensores.append(f"{relativo}:{no.lineno} {no.name}")

    assert ofensores == [], "rota sem permissão declarada:\n  " + "\n  ".join(ofensores)


@pytest.mark.parametrize(
    "documento",
    [
        "README.md",
        "CLAUDE.md",
        "ROADMAP.md",
        "docs/ARQUITETURA.md",
        "docs/DECISOES.md",
        "docs/DIVIDA-TECNICA.md",
        "docs/PERFORMANCE.md",
        "docs/RUNBOOK.md",
        "docs/SEGURANCA-RLS.md",
        "docs/SEGURANCA-IA.md",
    ],
)
def test_documento_obrigatorio_existe_e_nao_esta_vazio(documento: str) -> None:
    """§6. Um documento que a spec promete e não existe é pior que um que não foi
    prometido — quem procura desiste achando que a informação está em outro lugar."""
    caminho = RAIZ / documento

    assert caminho.exists(), f"{documento} não existe"
    assert len(caminho.read_text()) > 500, f"{documento} está praticamente vazio"


def test_nenhuma_fixture_tem_cpf_ou_cnpj_de_pessoa_real() -> None:
    """§3: nenhum dado pessoal nas fixtures.

    As fixtures do DJEN/DataJud foram gravadas ao vivo da API pública (specs 042–047) e
    trouxeram junto os nomes das partes e um CPF completo. Juridicamente é dado público —
    comunicação processual É pública por lei —, mas guardá-lo num repositório é uma
    decisão diferente de o tribunal publicá-lo, e não é nossa para tomar.
    Anonimizadas na 100, preservando a forma (mesma quantidade de destinatários, mesmo
    formato de nome e documento) para os ~40 testes que dependem delas não notarem.

    O único CPF que sobra é o `111.444.777-35`, sintético e de formato válido, usado como
    documento de teste em todo lugar.
    """
    CPF_DE_TESTE = "111.444.777-35"
    padrao = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")

    ofensores: list[str] = []
    for caminho in arquivos(TESTS / "fixtures", ".json"):
        for i, linha in enumerate(caminho.read_text().splitlines()):
            for achado in padrao.findall(linha):
                if achado != CPF_DE_TESTE:
                    ofensores.append(f"{caminho.relative_to(RAIZ)}:{i + 1} → {achado}")

    assert ofensores == [], "documento de pessoa real em fixture:\n  " + "\n  ".join(ofensores)


def test_cabecalho_de_cada_spec_concorda_com_o_roadmap() -> None:
    """§2, coerência — e uma divergência que só a auditoria final expôs.

    O `ROADMAP.md` é a fila; o cabeçalho de cada `specs/NNN-*.md` repete o mesmo estado.
    Duas fontes para o mesmo fato divergem, e divergiram: catorze specs marcadas ✅ no
    roadmap continuavam ⬜ no próprio arquivo, porque o ciclo que as fechou atualizou uma
    metade. Quem abrisse a spec 017 leria "pendente" sobre código que está em produção.

    Também exige um arquivo por número. Quatro specs tinham DUAS versões (a planejada e a
    expandida, com nomes diferentes), e a busca por `grep 06X` trazia as duas.
    """
    specs = RAIZ / "specs"
    roadmap = (RAIZ / "ROADMAP.md").read_text()

    concluidas_no_roadmap = set(re.findall(r"^### ✅ (\d{3}) ", roadmap, flags=re.M))
    divergentes: list[str] = []
    por_numero: dict[str, list[str]] = {}

    for caminho in sorted(specs.glob("*.md")):
        numero = caminho.name[:3]
        if not numero.isdigit() or numero == "000":
            continue
        por_numero.setdefault(numero, []).append(caminho.name)
        cabecalho = caminho.read_text()[:400]
        concluida_no_arquivo = "**Status:** ✅" in cabecalho
        if concluida_no_arquivo != (numero in concluidas_no_roadmap):
            divergentes.append(
                f"{caminho.name}: arquivo diz "
                f"{'✅' if concluida_no_arquivo else '⬜'}, roadmap diz "
                f"{'✅' if numero in concluidas_no_roadmap else '⬜'}"
            )

    duplicadas = [
        f"{numero}: {', '.join(nomes)}" for numero, nomes in por_numero.items() if len(nomes) > 1
    ]

    assert divergentes == [], "spec e roadmap discordam:\n  " + "\n  ".join(divergentes)
    assert duplicadas == [], "mais de um arquivo para o mesmo número:\n  " + "\n  ".join(duplicadas)


# ─────────────────────────────────────────────────────────────────────────────
# Spec 101 — os meta-testes que impedem o 14º item de nascer
#
# Corrigir 13 stubs é trabalho de um ciclo; impedir que o 14º apareça é o que evita a
# spec 201. Cada teste abaixo fecha uma das formas pelas quais a dívida escapou de 100
# specs de revisão.
# ─────────────────────────────────────────────────────────────────────────────

ROADMAP = RAIZ / "ROADMAP.md"
DIVIDA = RAIZ / "docs" / "DIVIDA-TECNICA.md"

# "chega na spec 022", "chegam na spec 056", "só chega na 017", "até a spec 032",
# "spec 015 (Descobertas)" — as cinco formas que os cinco stubs usaram para dizer
# "a dependência ainda não existe".
_ADIAMENTO = re.compile(
    r"(?:chega(?:m)? na spec (\d{3})"
    r"|só chega na (\d{3})"
    r"|até a spec (\d{3})"
    r"|spec (\d{3}) \(Descobertas\))",
    re.IGNORECASE,
)


def _specs_concluidas() -> set[str]:
    """Números marcados com ✅ no ROADMAP — as specs que já entregaram."""
    texto = ROADMAP.read_text(encoding="utf-8")
    return set(re.findall(r"###\s*✅\s*(\d{3})", texto))


def test_nenhum_comentario_adia_para_spec_ja_concluida() -> None:
    """A assinatura EXATA dos cinco stubs da spec 101: um comentário dizendo "nada
    referencia isto ainda, chega na spec NNN" sobre uma dependência que existe há
    dezenas de specs.

    Sozinho, este teste teria pegado as etapas, as origens, as categorias, as contas e a
    dívida nº 13 — sem ninguém precisar reler 100 specs.

    Quando a dependência chega, ou o código é implementado, ou o comentário passa a
    apontar para uma dívida numerada. O que não pode é continuar dizendo que a spec
    ainda não passou quando ela já passou.
    """
    concluidas = _specs_concluidas()
    assert concluidas, "ROADMAP sem nenhuma spec ✅ — regex de leitura quebrou"

    ofensores: list[str] = []
    for caminho in arquivos(APP, ".py"):
        for numero_linha, linha in enumerate(
            caminho.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for grupos in _ADIAMENTO.findall(linha):
                alvo = next(filter(None, grupos), None)
                if alvo in concluidas:
                    ofensores.append(
                        f"{caminho.relative_to(APP)}:{numero_linha} adia para a spec "
                        f"{alvo}, que já está ✅: {linha.strip()}"
                    )

    assert not ofensores, "comentário de produção adiando para spec já concluída:\n" + "\n".join(
        ofensores
    )


def test_toda_divida_aberta_tem_numero_e_alvo_no_futuro() -> None:
    """Regra 24 da spec 101. O `DIVIDA-TECNICA.md` abre dizendo que "se uma spec-alvo já
    passou e o item continua aqui, a próxima refatoração decide" — isso é uma regra, e
    regra sem teste é intenção.

    Duas formas de escapar, as duas fechadas aqui:
    - **sem número:** foi como a dívida do SAVEPOINT sobreviveu à 100, cuja tabela de
      fechamento contava itens numerados;
    - **alvo vencido:** o item continua aberto apontando para uma spec que já entregou.
    """
    texto = DIVIDA.read_text(encoding="utf-8")
    concluidas = _specs_concluidas()

    problemas: list[str] = []

    # Todo título de item é `## <n>. <titulo>`; item resolvido vem com ~~tachado~~ ou
    # com "RESOLVIDO" no próprio título.
    for titulo in re.findall(r"^## (.+)$", texto, re.MULTILINE):
        if titulo.startswith(("Estado no fechamento", "Dívida técnica")):
            continue
        if "RESOLVIDO" in titulo or titulo.startswith("~~"):
            continue
        if not re.match(r"^\d+\.\s", titulo):
            problemas.append(f"item sem número: {titulo!r}")

    # Spec-alvo de item ainda aberto não pode ser uma spec já entregue.
    for bloco in re.split(r"^## ", texto, flags=re.MULTILINE)[1:]:
        cabecalho = bloco.splitlines()[0]
        if "RESOLVIDO" in bloco.split("\n\n")[0] or cabecalho.startswith("~~"):
            continue
        for alvo in re.findall(r"\*\*Spec-alvo:\*\*\s*(\d{3})", bloco):
            if alvo in concluidas:
                problemas.append(
                    f"item {cabecalho.split('.')[0]!r} aberto com spec-alvo {alvo}, já ✅"
                )

    assert not problemas, "DIVIDA-TECNICA.md fora da própria regra:\n" + "\n".join(problemas)
