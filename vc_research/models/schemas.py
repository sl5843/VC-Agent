"""Shared structured types for the multi-agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class AgentResult:
    """Standard wrapper for every agent step."""

    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    agent_name: str = ""


@dataclass
class SourceDoc:
    source_id: str
    url: str
    title: str
    snippet: str
    query: str = ""


@dataclass
class SearchOutput:
    company_name: str
    sources: List[SourceDoc]
    raw_queries: List[str] = field(default_factory=list)

    def to_llm_context(self) -> str:
        lines = []
        for s in self.sources:
            lines.append(
                f"[{s.source_id}] URL: {s.url}\nTitle: {s.title}\nSnippet: {s.snippet}\n"
            )
        return "\n".join(lines)

    def by_id(self) -> Dict[str, SourceDoc]:
        return {s.source_id: s for s in self.sources}


DimensionKey = Literal[
    "market_size",
    "traction",
    "team",
    "competition",
    "business_model",
    "risk",
]


@dataclass
class Claim:
    text: str
    source_ids: List[str]
    source_urls: List[str]


@dataclass
class DimensionInsights:
    dimension: str
    claims: List[Claim]
    notes: str = ""


@dataclass
class AnalysisOutput:
    company_name: str
    dimensions: Dict[str, DimensionInsights]
    competitors: List[Dict[str, Any]]
    dimension_scores: Dict[str, int]


@dataclass
class VerifiedClaim:
    text: str
    source_urls: List[str]
    status: Literal["verified", "uncertain"]
    confidence: float
    rationale: str
    dimension: str


@dataclass
class FactCheckOutput:
    company_name: str
    verified_claims: List[VerifiedClaim]


@dataclass
class MemoSection:
    title: str
    body_markdown: str
    confidence: float
    key_citations: List[str]


@dataclass
class SynthesisOutput:
    company_name: str
    sections: List[MemoSection]
    recommendation: str
    recommendation_confidence: float
    executive_summary: str


@dataclass
class PipelineState:
    company_name: str
    description: str
    search: Optional[SearchOutput] = None
    analysis: Optional[AnalysisOutput] = None
    factcheck: Optional[FactCheckOutput] = None
    synthesis: Optional[SynthesisOutput] = None
    errors: List[str] = field(default_factory=list)
