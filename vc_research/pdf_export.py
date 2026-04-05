"""PDF export for final memo with citations."""

from __future__ import annotations

import re
import tempfile
import textwrap
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from vc_research.models.schemas import MemoSection, SynthesisOutput

_MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)", re.I)
_URL_BRACKET = re.compile(r"\[(https?://[^\]\s]+)\]", re.I)


def _pdf_ascii(text: str) -> str:
    """
    FPDF core fonts are Latin-1. Unicode dashes/quotes become '?' with naive encode;
    map common characters to ASCII first.
    """
    if not text:
        return ""
    t = (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2012", "-")
        .replace("\u2011", "-")
        .replace("\u00a0", " ")
        .replace("\u2026", "...")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u00b7", " ")
    )
    return t.encode("latin-1", "replace").decode("latin-1")


def _normalize_line_spaces(text: str) -> str:
    """Single spaces inside lines; keep paragraph breaks."""
    return "\n".join(re.sub(r" +", " ", ln.strip()) for ln in text.split("\n"))


def _extract_inline_urls(text: str) -> Tuple[str, List[str]]:
    """Turn [url] and [label](url) into [1], [2]; collect URLs in order."""
    urls: List[str] = []

    def md_sub(m: re.Match) -> str:
        urls.append(m.group(2))
        return f"[{len(urls)}]"

    t = _MD_LINK.sub(md_sub, text)

    def br_sub(m: re.Match) -> str:
        urls.append(m.group(1))
        return f"[{len(urls)}]"

    t = _URL_BRACKET.sub(br_sub, t)
    return _normalize_line_spaces(t), urls


def _prose_and_refs(body: str, model_footnotes: List[str]) -> Tuple[str, List[str]]:
    """Prefer model footnote list; still strip any raw URLs from prose."""
    cleaned, auto = _extract_inline_urls(body)
    refs = model_footnotes if model_footnotes else auto
    return cleaned, refs


def format_memo_prose(
    body: str, model_footnotes: Optional[List[str]] = None
) -> Tuple[str, List[str]]:
    """Public helper for Streamlit: clean prose + ordered source URLs."""
    return _prose_and_refs(body, model_footnotes or [])


_FOOTNOTE_BRACKET = re.compile(r"\[(\d+)\]")


def streamlit_prose_display(prose: str) -> str:
    """
    Streamlit Markdown treats [1] like a link reference (odd color). Use superscript
    digits so footnote markers render as plain text.
    """
    sup = "⁰¹²³⁴⁵⁶⁷⁸⁹"

    def to_sup(m: re.Match) -> str:
        return "".join(sup[int(d)] for d in m.group(1))

    return _FOOTNOTE_BRACKET.sub(to_sup, prose)


def _soft_wrap(text: str, width: int = 92) -> str:
    parts: list[str] = []
    for word in text.split():
        if len(word) > width:
            parts.extend(textwrap.wrap(word, width=width, break_long_words=True))
        else:
            parts.append(word)
    return " ".join(parts)


def _multicell_block(pdf: FPDF, line_height: float, text: str) -> None:
    txt = _pdf_ascii(_soft_wrap(text.strip()))
    if not txt:
        return
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        pdf.epw,
        line_height,
        txt,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align=Align.L,
    )


def _cell_full(pdf: FPDF, h: float, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    t = _pdf_ascii(text)
    pdf.cell(
        pdf.epw,
        h,
        t,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align=Align.L,
    )


def _write_references(pdf: FPDF, heading: str, urls: List[str]) -> None:
    if not urls:
        return
    pdf.ln(0.5)
    pdf.set_font("helvetica", "B", 8)
    _cell_full(pdf, 4, heading)
    pdf.set_font("helvetica", "", 8)
    for i, u in enumerate(urls, start=1):
        _multicell_block(pdf, 3.8, f"[{i}] {u}")


def _section_block(
    pdf: FPDF,
    sec: MemoSection,
) -> None:
    pdf.set_font("helvetica", "B", 10)
    _cell_full(
        pdf,
        6,
        f"{sec.title} (confidence {sec.confidence:.0%})",
    )
    pdf.set_font("helvetica", "", 10)
    body, refs = _prose_and_refs(
        sec.body_markdown, getattr(sec, "footnotes", None) or []
    )
    for line in body.split("\n"):
        if line.strip():
            _multicell_block(pdf, 5, line)
    _write_references(pdf, "Sources", refs)
    pdf.ln(1)


def _build_fpdf(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> FPDF:
    pdf = FPDF()
    pdf.set_margins(left=12, top=10, right=12)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=14)

    pdf.set_font("helvetica", "B", 14)
    _cell_full(pdf, 8, f"Investment memo: {startup_name}")
    pdf.ln(1)

    if dimension_scores:
        pdf.set_font("helvetica", "B", 10)
        _cell_full(pdf, 6, "Dimension scores (0-10)")
        pdf.set_font("helvetica", "", 10)
        for k, v in dimension_scores.items():
            _cell_full(pdf, 5, f"{k.replace('_', ' ').title()}: {v}/10")
        pdf.ln(1)

    es_fn = getattr(synthesis, "executive_summary_footnotes", None) or []
    pdf.set_font("helvetica", "B", 11)
    _cell_full(pdf, 6, "Executive summary")
    pdf.set_font("helvetica", "", 10)
    es_body, es_refs = _prose_and_refs(synthesis.executive_summary or "", es_fn)
    for line in es_body.split("\n"):
        if line.strip():
            _multicell_block(pdf, 5.2, line)
    _write_references(pdf, "Sources", es_refs)
    pdf.ln(1)

    for sec in synthesis.sections:
        _section_block(pdf, sec)

    pdf.set_font("helvetica", "B", 11)
    _cell_full(pdf, 6, "Recommendation")
    pdf.set_font("helvetica", "", 10)
    rec = synthesis.recommendation or ""
    rec_clean, rec_refs = _prose_and_refs(
        f"{rec} (confidence {synthesis.recommendation_confidence:.0%})", []
    )
    for line in rec_clean.split("\n"):
        if line.strip():
            _multicell_block(pdf, 5, line)
    _write_references(pdf, "Sources", rec_refs)
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
