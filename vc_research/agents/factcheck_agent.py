"""Agent 3: Cross-check analysis claims against raw search sources."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from vc_research.llm import generate_json_prompt
from vc_research.models.schemas import (
    AgentResult,
    AnalysisOutput,
    FactCheckOutput,
    SearchOutput,
    VerifiedClaim,
)


def run_factcheck_agent(
    search: SearchOutput,
    analysis: AnalysisOutput,
) -> AgentResult:
    if not search.sources:
        return AgentResult(
            ok=False,
            error="Fact-check requires search sources.",
            agent_name="factcheck",
        )

    sources_payload = [
        {
            "source_id": s.source_id,
            "url": s.url,
            "title": s.title,
            "snippet": s.snippet,
        }
        for s in search.sources
    ]

    claims_payload: List[Dict[str, Any]] = []
    for dim, block in analysis.dimensions.items():
        for c in block.claims:
            claims_payload.append(
                {
                    "dimension": dim,
                    "text": c.text,
                    "source_ids": c.source_ids,
                    "source_urls": c.source_urls,
                }
            )

    if not claims_payload:
        return AgentResult(
            ok=True,
            data=FactCheckOutput(
                company_name=analysis.company_name,
                verified_claims=[],
            ),
            agent_name="factcheck",
        )

    prompt = f"""You verify investment research claims against raw web snippets.

SOURCES:
{json.dumps(sources_payload, ensure_ascii=False)}

CLAIMS TO VERIFY:
{json.dumps(claims_payload, ensure_ascii=False)}

For each claim, decide if the cited source snippets clearly support the claim.
- If supported: status "verified", confidence 0.7-1.0
- If weakly supported or ambiguous: status "uncertain", confidence 0.3-0.6
- If not supported by cited snippets (but might be true elsewhere): status "uncertain", confidence 0.1-0.4
Never use the word "hallucinated". Use "uncertain" when evidence is insufficient.

Return JSON:
{{
  "results": [
    {{
      "dimension": "market_size",
      "text": "exact claim text",
      "status": "verified" | "uncertain",
      "confidence": 0.0-1.0,
      "rationale": "short explanation",
      "source_urls": ["https://..."]
    }}
  ]
}}

Rules:
- Copy claim text exactly as given.
- source_urls should list URLs from SOURCES that you used (subset of cited IDs).
"""

    try:
        text = generate_json_prompt(prompt)
        payload = json.loads(text)
        rows = payload.get("results") or []
        verified: List[VerifiedClaim] = []
        url_by_id = {s.source_id: s.url for s in search.sources}

        for row in rows:
            if not isinstance(row, dict):
                continue
            t = str(row.get("text") or "").strip()
            if not t:
                continue
            dim = str(row.get("dimension") or "unknown")
            st = row.get("status") or "uncertain"
            if st not in ("verified", "uncertain"):
                st = "uncertain"
            try:
                conf = float(row.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            conf = max(0.0, min(1.0, conf))
            rationale = str(row.get("rationale") or "")
            urls = row.get("source_urls") or []
            if isinstance(urls, str):
                urls = [urls]
            urls = [str(u) for u in urls if u]
            # Fallback: map from original claim's source_ids
            if not urls:
                for orig in claims_payload:
                    if orig.get("text") == t:
                        for sid in orig.get("source_ids") or []:
                            u = url_by_id.get(sid)
                            if u:
                                urls.append(u)
                        break
            verified.append(
                VerifiedClaim(
                    text=t,
                    source_urls=urls,
                    status=st,  # type: ignore[arg-type]
                    confidence=conf,
                    rationale=rationale,
                    dimension=dim,
                )
            )

        # If model returned fewer rows, pad uncertain entries for missing claims
        existing = {vc.text for vc in verified}
        for item in claims_payload:
            if item["text"] not in existing:
                urls = []
                for sid in item.get("source_ids") or []:
                    u = url_by_id.get(sid)
                    if u:
                        urls.append(u)
                verified.append(
                    VerifiedClaim(
                        text=item["text"],
                        source_urls=urls,
                        status="uncertain",
                        confidence=0.35,
                        rationale="No explicit verification returned; treated as uncertain.",
                        dimension=item["dimension"],
                    )
                )

        out = FactCheckOutput(
            company_name=analysis.company_name,
            verified_claims=verified,
        )
        return AgentResult(ok=True, data=out, agent_name="factcheck")
    except json.JSONDecodeError as e:
        return AgentResult(
            ok=False,
            error=f"Fact-check JSON parse error: {e}",
            agent_name="factcheck",
        )
    except Exception as e:
        return AgentResult(
            ok=False,
            error=f"Fact-check agent error: {e}",
            agent_name="factcheck",
        )
