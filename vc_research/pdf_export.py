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

# Report theme (RGB)
_COLOR_HEADER_BG = (44, 62, 80)
_COLOR_HEADING = (45, 55, 72)
_COLOR_MUTED = (100, 100, 100)
_COLOR_RULE = (210, 214, 220)
_COLOR_SOURCE = (55, 65, 81)
_COLOR_TABLE_HEAD = (245, 247, 250)


def _pdf_ascii(text: str) -> str:
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
    return "\n".join(re.sub(r" +", " ", ln.strip()) for ln in text.split("\n"))


def _extract_inline_urls(text: str) -> Tuple[str, List[str]]:
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
    cleaned, auto = _extract_inline_urls(body)
    refs = model_footnotes if model_footnotes else auto
    return cleaned, refs


def format_memo_prose(
    body: str, model_footnotes: Optional[List[str]] = None
) -> Tuple[str, List[str]]:
    return _prose_and_refs(body, model_footnotes or [])


_FOOTNOTE_BRACKET = re.compile(r"\[(\d+)\]")


def streamlit_prose_display(prose: str) -> str:
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


class _MemoPDF(FPDF):
    """PDF with footer page numbers."""

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.set_x(self.l_margin)
        self.cell(
            self.epw,
            8,
            _pdf_ascii(f"Page {self.page_no()}"),
            align=Align.C,
        )
        self.set_text_color(0, 0, 0)


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


def _cell_full(pdf: FPDF, h: float, text: str, align: Align = Align.L) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.cell(
        pdf.epw,
        h,
        _pdf_ascii(text),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align=align,
    )


def _hrule(pdf: FPDF) -> None:
    pdf.set_draw_color(*_COLOR_RULE)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2)


def _cover_banner(pdf: FPDF, company: str) -> None:
    h = 26.0
    pdf.set_fill_color(*_COLOR_HEADER_BG)
    pdf.rect(0, 0, pdf.w, h, "F")
    pdf.set_xy(pdf.l_margin, 8)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 7, "Investment memo", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("helvetica", "", 11)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 6, _pdf_ascii(company))
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 10)
    pdf.set_y(h + 4)


def _section_title(pdf: FPDF, title: str, meta: str = "") -> None:
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(*_COLOR_HEADING)
    _cell_full(pdf, 6, title)
    if meta:
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(*_COLOR_MUTED)
        _cell_full(pdf, 4, meta)
        pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 10)
    _hrule(pdf)


def _scores_table(pdf: FPDF, dimension_scores: Dict[str, int]) -> None:
    _section_title(pdf, "Dimension scores", "Scale 0-10")
    col_a = pdf.epw * 0.62
    col_b = pdf.epw - col_a
    pdf.set_draw_color(*_COLOR_RULE)
    pdf.set_fill_color(*_COLOR_TABLE_HEAD)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(col_a, 7, " Dimension", border=1, fill=True)
    pdf.cell(col_b, 7, " Score", border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("helvetica", "", 9)
    rows = list(dimension_scores.items())
    for i, (k, v) in enumerate(rows):
        fill = i % 2 == 1
        if fill:
            pdf.set_fill_color(252, 252, 253)
        else:
            pdf.set_fill_color(255, 255, 255)
        label = k.replace("_", " ").title()
        pdf.cell(col_a, 6.5, f" {label}", border="LR", fill=fill)
        pdf.cell(col_b, 6.5, f" {v}", border="LR", fill=fill, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_fill_color(255, 255, 255)
    pdf.cell(pdf.epw, 0, "", border="T", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _write_references(pdf: FPDF, urls: List[str]) -> None:
    if not urls:
        return
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(*_COLOR_HEADING)
    pdf.set_x(pdf.l_margin)
    pdf.cell(pdf.epw, 5, "Sources")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(0.5)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(*_COLOR_SOURCE)
    indent = 5.0
    for i, u in enumerate(urls, start=1):
        pdf.set_x(pdf.l_margin + indent)
        line = f"[{i}] {_pdf_ascii(u)}"
        pdf.multi_cell(
            pdf.epw - indent,
            3.6,
            line,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
            align=Align.L,
        )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def _body_paragraphs(pdf: FPDF, body: str, line_h: float = 5.0) -> None:
    for line in body.split("\n"):
        if line.strip():
            _multicell_block(pdf, line_h, line)


def _section_block(pdf: FPDF, sec: MemoSection) -> None:
    meta = f"Section confidence {sec.confidence:.0%}"
    _section_title(pdf, sec.title, meta)
    body, refs = _prose_and_refs(
        sec.body_markdown, getattr(sec, "footnotes", None) or []
    )
    _body_paragraphs(pdf, body)
    _write_references(pdf, refs)
    pdf.ln(1)


def _build_fpdf(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> FPDF:
    pdf = _MemoPDF()
    pdf.set_margins(left=14, top=14, right=14)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    _cover_banner(pdf, startup_name)

    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(*_COLOR_MUTED)
    _cell_full(pdf, 5, "Generated by VC Research Agent | Citations as numbered sources")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    if dimension_scores:
        _scores_table(pdf, dimension_scores)

    es_fn = getattr(synthesis, "executive_summary_footnotes", None) or []
    _section_title(pdf, "Executive summary")
    es_body, es_refs = _prose_and_refs(synthesis.executive_summary or "", es_fn)
    _body_paragraphs(pdf, es_body, 5.0)
    _write_references(pdf, es_refs)
    pdf.ln(2)

    for sec in synthesis.sections:
        _section_block(pdf, sec)

    meta = f"Model confidence {synthesis.recommendation_confidence:.0%}"
    _section_title(pdf, "Recommendation", meta)
    rec = synthesis.recommendation or ""
    rec_clean, rec_refs = _prose_and_refs(rec, [])
    _body_paragraphs(pdf, rec_clean)
    _write_references(pdf, rec_refs)
    return pdf


def build_memo_pdf_bytes(
    startup_name: str,
    synthesis: SynthesisOutput,
    dimension_scores: Optional[Dict[str, int]] = None,
) -> bytes:
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
    pdf = _build_fpdf(startup_name, synthesis, dimension_scores)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name
    tmp.close()
    pdf.output(path)
    return path
