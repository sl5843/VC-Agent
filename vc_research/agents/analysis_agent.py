"""Agent 2: Gemini analysis with mandatory source citations."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from vc_research.llm import generate_json_prompt
from vc_research.models.schemas import (
    AgentResult,
    AnalysisOutput,
    Claim,
    DimensionInsights,
    SearchOutput,
)

DIMENSIONS = [
    "market_size",
    "traction",
    "team",
    "competition",
    "business_model",
    "risk",
]


def _parse_analysis_json(
    company_name: str, payload: Dict[str, Any], valid_ids: set[str]
) -> AnalysisOutput:
    dims_out: Dict[str, DimensionInsights] = {}
    raw_dims = payload.get("dimensions") or {}
    for d in DIMENSIONS:
        block = raw_dims.get(d) or {}
        claims_raw = block.get("claims") or []
        claims: List[Claim] = []
        for c in claims_raw:
            if not isinstance(c, dict):
                continue
            text = str(c.get("text") or "").strip()
            if not text:
                continue
            ids = c.get("source_ids") or c.get("citation_source_ids") or []
            if isinstance(ids, str):
                ids = [ids]
            ids = [str(x) for x in ids if str(x) in valid_ids]
            urls = c.get("source_urls") or []
            if isinstance(urls, str):
                urls = [urls]
            urls = [str(u) for u in urls if u]
            claims.append(Claim(text=text, source_ids=ids, source_urls=urls))
        dims_out[d] = DimensionInsights(
            dimension=d,
            claims=claims,
            notes=str(block.get("notes") or ""),
        )

    competitors = payload.get("competitors") or []
    if not isinstance(competitors, list):
        competitors = []

    scores_raw = payload.get("dimension_scores") or {}
    if not isinstance(scores_raw, dict):
        scores_raw = {}
    dimension_scores: Dict[str, Optional[int]] = {}
    for d in DIMENSIONS:
        if d not in scores_raw:
            dimension_scores[d] = None
            continue
        raw_val = scores_raw[d]
        if raw_val is None:
            dimension_scores[d] = None
            continue
        try:
            v = int(raw_val)
        except (TypeError, ValueError):
            dimension_scores[d] = None
            continue
        dimension_scores[d] = max(0, min(10, v))

    return AnalysisOutput(
        company_name=company_name,
        dimensions=dims_out,
        competitors=competitors,
        dimension_scores=dimension_scores,
    )


def run_analysis_agent(
    company_name: str,
    description: str,
    search: SearchOutput,
) -> AgentResult:
    if not search or not search.sources:
        return AgentResult(
            ok=False,
            error="Analysis requires non-empty search results.",
            agent_name="analysis",
        )

    catalog = []
    for s in search.sources:
        catalog.append(
            {
                "source_id": s.source_id,
                "url": s.url,
                "title": s.title,
                "snippet": s.snippet,
            }
        )
    valid_ids = {s.source_id for s in search.sources}

    prompt = f"""You are a venture capital analyst. Reason ONLY from the provided sources.
Company: {company_name}
Optional context from user: {description or "N/A"}

SOURCES (each claim MUST cite one or more source_id values from this list only):
{json.dumps(catalog, ensure_ascii=False)}

Return a single JSON object with this exact shape:
{{
  "dimensions": {{
    "market_size": {{ "claims": [{{ "text": "...", "source_ids": ["src_0"] }}], "notes": "" }},
    "traction": {{ "claims": [...], "notes": "" }},
    "team": {{ "claims": [...], "notes": "" }},
    "competition": {{ "claims": [...], "notes": "" }},
    "business_model": {{ "claims": [...], "notes": "" }},
    "risk": {{ "claims": [...], "notes": "" }}
  }},
  "competitors": [
    {{ "name": "string", "description": "string", "threat_level": "High|Medium|Low", "source_ids": ["src_0"] }}
  ],
  "dimension_scores": {{
    "market_size": <integer 0-10 or null if not assessable from sources>,
    "traction": <0-10 or null>,
    "team": <0-10 or null>,
    "competition": <0-10 or null>,
    "business_model": <0-10 or null>,
    "risk": <0-10 or null>
  }}
}}

Rules:
- Every claim string must be supported by at least one source_id from SOURCES.
- Prefer 2-5 substantive claims per dimension; use fewer if sources are thin.
- For risk scores, higher means more risk (worse).
- For dimension_scores: use an integer 0-10 only when snippets support a defensible rating. If sources lack evidence for a dimension (e.g. team background not covered), set that key to null or omit it — do NOT use 0 as a placeholder for unknown.
- Competitors must also include source_ids when possible.
- Do not invent URLs or facts not implied by snippets.
"""

    try:
        text = generate_json_prompt(prompt)
        payload = json.loads(text)
        analysis = _parse_analysis_json(company_name, payload, valid_ids)
        return AgentResult(ok=True, data=analysis, agent_name="analysis")
    except json.JSONDecodeError as e:
        return AgentResult(
            ok=False,
            error=f"Analysis JSON parse error: {e}",
            agent_name="analysis",
        )
    except Exception as e:
        return AgentResult(
            ok=False,
            error=f"Analysis agent error: {e}",
            agent_name="analysis",
        )
