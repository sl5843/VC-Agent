"""PDF export for final memo with citations."""

from __future__ import annotations

import tempfile
from io import BytesIO
from typing import Dict, Optional

from fpdf import FPDF

from vc_research.models.schemas import SynthesisOutput


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def _build_fpdf(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> FPDF:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, _latin1_safe(f"Investment memo: {startup_name}"), ln=True)
    pdf.set_font("helvetica", "I", 9)
    pdf.cell(
        0,
        6,
        "VC Research Agent | Multi-agent pipeline (search, analysis, fact-check, synthesis)",
        ln=True,
    )
    pdf.ln(4)

    if dimension_scores:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 8, "Dimension scores (0-10)", ln=True)
        pdf.set_font("helvetica", "", 10)
        for k, v in dimension_scores.items():
            pdf.cell(0, 6, _latin1_safe(f"{k}: {v}/10"), ln=True)
        pdf.ln(3)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "Executive summary", ln=True)
    pdf.set_font("helvetica", "", 9)
    for line in (synthesis.executive_summary or "").split("\n"):
        if line.strip():
            pdf.multi_cell(0, 5, _latin1_safe(line))
    pdf.ln(2)

    for sec in synthesis.sections:
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(
            0,
            7,
            _latin1_safe(f"{sec.title} (confidence {sec.confidence:.0%})"),
            ln=True,
        )
        pdf.set_font("helvetica", "", 9)
        for line in sec.body_markdown.split("\n"):
            if line.strip():
                pdf.multi_cell(0, 5, _latin1_safe(line))
        if sec.key_citations:
            pdf.set_font("helvetica", "I", 8)
            pdf.cell(0, 5, "Key citations:", ln=True)
            for url in sec.key_citations[:20]:
                pdf.multi_cell(0, 4, _latin1_safe(url))
        pdf.ln(2)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "Recommendation", ln=True)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(
        0,
        5,
        _latin1_safe(
            f"{synthesis.recommendation} (confidence {synthesis.recommendation_confidence:.0%})"
        ),
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
