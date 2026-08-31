"""Render HTML → PDF (spec 067) — `xhtml2pdf`, pura Python, sem dependência de
sistema (diferente de weasyprint/wkhtmltopdf). Cabeçalho e rodapé saem uma vez
(topo/fim do documento, não por página — Fora de escopo §3); marca d'água é um
rótulo de destaque no topo, não uma sobreposição diagonal (mesma seção)."""

from io import BytesIO


class PdfRenderError(Exception):
    pass


def render_pdf(
    *, header_content: str, content: str, footer_content: str, watermark_text: str | None
) -> bytes:
    # Spec 104: `xhtml2pdf` custa 209 ms de import e só quem gera PDF paga — não todo
    # worker de teste que importa `app.main` para servir uma rota de listagem.
    from xhtml2pdf import pisa

    watermark_html = (
        f'<p style="color:#b91c1c;font-weight:bold;border:1px solid #b91c1c;'
        f'padding:4px;display:inline-block;">{watermark_text}</p>'
        if watermark_text
        else ""
    )
    header_html = f"<div>{header_content}</div><hr/>" if header_content.strip() else ""
    footer_html = f"<hr/><div>{footer_content}</div>" if footer_content.strip() else ""

    html = (
        "<html><head><meta charset='utf-8'></head>"
        f"<body>{watermark_html}{header_html}<div>{content}</div>{footer_html}</body></html>"
    )

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if result.err:
        raise PdfRenderError
    return buffer.getvalue()
