"""Gera o PDF da auditoria de segurança a partir de `achados.py`.

    docs/security-audit/.venv/bin/python docs/security-audit/gerar_relatorio.py

Só reportlab — os dois gráficos são desenhados com `reportlab.graphics`, sem matplotlib.
Um gerador que depende de menos coisas é um gerador que ainda roda daqui a um ano.

A4, margens de 2 cm, cabeçalho e rodapé com nome do relatório e número de página.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.doughnut import Doughnut
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from achados import (  # noqa: E402
    ACHADOS,
    CATEGORIAS,
    COMMIT,
    CORES,
    DATA,
    ESCOPO,
    FORTES,
    METODOLOGIA,
    PROJETO,
    RECOMENDACOES,
)

SAIDA = Path(__file__).resolve().parent / "relatorio-auditoria-seguranca.pdf"
TITULO = f"Relatório de Auditoria de Segurança — {PROJETO}"

MARGEM = 2 * cm
LARGURA_UTIL = A4[0] - 2 * MARGEM

TINTA = colors.HexColor("#0F172A")
TINTA_SUAVE = colors.HexColor("#475569")
LINHA = colors.HexColor("#CBD5E1")
FUNDO_SUAVE = colors.HexColor("#F1F5F9")

ORDEM_SEVERIDADE = ["crítica", "alta", "média", "baixa", "informativa"]


# --------------------------------------------------------------------- estilos


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "capa_titulo": ParagraphStyle(
            "capa_titulo",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=31,
            textColor=TINTA,
            alignment=0,
            spaceAfter=6,
        ),
        "capa_sub": ParagraphStyle(
            "capa_sub",
            parent=base["Normal"],
            fontSize=12.5,
            leading=18,
            textColor=TINTA_SUAVE,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=TINTA,
            spaceBefore=2,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=TINTA,
            spaceBefore=12,
            spaceAfter=5,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=TINTA,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "corpo": ParagraphStyle(
            "corpo",
            parent=base["Normal"],
            fontSize=9.6,
            leading=14.2,
            textColor=TINTA,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "celula": ParagraphStyle(
            "celula", parent=base["Normal"], fontSize=8.4, leading=11.6, textColor=TINTA
        ),
        "celula_mono": ParagraphStyle(
            "celula_mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.0,
            leading=9.8,
            textColor=colors.HexColor("#1E3A5F"),
        ),
        "cabecalho_tabela": ParagraphStyle(
            "cabecalho_tabela",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=11,
            textColor=colors.white,
        ),
        "legenda": ParagraphStyle(
            "legenda", parent=base["Normal"], fontSize=8.2, leading=11.5, textColor=TINTA_SUAVE
        ),
    }


E = _estilos()

# As únicas tags que o texto dos achados pode usar. Tudo o mais vira literal — sem isto,
# um achado que cita `<script>` (e este relatório cita) quebra o parser do reportlab.
_TAGS_PERMITIDAS = ("b", "/b", "i", "/i", "br/")


def _rich(texto: str) -> str:
    """Escapa o texto e devolve só as tags da allowlist."""
    seguro = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for tag in _TAGS_PERMITIDAS:
        seguro = seguro.replace(f"&lt;{tag}&gt;", f"<{tag}>")
    return seguro


# ------------------------------------------------------------------- moldura


def _moldura(canvas, doc) -> None:  # noqa: ANN001
    """Cabeçalho e rodapé de toda página que não é a capa."""
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont("Helvetica", 7.6)
        canvas.setFillColor(TINTA_SUAVE)
        canvas.drawString(MARGEM, A4[1] - MARGEM + 0.55 * cm, TITULO)
        canvas.setStrokeColor(LINHA)
        canvas.setLineWidth(0.5)
        canvas.line(
            MARGEM, A4[1] - MARGEM + 0.32 * cm, A4[0] - MARGEM, A4[1] - MARGEM + 0.32 * cm
        )
        canvas.line(MARGEM, MARGEM - 0.5 * cm, A4[0] - MARGEM, MARGEM - 0.5 * cm)
        canvas.drawString(MARGEM, MARGEM - 0.95 * cm, f"{DATA} · commit {COMMIT}")
        canvas.drawRightString(A4[0] - MARGEM, MARGEM - 0.95 * cm, f"Página {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------- chips


def _chip(severidade: str, largura: float = 2.05 * cm) -> Drawing:
    """Etiqueta colorida da severidade — a coluna que se lê de relance."""
    altura = 0.46 * cm
    d = Drawing(largura, altura)
    d.add(
        Rect(
            0,
            0,
            largura,
            altura,
            fillColor=colors.HexColor(CORES[severidade]),
            strokeColor=None,
            rx=3,
            ry=3,
        )
    )
    d.add(
        String(
            largura / 2,
            altura / 2 - 3.1,
            severidade.upper(),
            fontName="Helvetica-Bold",
            fontSize=7.1,
            fillColor=colors.white,
            textAnchor="middle",
        )
    )
    return d


# ------------------------------------------------------------------- gráficos


def _contagem_severidade() -> dict[str, int]:
    contagem = {s: 0 for s in ORDEM_SEVERIDADE}
    for achado in ACHADOS:
        contagem[achado.severidade] += 1
    return contagem


def _rosca() -> Drawing:
    contagem = _contagem_severidade()
    presentes = [(s, n) for s, n in contagem.items() if n]

    d = Drawing(8.4 * cm, 6.2 * cm)
    rosca = Doughnut()
    rosca.x = 0.2 * cm
    rosca.y = 0.55 * cm
    rosca.width = 5.0 * cm
    rosca.height = 5.0 * cm
    rosca.data = [n for _s, n in presentes]
    rosca.innerRadiusFraction = 0.55
    for i, (severidade, _n) in enumerate(presentes):
        rosca.slices[i].fillColor = colors.HexColor(CORES[severidade])
        rosca.slices[i].strokeColor = colors.white
        rosca.slices[i].strokeWidth = 1.4
    d.add(rosca)

    total = sum(n for _s, n in presentes)
    centro_x = rosca.x + rosca.width / 2
    centro_y = rosca.y + rosca.height / 2
    d.add(
        String(
            centro_x,
            centro_y + 1,
            str(total),
            fontName="Helvetica-Bold",
            fontSize=19,
            fillColor=TINTA,
            textAnchor="middle",
        )
    )
    d.add(
        String(
            centro_x,
            centro_y - 11,
            "achados",
            fontName="Helvetica",
            fontSize=7.6,
            fillColor=TINTA_SUAVE,
            textAnchor="middle",
        )
    )

    # Legenda própria: a do reportlab não deixa alinhar rótulo e contagem lado a lado.
    topo = 5.15 * cm
    for i, (severidade, n) in enumerate(presentes):
        y = topo - i * 0.62 * cm
        d.add(
            Rect(
                5.5 * cm,
                y,
                0.32 * cm,
                0.32 * cm,
                fillColor=colors.HexColor(CORES[severidade]),
                strokeColor=None,
            )
        )
        d.add(
            String(
                6.0 * cm,
                y + 1.5,
                f"{severidade.capitalize()}: {n}",
                fontName="Helvetica",
                fontSize=8.2,
                fillColor=TINTA,
            )
        )
    return d


def _barras() -> Drawing:
    contagem = {chave: 0 for chave in CATEGORIAS}
    for achado in ACHADOS:
        contagem[achado.categoria] += 1

    chaves = list(CATEGORIAS)
    valores = [contagem[c] for c in chaves]

    d = Drawing(8.4 * cm, 6.2 * cm)
    grafico = VerticalBarChart()
    grafico.x = 0.9 * cm
    grafico.y = 2.25 * cm
    grafico.width = 7.1 * cm
    grafico.height = 3.6 * cm
    grafico.data = [valores]
    grafico.barSpacing = 2
    grafico.groupSpacing = 6
    grafico.valueAxis.valueMin = 0
    grafico.valueAxis.valueMax = max(valores) + 1
    grafico.valueAxis.valueStep = 1
    grafico.valueAxis.labels.fontName = "Helvetica"
    grafico.valueAxis.labels.fontSize = 7.5
    grafico.categoryAxis.categoryNames = ["C1", "C2", "C3", "C4", "C5", "Outros"]
    grafico.categoryAxis.labels.fontName = "Helvetica"
    grafico.categoryAxis.labels.fontSize = 7.5
    grafico.categoryAxis.labels.dy = -6
    grafico.barLabels.fontName = "Helvetica-Bold"
    grafico.barLabels.fontSize = 7.5
    grafico.barLabelFormat = "%d"
    grafico.barLabels.dy = 5

    # Cada barra recebe a cor da severidade mais grave que ela contém — a categoria
    # sem achado fica cinza, e é essa a informação que interessa nela.
    for i, chave in enumerate(chaves):
        piores = [a.severidade for a in ACHADOS if a.categoria == chave]
        pior = next((s for s in ORDEM_SEVERIDADE if s in piores), None)
        cor = colors.HexColor(CORES[pior]) if pior else colors.HexColor("#CBD5E1")
        grafico.bars[(0, i)].fillColor = cor
        grafico.bars[(0, i)].strokeColor = None
    d.add(grafico)

    rotulos = [
        "C1 Isolamento",
        "C2 Permissão",
        "C3 IDOR",
        "C4 Chaves",
        "C5 XSS",
        "Outros",
    ]
    for i, rotulo in enumerate(rotulos):
        coluna, linha = i % 2, i // 2
        d.add(
            String(
                0.4 * cm + coluna * 4.1 * cm,
                1.25 * cm - linha * 0.44 * cm,
                rotulo,
                fontName="Helvetica",
                fontSize=7.0,
                fillColor=TINTA_SUAVE,
            )
        )
    return d


# --------------------------------------------------------------------- blocos


def _tabela_achados(historia: list) -> None:
    """Uma tabela por categoria: Severidade | Arquivo:linha | Descrição."""
    cabecalho = [
        Paragraph("Severidade", E["cabecalho_tabela"]),
        Paragraph("Arquivo:linha", E["cabecalho_tabela"]),
        Paragraph("Descrição", E["cabecalho_tabela"]),
    ]
    larguras = [2.4 * cm, 5.7 * cm, LARGURA_UTIL - 8.1 * cm]

    for chave, nome in CATEGORIAS.items():
        do_grupo = [a for a in ACHADOS if a.categoria == chave]
        historia.append(Paragraph(nome, E["h2"]))
        if not do_grupo:
            historia.append(
                Paragraph(
                    "Nenhum achado nesta categoria — ver a seção de pontos fortes.",
                    E["legenda"],
                )
            )
            continue

        linhas = [cabecalho]
        for achado in do_grupo:
            arquivos = "<br/>".join(_rich(a) for a in achado.arquivos[:3])
            descricao = (
                f"<b>{achado.id} — {_rich(achado.titulo)}</b><br/>{_rich(achado.descricao)}"
                f"<br/><br/><i>Por que é explorável:</i> {_rich(achado.explorabilidade)}"
            )
            if achado.condicoes:
                descricao += f"<br/><i>Condições:</i> {_rich(achado.condicoes)}"
            linhas.append(
                [
                    _chip(achado.severidade),
                    Paragraph(arquivos, E["celula_mono"]),
                    Paragraph(descricao, E["celula"]),
                ]
            )

        tabela = Table(linhas, colWidths=larguras, repeatRows=1)
        tabela.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), TINTA),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.4, LINHA),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FUNDO_SUAVE]),
                ]
            )
        )
        historia.append(tabela)
        historia.append(Spacer(1, 4))


def _bloco_issue(achado, numero: int) -> list:
    """O texto completo da issue, entre delimitadores, pronto para copiar."""
    labels = f"security, severidade:{achado.severidade}"
    evidencia = "\n".join(f"- `{a}`" for a in achado.arquivos)
    aceite = "\n".join(f"- [ ] {item}" for item in achado.aceite)
    corpo = (
        f"--- ISSUE {numero} ---\n"
        f"# [Segurança] {achado.titulo}\n\n"
        f"**Labels:** {labels}\n\n"
        f"## Problema\n{achado.descricao}\n\n"
        f"## Por que é explorável\n{achado.explorabilidade}\n"
        + (f"\n_Condições:_ {achado.condicoes}\n" if achado.condicoes else "")
        + f"\n## Evidência\n{evidencia}\n\n"
        f"```\n{achado.trecho}\n```\n\n"
        f"## Impacto\n{achado.impacto}\n\n"
        f"## Sugestão de correção\n{achado.correcao}\n\n"
        f"## Critérios de aceite\n{aceite}\n"
        f"--- FIM ISSUE {numero} ---"
    )
    # Preformatted preserva a quebra de linha do Markdown — é o que faz o texto
    # continuar sendo Markdown depois de copiado do PDF.
    regua = Drawing(LARGURA_UTIL, 3)
    regua.add(
        Rect(
            0,
            0,
            LARGURA_UTIL,
            3,
            fillColor=colors.HexColor(CORES[achado.severidade]),
            strokeColor=None,
        )
    )
    return [
        regua,
        Spacer(1, 3),
        Preformatted(
            corpo,
            ParagraphStyle(
                f"issue{numero}",
                fontName="Courier",
                fontSize=7.1,
                leading=9.4,
                textColor=TINTA,
                backColor=colors.HexColor("#F8FAFC"),
                borderColor=LINHA,
                borderWidth=0.5,
                borderPadding=7,
                leftIndent=0,
            ),
            maxLineLength=104,
            splitChars=" ,;:.",
        ),
        Spacer(1, 10),
    ]


def _historia() -> list:
    h: list = []

    # ------------------------------------------------------------------- capa
    h.append(Spacer(1, 2.6 * cm))
    h.append(Paragraph(TITULO, E["capa_titulo"]))
    h.append(Spacer(1, 0.15 * cm))
    barra = Drawing(LARGURA_UTIL, 5)
    largura_faixa = LARGURA_UTIL / 5
    for i, severidade in enumerate(ORDEM_SEVERIDADE):
        barra.add(
            Rect(
                i * largura_faixa,
                0,
                largura_faixa,
                5,
                fillColor=colors.HexColor(CORES[severidade]),
                strokeColor=None,
            )
        )
    h.append(barra)
    h.append(Spacer(1, 0.9 * cm))
    h.append(
        Paragraph(
            f"Auditoria de código-fonte · {DATA} · commit <b>{COMMIT}</b><br/>"
            "Sistema de gestão jurídica multi-tenant (SaaS)",
            E["capa_sub"],
        )
    )
    h.append(Spacer(1, 1.1 * cm))

    contagem = _contagem_severidade()
    resumo = [
        [
            Paragraph("<b>Achados por severidade</b>", E["celula"]),
            Paragraph(
                " · ".join(
                    f"{s.capitalize()}: <b>{n}</b>" for s, n in contagem.items() if n or s == "crítica"
                ),
                E["celula"],
            ),
        ],
        [
            Paragraph("<b>Categorias com achado</b>", E["celula"]),
            Paragraph("Isolamento por dono, permissão no servidor, XSS", E["celula"]),
        ],
        [
            Paragraph("<b>Categorias limpas</b>", E["celula"]),
            Paragraph("IDOR e chaves expostas (nenhum achado acionável)", E["celula"]),
        ],
    ]
    tabela_resumo = Table(resumo, colWidths=[5.2 * cm, LARGURA_UTIL - 5.2 * cm])
    tabela_resumo.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (0, -1), FUNDO_SUAVE),
                ("GRID", (0, 0), (-1, -1), 0.4, LINHA),
            ]
        )
    )
    h.append(tabela_resumo)

    h.append(PageBreak())

    # ------------------------------------------------- escopo e metodologia
    h.append(Paragraph("Escopo e metodologia", E["h1"]))
    h.append(Paragraph("Escopo auditado", E["h2"]))
    h.append(Paragraph(_rich(ESCOPO), E["corpo"]))
    h.append(Paragraph("Nota metodológica", E["h2"]))
    # O texto vem com parágrafos separados por linha em branco; o Paragraph do
    # reportlab não os enxerga, então cada bloco vira um Paragraph próprio.
    for bloco in METODOLOGIA.split("\n\n"):
        h.append(Paragraph(_rich(bloco), E["corpo"]))
    h.append(PageBreak())

    # -------------------------------------------------------- resumo executivo
    h.append(Paragraph("Resumo executivo", E["h1"]))
    h.append(
        Paragraph(
            "O Rito é um sistema deliberadamente endurecido: RLS forçado em todas as tabelas "
            "de domínio com auditoria automatizada das políticas, um teste que reprova "
            "qualquer rota nascida sem declaração de permissão, fronteira entre escritórios "
            "parceiros implementada dentro do banco e validação de configuração que recusa "
            "subir com o segredo de exemplo. Nenhum segredo real foi encontrado no código, "
            "nos arquivos de deploy ou no histórico do Git, e a varredura de todos os "
            "handlers de rota não confirmou nenhum IDOR.",
            E["corpo"],
        )
    )
    h.append(
        Paragraph(
            "Os achados se concentram onde o projeto abriu um caminho paralelo às suas "
            "próprias regras. A API pública por token reimplementa consultas em vez de "
            "reusar as da API interna, e nessa reimplementação perdeu duas garantias: a "
            "visibilidade de tarefa privada (A1) e a dimensão de acesso financeiro do RBAC "
            "(A2). O terceiro achado alto é de outra natureza: HTML vindo de um modelo de "
            "linguagem é injetado no DOM sem sanitização, num projeto que não tem nenhuma "
            "biblioteca de sanitização (A3). Os três são corrigíveis com mudanças pequenas e "
            "localizadas.",
            E["corpo"],
        )
    )

    graficos = Table(
        [
            [
                Paragraph("<b>Achados por severidade</b>", E["celula"]),
                Paragraph("<b>Achados por categoria</b>", E["celula"]),
            ],
            [_rosca(), _barras()],
        ],
        colWidths=[LARGURA_UTIL / 2, LARGURA_UTIL / 2],
    )
    graficos.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 0), (-1, 0), 0),
            ]
        )
    )
    h.append(graficos)
    h.append(
        Paragraph(
            "A cor de cada barra é a da severidade mais grave contida na categoria; cinza "
            "indica categoria sem nenhum achado. As duas entradas informativas registram "
            "verificações concluídas sem falha — não são pendências.",
            E["legenda"],
        )
    )

    h.append(Spacer(1, 0.55 * cm))
    h.append(Paragraph("Índice dos achados", E["h2"]))
    indice = [
        [
            Paragraph("<b>#</b>", E["cabecalho_tabela"]),
            Paragraph("<b>Severidade</b>", E["cabecalho_tabela"]),
            Paragraph("<b>Achado</b>", E["cabecalho_tabela"]),
            Paragraph("<b>Onde</b>", E["cabecalho_tabela"]),
        ]
    ]
    for achado in ACHADOS:
        indice.append(
            [
                Paragraph(f"<b>{achado.id}</b>", E["celula"]),
                _chip(achado.severidade, largura=1.9 * cm),
                Paragraph(_rich(achado.titulo), E["celula"]),
                Paragraph(_rich(achado.arquivos[0]), E["celula_mono"]),
            ]
        )
    tabela_indice = Table(
        indice,
        colWidths=[1.0 * cm, 2.2 * cm, 7.2 * cm, LARGURA_UTIL - 10.4 * cm],
        repeatRows=1,
    )
    tabela_indice.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TINTA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.4, LINHA),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FUNDO_SUAVE]),
            ]
        )
    )
    h.append(tabela_indice)

    # ------------------------------------------------------------ pontos fortes
    h.append(Spacer(1, 0.7 * cm))
    h.append(Paragraph("Pontos fortes (verificados)", E["h1"]))
    h.append(
        Paragraph(
            "Cada item abaixo foi conferido no código durante esta auditoria e é o motivo "
            "pelo qual categorias inteiras do escopo saíram sem achado.",
            E["corpo"],
        )
    )
    linhas = [
        [
            Paragraph("<b>O que está protegido</b>", E["cabecalho_tabela"]),
            Paragraph("<b>Evidência</b>", E["cabecalho_tabela"]),
        ]
    ]
    for forte in FORTES:
        linhas.append(
            [Paragraph(_rich(forte.titulo), E["celula"]), Paragraph(_rich(forte.evidencia), E["celula"])]
        )
    tabela = Table(linhas, colWidths=[5.9 * cm, LARGURA_UTIL - 5.9 * cm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CORES["forte"])),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.4, LINHA),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#ECFDF5")]),
            ]
        )
    )
    h.append(tabela)

    h.append(Spacer(1, 0.5 * cm))
    h.append(Paragraph("Pontos fracos — os riscos centrais", E["h1"]))
    fracos = [
        (
            "A API pública é um segundo caminho para os mesmos dados, e ele não herda as "
            "regras do primeiro",
            "Os dois achados altos de controle de acesso (A1 e A2) nascem do mesmo lugar: "
            "`app/public/router.py` monta `select(...)` à mão em vez de chamar os services "
            "que já carregam as regras. A API interna tem um teste que impede rota sem "
            "permissão; a pública não tem equivalente que compare a permissão dela com a da "
            "rota interna correspondente.",
        ),
        (
            "Não existe sanitização de HTML em lugar nenhum do projeto",
            "O sistema gera HTML por LLM, guarda HTML em template, renderiza HTML na tela e "
            "monta HTML para PDF — e não há nenhuma biblioteca de sanitização declarada. "
            "Hoje isso se manifesta em A3 e A4; a ausência da camada é o risco, não os dois "
            "pontos onde ela falta.",
        ),
        (
            "O refresh token vive em `localStorage`, com validade de 30 dias",
            "É uma decisão defensável, mas ela transforma qualquer falha de XSS em sequestro "
            "de conta duradouro. Enquanto não houver sanitização, esta escolha amplifica o "
            "impacto de A3 e A4.",
        ),
        (
            "O endurecimento de produção depende de o operador preencher o que o exemplo "
            "deixou vazio",
            "`bootstrap.py` é rigoroso com o que está na lista — e `METRICS_TOKEN` não está "
            "(A5), nem há recusa de CORS com curinga (A6). São as bordas que faltam para o "
            "conjunto ficar coerente com o próprio padrão do projeto.",
        ),
    ]
    for titulo, texto in fracos:
        h.append(KeepTogether([Paragraph(_rich(titulo), E["h3"]), Paragraph(_rich(texto), E["corpo"])]))
    h.append(PageBreak())

    # ------------------------------------------------------ achados detalhados
    h.append(Paragraph("Achados detalhados por categoria", E["h1"]))
    _tabela_achados(h)

    # ------------------------------------------------------------ recomendações
    h.append(Spacer(1, 0.6 * cm))
    h.append(Paragraph("Recomendações priorizadas", E["h1"]))
    linhas = [
        [
            Paragraph("<b>Prio.</b>", E["cabecalho_tabela"]),
            Paragraph("<b>Ação</b>", E["cabecalho_tabela"]),
            Paragraph("<b>Como</b>", E["cabecalho_tabela"]),
        ]
    ]
    for prioridade, acao, como in RECOMENDACOES:
        linhas.append(
            [
                Paragraph(f"<b>{prioridade}</b>", E["celula"]),
                Paragraph(_rich(acao), E["celula"]),
                Paragraph(_rich(como), E["celula"]),
            ]
        )
    tabela = Table(linhas, colWidths=[1.3 * cm, 5.2 * cm, LARGURA_UTIL - 6.5 * cm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TINTA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.4, LINHA),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FUNDO_SUAVE]),
            ]
        )
    )
    h.append(tabela)
    h.append(PageBreak())

    # --------------------------------------------------------- issues do GitHub
    h.append(Paragraph("Issues para o GitHub", E["h1"]))
    acionaveis = [a for a in ACHADOS if a.issue]
    h.append(
        Paragraph(
            f"{len(acionaveis)} issues, uma por achado acionável, em Markdown pronto para "
            "copiar. Cada uma vive entre <b>--- ISSUE n ---</b> e <b>--- FIM ISSUE n ---</b>. "
            "A1 e A2 têm a mesma causa de fundo, mas ficam separadas de propósito: o "
            "conserto de uma não conserta a outra, e cada uma tem seus próprios critérios de "
            "aceite. A6, A7 e A8 poderiam ser agrupadas num único chamado de endurecimento "
            "se a equipe preferir tratá-las numa tacada — ver a recomendação P3.",
            E["corpo"],
        )
    )
    for numero, achado in enumerate(acionaveis, start=1):
        h.extend(_bloco_issue(achado, numero))
    return h


def main() -> int:
    doc = BaseDocTemplate(
        str(SAIDA),
        pagesize=A4,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=MARGEM,
        bottomMargin=MARGEM,
        title=TITULO,
        author="Auditoria de segurança",
        subject="Auditoria de segurança de código-fonte",
    )
    frame = Frame(MARGEM, MARGEM, LARGURA_UTIL, A4[1] - 2 * MARGEM, id="corpo")
    doc.addPageTemplates([PageTemplate(id="padrao", frames=[frame], onPage=_moldura)])
    doc.build(_historia())
    print(f"PDF gerado: {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
