# -*- coding: utf-8 -*-
"""Streamlit entry: multi-agent VC research pipeline."""

from __future__ import annotations

import base64
import pickle
import zlib
from typing import Any, Callable, Dict, List, Optional

import streamlit as st

from vc_research.charts import (
    create_comparison_radar,
    create_dimension_radar,
    create_market_map,
)
from vc_research.models.schemas import PipelineState, VerifiedClaim
from vc_research.pdf_export import build_memo_pdf_bytes
from vc_research.pipeline import run_compare_bundle, run_pipeline

st.set_page_config(
    page_title="VC Research Agent",
    page_icon="💼",
    layout="wide",
)

try:
    from vc_research.config import get_gemini_key, get_serper_key

    _ = get_gemini_key()
    _ = get_serper_key()
except Exception as e:
    st.error(f"Configuration error: {e}")
    st.stop()

# Raw objects in session_state are often lost on rerun (especially on Streamlit Cloud
# after JSON round-trips). Persist pipeline + PDF as base64 so "Generate PDF" keeps results.
SS_SINGLE_PICKLE_B64 = "vc_single_pipeline_pickle_b64"
SS_SINGLE_STATE_LEGACY = "vc_single_pipeline_state"
SS_COMPARE = "vc_compare_payload"
PDF_KEY_PREFIX = "vc_pdf_b64_"


def _company_slug(name: str) -> str:
    s = "".join(c if c.isalnum() else "_" for c in (name or "").strip())
    return (s[:64] or "company").lower()


def _clear_pdf_keys() -> None:
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and (
            k.startswith(PDF_KEY_PREFIX) or k.startswith("vc_pdf_bytes_")
        ):
            del st.session_state[k]


def _persist_pipeline_state(state: PipelineState) -> None:
    blob = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
    comp = zlib.compress(blob, level=7)
    st.session_state[SS_SINGLE_PICKLE_B64] = base64.b64encode(comp).decode("ascii")


def _load_pipeline_state() -> Optional[PipelineState]:
    raw = st.session_state.get(SS_SINGLE_PICKLE_B64)
    if raw:
        try:
            decoded = base64.b64decode(raw.encode("ascii"))
            try:
                data = zlib.decompress(decoded)
            except zlib.error:
                data = decoded
            return pickle.loads(data)
        except Exception:
            st.session_state.pop(SS_SINGLE_PICKLE_B64, None)
    legacy = st.session_state.pop(SS_SINGLE_STATE_LEGACY, None)
    if legacy is not None:
        try:
            _persist_pipeline_state(legacy)
        except Exception:
            pass
        return legacy
    return None


def _clear_single_pipeline() -> None:
    st.session_state.pop(SS_SINGLE_PICKLE_B64, None)
    st.session_state.pop(SS_SINGLE_STATE_LEGACY, None)
    _clear_pdf_keys()


FULL_PIPELINE_STEPS: Dict[str, str] = {
    "search:start": "🔍 Search agent: querying Serper…",
    "search:ok": "✅ Search agent: structured sources ready.",
    "search:failed": "❌ Search agent failed.",
    "analysis:start": "🧠 Analysis agent: Gemini extracting cited insights…",
    "analysis:ok": "✅ Analysis agent: dimensions + competitors drafted.",
    "analysis:failed": "❌ Analysis agent failed.",
    "factcheck:start": "🛡️ Fact-check agent: cross-referencing claims…",
    "factcheck:ok": "✅ Fact-check agent: verification complete.",
    "factcheck:failed": "❌ Fact-check agent failed.",
    "synthesis:start": "📑 Synthesis agent: building investment memo…",
    "synthesis:ok": "✅ Synthesis agent: memo ready.",
    "synthesis:failed": "❌ Synthesis agent failed.",
}

QUICK_STEPS: Dict[str, str] = {
    "search:start": "🔍 Search agent (Serper) running…",
    "search:ok": "✅ Search agent done.",
    "analysis:start": "🧠 Analysis agent running…",
    "analysis:ok": "✅ Analysis agent done.",
}


def _status_log(status, message: str) -> None:
    status.write(message)


def _run_pipeline_with_status(
    company_name: str,
    description: str,
    log: Callable[[str], None],
) -> PipelineState:
    def on_step(ev: str) -> None:
        log(FULL_PIPELINE_STEPS.get(ev, ev))

    state = run_pipeline(company_name, description, on_step=on_step)
    for err in state.errors:
        log(f"**Error:** {err}")
    return state


def _render_claims_with_links(claims: List[VerifiedClaim]) -> None:
    for vc in claims:
        badge = "🟢 verified" if vc.status == "verified" else "🟡 uncertain"
        line = (
            f"**{vc.dimension}** — {vc.text} — _{badge}_ — "
            f"confidence `{vc.confidence:.0%}`"
        )
        if vc.source_urls:
            line += " — " + " · ".join(
                f"[source {i+1}]({url})" for i, url in enumerate(vc.source_urls)
            )
        st.markdown(line)
        if vc.rationale:
            st.caption(vc.rationale)


def _render_single_company_results(state: PipelineState) -> None:
    """Tabs for one pipeline run (expects state kept in session between reruns)."""
    if state.errors and not state.synthesis:
        st.error(
            "Pipeline stopped after errors. Partial outputs (if any) are shown below."
        )

    slug = _company_slug(state.company_name)
    def _store_pdf_bytes(data: bytes) -> None:
        st.session_state[f"{PDF_KEY_PREFIX}{slug}"] = base64.b64encode(data).decode(
            "ascii"
        )

    def _read_pdf_bytes() -> Optional[bytes]:
        b64 = st.session_state.get(f"{PDF_KEY_PREFIX}{slug}")
        if not b64:
            return None
        try:
            return base64.b64decode(b64.encode("ascii"))
        except Exception:
            return None

    # PDF must live *above* tabs: every widget click reruns the app and Streamlit
    # resets the active tab to the first one — a download button only in a later
    # tab looked like "Generate PDF does nothing" because users stayed on tab 1.
    if state.synthesis and state.analysis:
        st.markdown("---")
        st.subheader("Export PDF")
        st.caption(
            "Use this section first — it stays visible. "
            "(Buttons inside later tabs are easy to miss after Streamlit jumps back to tab 1.)"
        )
        gen_clicked = st.button(
            "Generate PDF",
            type="secondary",
            use_container_width=True,
            key=f"btn_gen_pdf_{slug}",
        )
        if gen_clicked:
            with st.spinner("Building PDF…"):
                try:
                    _store_pdf_bytes(
                        build_memo_pdf_bytes(
                            state.company_name,
                            state.synthesis,
                            state.analysis.dimension_scores,
                        )
                    )
                    st.success("PDF ready — download below.")
                except Exception as e:
                    st.error(f"Could not build PDF: {e}")

        pdf_blob = _read_pdf_bytes()
        if pdf_blob:
            safe_fn = (
                "".join(
                    c if c.isalnum() or c in "-_" else "_"
                    for c in state.company_name.strip()
                ).strip("_")
                or "memo"
            ) + "_memo.pdf"
            st.download_button(
                label="Download investment memo PDF",
                data=pdf_blob,
                file_name=safe_fn,
                mime="application/pdf",
                use_container_width=True,
                key=f"btn_dl_pdf_{slug}",
            )

    tab_a, tab_b, tab_c, tab_d = st.tabs(
        [
            "Scores & market map",
            "Sources",
            "Claims & citations",
            "Investment memo",
        ]
    )

    with tab_a:
        if state.analysis and state.analysis.dimension_scores:
            st.subheader("Dimension radar")
            fig = create_dimension_radar(
                state.analysis.dimension_scores, state.company_name
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No analysis scores available.")

        st.subheader("Market map (target vs competitors)")
        comps = state.analysis.competitors if state.analysis else []
        fig2 = create_market_map(state.company_name, comps)
        st.plotly_chart(fig2, use_container_width=True)

    with tab_b:
        if state.search:
            st.subheader(f"{len(state.search.sources)} sources")
            for s in state.search.sources:
                st.markdown(f"**[{s.source_id}]** [{s.title}]({s.url})")
                st.caption(s.snippet[:400] + ("…" if len(s.snippet) > 400 else ""))
        else:
            st.info("No search results.")

    with tab_c:
        if state.factcheck and state.factcheck.verified_claims:
            st.subheader("Fact-checked claims (click source links)")
            _render_claims_with_links(state.factcheck.verified_claims)
        elif state.analysis:
            st.warning(
                "Fact-check did not complete; showing analysis claims without verification."
            )
            for dim, block in state.analysis.dimensions.items():
                for c in block.claims:
                    urls_md = ""
                    if c.source_urls:
                        urls_md = " · ".join(f"[src]({u})" for u in c.source_urls)
                    elif state.search:
                        id_to_url = {x.source_id: x.url for x in state.search.sources}
                        urls = [id_to_url[i] for i in c.source_ids if i in id_to_url]
                        urls_md = " · ".join(f"[src]({u})" for u in urls)
                    st.markdown(f"**{dim}:** {c.text} {urls_md}")
        else:
            st.info("No claims to display.")

    with tab_d:
        if state.synthesis:
            syn = state.synthesis
            st.metric(
                "Recommendation confidence",
                f"{syn.recommendation_confidence:.0%}",
            )
            st.markdown(f"### Recommendation\n{syn.recommendation}")
            st.markdown("### Executive summary")
            st.markdown(syn.executive_summary or "_N/A_")
            for sec in syn.sections:
                st.markdown(
                    f"### {sec.title} _(section confidence {sec.confidence:.0%})_"
                )
                st.markdown(sec.body_markdown)
                if sec.key_citations:
                    st.markdown(
                        "**Citations:** "
                        + " · ".join(f"[link]({u})" for u in sec.key_citations)
                    )
        else:
            st.info("Synthesis not available (pipeline may have failed earlier).")


def _render_compare_results(payload: Dict[str, Any]) -> None:
    errors: List[str] = payload.get("errors") or []
    states: List[PipelineState] = payload.get("states") or []
    full: bool = bool(payload.get("full"))

    if errors:
        st.error("Some companies failed:\n- " + "\n- ".join(errors))

    all_scores = {}
    for ps in states:
        if ps.analysis and ps.analysis.dimension_scores:
            all_scores[ps.company_name] = ps.analysis.dimension_scores

    if len(all_scores) >= 2:
        mode_lbl = "full 4-agent pipeline" if full else "quick (search + analysis only)"
        st.success(f"Comparison ready ({mode_lbl}).")
        fig = create_comparison_radar(all_scores)
        st.plotly_chart(fig, use_container_width=True)
    elif not errors:
        st.info("Not enough successful runs to chart.")

    if full:
        st.subheader("Per-company summaries (same depth as single-company mode)")
        for ps in states:
            if not ps.analysis:
                continue
            with st.expander(f"**{ps.company_name}** — detail", expanded=False):
                if ps.synthesis:
                    st.markdown(f"**Recommendation:** {ps.synthesis.recommendation}")
                    st.caption(
                        f"Confidence: {ps.synthesis.recommendation_confidence:.0%}"
                    )
                    st.markdown(ps.synthesis.executive_summary or "_No summary_")
                else:
                    st.write("_No synthesis (pipeline may have stopped early)._")
                c1, c2 = st.columns(2)
                with c1:
                    if ps.analysis.dimension_scores:
                        st.markdown("**Scores (radar dimensions)**")
                        for k, v in ps.analysis.dimension_scores.items():
                            st.write(f"- {k}: {v}/10")
                with c2:
                    if ps.analysis.competitors:
                        st.markdown("**Competitors (from analysis)**")
                        for comp in ps.analysis.competitors[:5]:
                            st.write(
                                f"- **{comp.get('name', '?')}** "
                                f"({comp.get('threat_level', '')})"
                            )


st.title("💼 VC Research Agent")
st.subheader(
    "Multi-agent pipeline: search → analysis → fact-check → synthesis (Gemini + Serper)"
)
st.markdown("---")

mode = st.radio(
    "Select mode",
    [
        "Single company (full pipeline)",
        "Compare companies",
    ],
    horizontal=True,
    key="vc_mode_radio",
)
st.markdown("---")

if mode == "Single company (full pipeline)":
    c1, c2 = st.columns(2)
    with c1:
        startup_name = st.text_input(
            "Company name",
            placeholder="e.g. Northspyre",
            key="vc_single_company_name",
        )
    with c2:
        startup_description = st.text_area(
            "Brief description (optional)",
            placeholder="e.g. AI platform for real estate developers",
            height=100,
            key="vc_single_company_desc",
        )

    b1, b2 = st.columns([3, 1])
    with b1:
        run_clicked = st.button(
            "Run full pipeline", type="primary", use_container_width=True
        )
    with b2:
        if st.button("Clear results", use_container_width=True):
            _clear_single_pipeline()
            st.rerun()

    if run_clicked:
        if not (startup_name or "").strip():
            st.warning("Enter a company name.")
        else:
            st.info(
                "⏱️ **Patience:** this run does ~3 web searches plus **4 Gemini calls** "
                "(analysis, fact-check, synthesis, etc.). Expect **about 2–10 minutes**; "
                "the status box below updates after each agent finishes. "
                "If nothing moves for longer than your `GEMINI_REQUEST_TIMEOUT` (default 120s) "
                "× retries, the run will error instead of hanging forever."
            )
            try:
                with st.status("Running agents…", expanded=True) as status:
                    done = _run_pipeline_with_status(
                        startup_name.strip(),
                        startup_description,
                        log=lambda m: _status_log(status, m),
                    )
                _persist_pipeline_state(done)
                _clear_pdf_keys()
            except Exception as err:
                st.error(
                    "Pipeline stopped with an error. Check the traceback below "
                    "(often a Gemini timeout, quota, or network issue)."
                )
                st.exception(err)

    saved = _load_pipeline_state()
    if saved is not None:
        st.success(f"Showing results for **{saved.company_name}**.")
        if (startup_name or "").strip() and startup_name.strip() != saved.company_name:
            st.caption(
                "Company name in the box differs from these results — run again to refresh."
            )
        _render_single_company_results(saved)

else:
    st.subheader("Compare companies")
    st.caption(
        "Default: same **full pipeline** as single-company mode (per company). "
        "Optional quick mode only runs search + analysis (lighter, shallower)."
    )
    quick_only = st.checkbox(
        "Quick mode only (search + analysis, no fact-check or memo synthesis)",
        value=False,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        s1 = st.text_input("Company 1", placeholder="e.g. Northspyre", key="cmp1")
    with c2:
        s2 = st.text_input("Company 2", placeholder="e.g. EliseAI", key="cmp2")
    with c3:
        s3 = st.text_input("Company 3 (optional)", placeholder="e.g. Cherre", key="cmp3")

    bc1, bc2 = st.columns([3, 1])
    with bc1:
        compare_clicked = st.button("Compare", type="primary", use_container_width=True)
    with bc2:
        if st.button("Clear comparison", use_container_width=True):
            st.session_state.pop(SS_COMPARE, None)
            st.rerun()

    if compare_clicked:
        names = [x.strip() for x in [s1, s2, s3] if x and x.strip()]
        if len(names) < 2:
            st.warning("Enter at least two company names.")
        else:
            errors: List[str] = []
            states_out: List[PipelineState] = []
            for nm in names:
                label = f"{nm} — {'quick' if quick_only else 'full pipeline'}"
                with st.status(label, expanded=True) as stt:
                    stt.write(f"Starting `{nm}`…")

                    def _log(m: str, _st=stt) -> None:
                        _st.write(m)

                    if quick_only:

                        def _on_step(ev: str, __log=_log) -> None:
                            __log(QUICK_STEPS.get(ev, ev))

                        partial, err = run_compare_bundle(nm, "", on_step=_on_step)
                        if err:
                            errors.append(f"{nm}: {err}")
                            _log(f"❌ {err}")
                        else:
                            _log("✅ Search + analysis complete.")
                            states_out.append(partial)
                    else:

                        def _on_step(ev: str, __log=_log) -> None:
                            __log(FULL_PIPELINE_STEPS.get(ev, ev))

                        try:
                            state = run_pipeline(nm, "", on_step=_on_step)
                        except Exception as ex:
                            errors.append(f"{nm}: crashed — {ex}")
                            _log(f"❌ **Crash:** {ex}")
                            continue
                        for err_line in state.errors:
                            _log(f"**Error:** {err_line}")
                        states_out.append(state)
                        if state.errors and not state.synthesis:
                            errors.append(f"{nm}: pipeline incomplete — see log above")

            st.session_state[SS_COMPARE] = {
                "full": not quick_only,
                "errors": errors,
                "states": states_out,
            }

    compare_payload = st.session_state.get(SS_COMPARE)
    if compare_payload:
        _render_compare_results(compare_payload)

st.markdown("---")
st.caption("VC Research Agent | Serper + Gemini | Multi-agent architecture")
