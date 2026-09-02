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
        if relativo.endswith("router.py") and relativo not in PUBLICAS:
            ofensores += _rotas_sem_permissao(caminho, relativo)

    assert ofensores == [], "rota sem permissão declarada:\n  " + "\n  ".join(ofensores)


def _rotas_sem_permissao(caminho: Path, relativo: str) -> list[str]:
    """As rotas de UM arquivo que não declaram permissão na assinatura.

    A permissão é procurada nos ARGUMENTOS, não no corpo: `Depends(require_role(...))` é
    contrato da rota e aparece no OpenAPI; uma checagem escondida no meio do corpo não
    aparece, e é justamente essa a que passa despercebida numa revisão.
    """
    ofensores: list[str] = []
    for no in ast.walk(ast.parse(caminho.read_text())):
        if not isinstance(no, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        decoradores = " ".join(ast.unparse(d) for d in no.decorator_list)
        if not re.search(r"router\.(get|post|put|patch|delete)", decoradores):
            continue
        if not re.search(r"require_role|require_financial|require_scope", ast.unparse(no.args)):
            ofensores.append(f"{relativo}:{no.lineno} {no.name}")
    return ofensores


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
    problemas = _itens_sem_numero(texto) + _alvos_ja_entregues(texto, _specs_concluidas())
    assert not problemas, "DIVIDA-TECNICA.md fora da própria regra:\n" + "\n".join(problemas)


def _e_item_resolvido(cabecalho: str) -> bool:
    """Resolvido vem com ~~tachado~~ ou com "RESOLVIDO" no próprio título."""
    return "RESOLVIDO" in cabecalho or cabecalho.startswith("~~")


def _itens_sem_numero(texto: str) -> list[str]:
    """Todo título de item é `## <n>. <titulo>`.

    Sem número foi como a dívida do SAVEPOINT sobreviveu à 100, cuja tabela de fechamento
    contava itens numerados.
    """
    return [
        f"item sem número: {titulo!r}"
        for titulo in re.findall(r"^## (.+)$", texto, re.MULTILINE)
        if not titulo.startswith(("Estado no fechamento", "Dívida técnica"))
        and not _e_item_resolvido(titulo)
        and not re.match(r"^\d+\.\s", titulo)
    ]


def _alvos_ja_entregues(texto: str, concluidas: set[str]) -> list[str]:
    """Spec-alvo de item ainda ABERTO não pode ser uma spec já entregue."""
    problemas: list[str] = []
    for bloco in re.split(r"^## ", texto, flags=re.MULTILINE)[1:]:
        cabecalho = bloco.splitlines()[0]
        if _e_item_resolvido(bloco.split("\n\n")[0]) or cabecalho.startswith("~~"):
            continue
        problemas += [
            f"item {cabecalho.split('.')[0]!r} aberto com spec-alvo {alvo}, já ✅"
            for alvo in re.findall(r"\*\*Spec-alvo:\*\*\s*(\d{3})", bloco)
            if alvo in concluidas
        ]
    return problemas


def test_toda_rota_do_menu_lateral_existe_em_app_tsx() -> None:
    """Regra 17 da spec 101/102: todo `path` de `NAV_ITEMS` resolve para uma rota
    declarada em `App.tsx`.

    O `/settings` sobreviveu 92 specs apontando para lugar nenhum — clicar em
    "Configurações" caía no `NotFoundPage`. As duas coisas que deveriam ter pego
    olhavam para o lado errado: `Sidebar.test.tsx` percorre `NAV_ITEMS` só para conferir
    que o link RENDERIZA (um link para uma rota inexistente renderiza igualzinho), e a
    jornada e2e "navegar por todos os módulos" iterava uma cópia manual da lista, que
    omitia justamente Financeiro, Configurações e Conta e assinatura.

    Aqui o cruzamento é entre as duas fontes reais: o menu e o roteador.
    """
    nav = (FRONT / "components" / "shell" / "navItems.ts").read_text(encoding="utf-8")
    app_tsx = (FRONT / "App.tsx").read_text(encoding="utf-8")

    caminhos_do_menu = re.findall(r'path:\s*"([^"]+)"', nav)
    assert caminhos_do_menu, "navItems.ts sem nenhum path — regex de leitura quebrou"

    rotas = set(re.findall(r'<Route\s+path="([^"]+)"', app_tsx))
    # `<Route path="/x" element={...}>` pode estar quebrado em várias linhas pelo
    # prettier; a segunda forma pega esses.
    rotas |= set(re.findall(r'path="([^"]+)"', app_tsx))
    assert rotas, "App.tsx sem nenhuma rota — regex de leitura quebrou"

    faltando = [caminho for caminho in caminhos_do_menu if caminho not in rotas]

    assert not faltando, (
        "item do menu aponta para rota que não existe em App.tsx (cai no NotFoundPage): "
        f"{faltando}"
    )


def test_nenhum_date_today_em_app() -> None:
    """Spec 114, regras 1 e 2: «hoje» é sempre o do escritório, nunca o do processo.

    Por AST e não por regex: `# date.today()` num comentário, `"date.today()"` numa
    docstring e `hoje.today()` num objeto qualquer casariam num `grep` e não são o
    defeito. O que se procura é a chamada de atributo `today` sobre o nome `date` —
    exatamente o que o `DTZ011` do Ruff pega, replicado aqui para que a proibição
    sobreviva a alguém desligar a regra do `select`.

    A regra do Ruff e este teste se cobrem mutuamente: quem apagar `DTZ` do
    `pyproject.toml` continua reprovando aqui; quem apagar este teste continua
    reprovando no `make lint`.
    """
    ofensores: list[str] = []
    for arquivo in sorted((BACKEND / "app").rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(), filename=str(arquivo))
        for node in ast.walk(arvore):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "today"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "date"
            ):
                relativo = arquivo.relative_to(BACKEND)
                ofensores.append(f"{relativo}:{node.lineno}")

    assert ofensores == [], (
        "`date.today()` lê o relógio do processo, não o do escritório (spec 114). "
        "Receba o dia por `Depends(get_clock)` na rota, por parâmetro no service, ou "
        "resolva com `Clock(await AccountRepository(session).timezone())` em worker.\n"
        + "\n".join(ofensores)
    )


# Spec 106 §7, regra 5. Não é zero: há função cuja complexidade é o FLUXO dela — um laço
# de retry, um driver de grafo —, e quebrá-la em pedaços que só existem para baixar o
# número piora o código em vez de melhorar. Três é pouco o bastante para que cada uma
# precise ser defendida, e o teto é o que impede o `# noqa` de virar a saída padrão.
TETO_DE_NOQA_C901 = 3


def _noqa_da_regra(raiz: Path, regra: str) -> list[tuple[Path, int, list[str]]]:
    """Onde `regra` está silenciada, com as linhas de contexto de cada ocorrência.

    Este arquivo fica de fora da varredura porque ele PRECISA escrever o marcador para
    falar dele: o exemplo no comentário do regex e as duas mensagens de falha abaixo
    casariam com o próprio padrão, e o teste acusaria três silenciamentos que não existem.
    É a exceção clássica do linter que se lê — e o preço é uma cegueira estreita: um
    `# noqa: C901` de verdade AQUI não seria contado. Aceitável porque este arquivo é
    varredura de AST e regex, sem laço complexo, e porque a alternativa (adivinhar se o
    marcador está em código ou em texto) erraria nos dois sentidos.
    """
    achados: list[tuple[Path, int, list[str]]] = []
    for caminho in arquivos(raiz, ".py"):
        if caminho == Path(__file__).resolve():
            continue
        linhas = caminho.read_text().splitlines()
        for i, linha in enumerate(linhas):
            # `# noqa: <regra>` e `# noqa: B008, <regra>` — mas não um sufixo maior.
            if not re.search(rf"#\s*noqa:[^#]*\b{regra}\b", linha):
                continue
            # Só conta marcador REAL, que o Ruff exige na mesma linha do código que ele
            # silencia — logo sempre há código antes do `#`. Sem esta condição, a própria
            # justificativa (que precisa escrever `# noqa: XXX` para falar dele) seria
            # contada, e cada silenciamento valeria dois.
            if linha.split("#", 1)[0].strip():
                achados.append((caminho, i, linhas))
    return achados


def test_noqa_c901_dentro_do_teto() -> None:
    """§7 regra 5: silenciar a complexidade é exceção contada, não válvula de escape.

    O gate real é o `max-complexity = 6` do `pyproject.toml`; o `# noqa` é o furo dele. Um
    teto numérico é o que separa «esta função é irredutível» de «não quis mexer»: sem ele,
    a primeira função difícil vira precedente e o gate morre por mil silenciamentos.
    """
    achados = _todos_os_noqa("C901")
    locais = [f"{c.relative_to(RAIZ)}:{i + 1}" for c, i, _ in achados]
    assert len(achados) <= TETO_DE_NOQA_C901, (
        f"{len(achados)} `# noqa: C901` no projeto, teto é {TETO_DE_NOQA_C901}. "
        "Simplifique a função ou abra spec para discutir o teto:\n  " + "\n  ".join(locais)
    )


def test_todo_noqa_c901_tem_justificativa() -> None:
    """E cada um dos três precisa dizer POR QUE aquela função é irredutível.

    Mesmo critério do `# type: ignore`: não dá para verificar automaticamente se a
    explicação é boa, dá para exigir que exista. «Este laço de retry tem quatro saídas e
    quebrá-lo esconderia a ordem delas» é uma defesa; o silêncio não é.
    """
    ofensores = [
        f"{caminho.relative_to(RAIZ)}:{i + 1}"
        for caminho, i, linhas in _todos_os_noqa("C901")
        if not tem_justificativa(linhas, i)
    ]
    assert ofensores == [], "`# noqa: C901` sem justificativa:\n  " + "\n  ".join(ofensores)


def _todos_os_noqa(regra: str) -> list[tuple[Path, int, list[str]]]:
    """A varredura completa: `app/` e `tests/`."""
    return _noqa_da_regra(APP, regra) + _noqa_da_regra(BACKEND / "tests", regra)


# Spec 116 §7, regra 5. Dois, não zero: o `PLR0913` conta argumentos, e há duas formas
# legítimas de ter muitos que a regra não sabe distinguir — o construtor que só injeta
# dependências, e o construtor de dado de teste com um opcional por variação de caso. Duas
# é pouco o bastante para que cada uma precise ser defendida por escrito.
TETO_DE_NOQA_PLR0913 = 2


def test_noqa_plr0913_dentro_do_teto() -> None:
    """§7 regra 5 da 116: o furo do gate de argumentos é contado."""
    achados = _todos_os_noqa("PLR0913")
    locais = [f"{c.relative_to(RAIZ)}:{i + 1}" for c, i, _ in achados]
    assert len(achados) <= TETO_DE_NOQA_PLR0913, (
        f"{len(achados)} `# noqa: PLR0913` no projeto, teto é {TETO_DE_NOQA_PLR0913}. "
        "Agrupe os argumentos num objeto tipado ou abra spec para discutir o teto:\n  "
        + "\n  ".join(locais)
    )


def test_todo_noqa_plr0913_tem_justificativa() -> None:
    """E cada um dos dois diz por que agrupar pioraria o código.

    «São muitos mesmo» não é justificativa; «são dependências injetadas, e agrupá-las
    obrigaria 15 testes a construir um objeto para trocar uma função» é.
    """
    ofensores = [
        f"{caminho.relative_to(RAIZ)}:{i + 1}"
        for caminho, i, linhas in _todos_os_noqa("PLR0913")
        if not tem_justificativa(linhas, i)
    ]
    assert ofensores == [], "`# noqa: PLR0913` sem justificativa:\n  " + "\n  ".join(ofensores)


# Spec 115 §7, regra 4. `assert` some sob `python -O`: a validação deixa de existir sem
# aviso e o código segue com o valor que ela recusaria. Em teste isso é irrelevante (a
# suíte É feita de assert, e nunca roda otimizada); em produção é uma garantia imaginária.
def test_nenhum_assert_em_producao() -> None:
    """Zero `assert` em `app/`, por AST.

    Por AST e não por regex porque «assert» aparece em docstring, em comentário e em
    string de mensagem — e nada disso é o defeito. O que se procura é o statement.

    A regra do Ruff (`S101`) e este teste se cobrem mutuamente: quem apagar `S` do
    `select` continua reprovando aqui; quem apagar este teste continua reprovando no
    `make lint`. Mesmo par da 114 com o `DTZ011`.

    Substituto: `app/core/invariants.py::not_none` para invariante de programador,
    `ConfigurationError` para configuração ausente, e erro de domínio para o resto.
    """
    ofensores: list[str] = []
    for arquivo in sorted(APP.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(), filename=str(arquivo))
        ofensores += [
            f"{arquivo.relative_to(RAIZ)}:{node.lineno}"
            for node in ast.walk(arvore)
            if isinstance(node, ast.Assert)
        ]
    assert ofensores == [], (
        "`assert` em código de produção some sob `python -O` — a garantia deixa de "
        "existir em silêncio (spec 115). Use `not_none` para invariante, "
        "`ConfigurationError` para configuração, ou um erro de domínio:\n  "
        + "\n  ".join(ofensores)
    )


# O silenciamento da família `S` é contado como os outros. Os seis de hoje: `S603` no
# `rito backup` (2), `S608` no `SELECT count(*)` de view validada por allowlist (1),
# `S105` em duas constantes cujo NOME confunde a regra (2), e `S311` no jitter de backoff,
# que não é uso criptográfico (1).
TETO_DE_NOQA_S = 6


def test_noqa_de_seguranca_dentro_do_teto() -> None:
    """§7 da 115: silenciar regra de segurança é exceção contada, nunca reflexo."""
    achados = [
        (caminho, i, linhas)
        for regra in ("S101", "S105", "S106", "S107", "S112", "S311", "S603", "S607", "S608")
        for caminho, i, linhas in _todos_os_noqa(regra)
    ]
    locais = sorted(f"{c.relative_to(RAIZ)}:{i + 1}" for c, i, _ in achados)
    assert len(achados) <= TETO_DE_NOQA_S, (
        f"{len(achados)} `# noqa: S*` no projeto, teto é {TETO_DE_NOQA_S}. Corrija na "
        "origem ou abra spec para discutir o teto:\n  " + "\n  ".join(locais)
    )


def test_todo_noqa_de_seguranca_tem_justificativa() -> None:
    """E cada um explica por que o achado é falso positivo — ou por que o risco não existe.

    «É seguro» não é justificativa; «o nome vem de `_KNOWN_VIEWS`, validado na entrada da
    função» é. Um silenciamento de regra de segurança sem defesa escrita é indistinguível
    de um bug aceito por engano.
    """
    ofensores = [
        f"{caminho.relative_to(RAIZ)}:{i + 1}"
        for regra in ("S101", "S105", "S106", "S107", "S112", "S311", "S603", "S607", "S608")
        for caminho, i, linhas in _todos_os_noqa(regra)
        if not tem_justificativa(linhas, i)
    ]
    assert ofensores == [], "`# noqa: S*` sem justificativa:\n  " + "\n  ".join(ofensores)
