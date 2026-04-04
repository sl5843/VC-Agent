"""Orchestrates the four-agent research pipeline with explicit error handling."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from vc_research.agents.analysis_agent import run_analysis_agent
from vc_research.agents.factcheck_agent import run_factcheck_agent
from vc_research.agents.search_agent import run_search_agent
from vc_research.agents.synthesis_agent import run_synthesis_agent
from vc_research.models.schemas import PipelineState


def run_pipeline(
    company_name: str,
    description: str = "",
    on_step: Optional[Callable[[str], None]] = None,
) -> PipelineState:
    """
    Run search → analysis → fact-check → synthesis.
    Stops early on failure; inspect `state.errors` and partial outputs.
    """
    state = PipelineState(
        company_name=company_name.strip(),
        description=(description or "").strip(),
    )

    def _emit(msg: str) -> None:
        if on_step:
            on_step(msg)

    _emit("search:start")
    r_search = run_search_agent(state.company_name)
    if not r_search.ok:
        state.errors.append(f"[search] {r_search.error}")
        _emit("search:failed")
        return state
    state.search = r_search.data
    _emit("search:ok")

    _emit("analysis:start")
    r_analysis = run_analysis_agent(
        state.company_name, state.description, state.search
    )
    if not r_analysis.ok:
        state.errors.append(f"[analysis] {r_analysis.error}")
        _emit("analysis:failed")
        return state
    state.analysis = r_analysis.data
    _emit("analysis:ok")

    _emit("factcheck:start")
    r_fc = run_factcheck_agent(state.search, state.analysis)
    if not r_fc.ok:
        state.errors.append(f"[factcheck] {r_fc.error}")
        _emit("factcheck:failed")
        return state
    state.factcheck = r_fc.data
    _emit("factcheck:ok")

    _emit("synthesis:start")
    competitors = state.analysis.competitors if state.analysis else []
    if not isinstance(competitors, list):
        competitors = []
    r_syn = run_synthesis_agent(state.search, state.factcheck, competitors)
    if not r_syn.ok:
        state.errors.append(f"[synthesis] {r_syn.error}")
        _emit("synthesis:failed")
        return state
    state.synthesis = r_syn.data
    _emit("synthesis:ok")

    return state


def run_compare_bundle(
    company_name: str,
    description: str = "",
    on_step: Optional[Callable[[str], None]] = None,
) -> Tuple[PipelineState, Optional[str]]:
    """
    Lighter path for multi-startup compare: search + analysis only.
    Returns (state_with_search_and_analysis_only, error_or_none).
    """
    state = PipelineState(
        company_name=company_name.strip(),
        description=(description or "").strip(),
    )

    def _emit(msg: str) -> None:
        if on_step:
            on_step(msg)

    _emit("search:start")
    r_search = run_search_agent(state.company_name)
    if not r_search.ok:
        return state, f"[search] {r_search.error}"
    state.search = r_search.data
    _emit("search:ok")

    _emit("analysis:start")
    r_analysis = run_analysis_agent(
        state.company_name, state.description, state.search
    )
    if not r_analysis.ok:
        return state, f"[analysis] {r_analysis.error}"
    state.analysis = r_analysis.data
    _emit("analysis:ok")

    return state, None
