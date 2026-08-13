"""Modelos: geração de PDF (spec 067, §8) — `render_pdf` puro, sem banco."""

from app.domain.templates.pdf import render_pdf


def test_render_pdf_produz_arquivo_valido_com_cabecalho_corpo_rodape() -> None:
    pdf_bytes = render_pdf(
        header_content="<p>Escritório Modelo</p>",
        content="<p><strong>Corpo do documento</strong></p>",
        footer_content="<p>Página confidencial</p>",
        watermark_text="MINUTA",
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 0


def test_render_pdf_sem_marca_dagua_nem_cabecalho_ainda_gera() -> None:
    pdf_bytes = render_pdf(
        header_content="", content="<p>Só corpo</p>", footer_content="", watermark_text=None
    )
    assert pdf_bytes.startswith(b"%PDF")
