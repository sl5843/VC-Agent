"""PDF export for final memo with citations."""

from __future__ import annotations

import tempfile
import textwrap
from io import BytesIO
from typing import Dict, Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from vc_research.models.schemas import SynthesisOutput


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def _soft_wrap(text: str, width: int = 92) -> str:
    """Break very long tokens (URLs) so multi_cell always has room to wrap."""
    parts: list[str] = []
    for word in text.split():
        if len(word) > width:
            parts.extend(textwrap.wrap(word, width=width, break_long_words=True))
        else:
            parts.append(word)
    return " ".join(parts)


def _multicell_block(pdf: FPDF, line_height: float, text: str) -> None:
    """
    Write wrapped text using full page width. Resets x after each block so
    consecutive multi_cell calls do not see 0 remaining width (fpdf2 error:
    'Not enough horizontal space to render a single character').
    """
    txt = _latin1_safe(_soft_wrap(text.strip()))
    if not txt:
        return
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        pdf.epw,
        line_height,
        txt,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


def _cell_full(pdf: FPDF, h: float, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    t = _latin1_safe(text)
    pdf.cell(pdf.epw, h, t, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _build_fpdf(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> FPDF:
    pdf = FPDF()
    pdf.set_margins(left=12, top=12, right=12)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("helvetica", "B", 16)
    _cell_full(pdf, 10, f"Investment memo: {startup_name}")
    pdf.set_font("helvetica", "I", 9)
    _cell_full(
        pdf,
        6,
        "VC Research Agent | Multi-agent pipeline (search, analysis, fact-check, synthesis)",
    )
    pdf.ln(2)

    if dimension_scores:
        pdf.set_font("helvetica", "B", 12)
        _cell_full(pdf, 8, "Dimension scores (0-10)")
        pdf.set_font("helvetica", "", 10)
        for k, v in dimension_scores.items():
            _cell_full(pdf, 6, f"{k}: {v}/10")
        pdf.ln(2)

    pdf.set_font("helvetica", "B", 12)
    _cell_full(pdf, 8, "Executive summary")
    pdf.set_font("helvetica", "", 9)
    for line in (synthesis.executive_summary or "").split("\n"):
        if line.strip():
            _multicell_block(pdf, 5, line)
    pdf.ln(2)

    for sec in synthesis.sections:
        pdf.set_font("helvetica", "B", 11)
        _cell_full(
            pdf,
            7,
            f"{sec.title} (confidence {sec.confidence:.0%})",
        )
        pdf.set_font("helvetica", "", 9)
        for line in sec.body_markdown.split("\n"):
            if line.strip():
                _multicell_block(pdf, 5, line)
        if sec.key_citations:
            pdf.set_font("helvetica", "I", 8)
            _cell_full(pdf, 5, "Key citations:")
            for url in sec.key_citations[:20]:
                _multicell_block(pdf, 4, url)
        pdf.ln(2)

    pdf.set_font("helvetica", "B", 12)
    _cell_full(pdf, 8, "Recommendation")
    pdf.set_font("helvetica", "", 10)
    _multicell_block(
        pdf,
        5,
        f"{synthesis.recommendation} (confidence {synthesis.recommendation_confidence:.0%})",
    )
    return pdf


def build_memo_pdf_bytes(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> bytes:
    """Build PDF in memory (avoids temp-file quirks on Streamlit Cloud)."""
    pdf = _build_fpdf(startup_name, synthesis, dimension_scores)
    buf = BytesIO()
    pdf.output(buf)
    raw = buf.getvalue()
    return raw if isinstance(raw, bytes) else bytes(raw)


def export_memo_pdf(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> str:
    """Write PDF to a temp file and return path (legacy helper)."""
    pdf = _build_fpdf(startup_name, synthesis, dimension_scores)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name
    tmp.close()
    pdf.output(path)
    return path
