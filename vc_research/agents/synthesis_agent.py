"""Agent 4: Build structured memo from verified claims."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from vc_research.llm import generate_json_prompt
from vc_research.models.schemas import (
    AgentResult,
    FactCheckOutput,
    MemoSection,
    SearchOutput,
    SynthesisOutput,
)

def run_synthesis_agent(
    search: SearchOutput,
    factcheck: FactCheckOutput,
    competitors_json: List[Dict[str, Any]],
) -> AgentResult:
    claims_blob = [
        {
            "dimension": vc.dimension,
            "text": vc.text,
            "status": vc.status,
            "confidence": vc.confidence,
            "source_urls": vc.source_urls,
            "rationale": vc.rationale,
        }
        for vc in factcheck.verified_claims
    ]

    prompt = f"""You are a VC partner drafting an investment memo body.

Company: {search.company_name}

VERIFIED CLAIMS (use only these; keep citations inline as markdown links):
{json.dumps(claims_blob, ensure_ascii=False)}

COMPETITORS (from earlier analysis; may include uncertain details):
{json.dumps(competitors_json, ensure_ascii=False)}

Return JSON:
{{
  "executive_summary": "markdown paragraph(s)",
  "recommendation": "Invest | Pass | Further diligence — with short justification",
  "recommendation_confidence": 0.0-1.0,
  "sections": [
    {{
      "title": "string",
      "body_markdown": "markdown with inline [label](url) citations after sentences",
      "confidence": 0.0-1.0,
      "key_citations": ["url1", "url2"]
    }}
  ]
}}

Rules:
- Each factual sentence in body_markdown should end with or include markdown links to source URLs from claims.
- Clearly mark uncertain claims: prefix with "**Uncertain:**" when status is uncertain.
- Do not add new factual claims or URLs beyond what appears in VERIFIED CLAIMS / COMPETITORS.
- Use 5-12 sentences per main section where possible.
"""

    try:
        text = generate_json_prompt(prompt)
        payload = json.loads(text)
        sections: List[MemoSection] = []
        for s in payload.get("sections") or []:
            if not isinstance(s, dict):
                continue
            title = str(s.get("title") or "Section").strip()
            body = str(s.get("body_markdown") or "").strip()
            try:
                conf = float(s.get("confidence", 0.6))
            except (TypeError, ValueError):
                conf = 0.6
            kc = s.get("key_citations") or []
            if isinstance(kc, str):
                kc = [kc]
            kc = [str(x) for x in kc if x]
            sections.append(
                MemoSection(
                    title=title,
                    body_markdown=body,
                    confidence=max(0.0, min(1.0, conf)),
                    key_citations=kc,
                )
            )

        rec_conf = float(payload.get("recommendation_confidence") or 0.5)
        rec_conf = max(0.0, min(1.0, rec_conf))

        out = SynthesisOutput(
            company_name=search.company_name,
            sections=sections,
            recommendation=str(payload.get("recommendation") or "Further diligence"),
            recommendation_confidence=rec_conf,
            executive_summary=str(payload.get("executive_summary") or ""),
        )
        return AgentResult(ok=True, data=out, agent_name="synthesis")
    except json.JSONDecodeError as e:
        return AgentResult(
            ok=False,
            error=f"Synthesis JSON parse error: {e}",
            agent_name="synthesis",
        )
    except Exception as e:
        return AgentResult(
            ok=False,
            error=f"Synthesis agent error: {e}",
            agent_name="synthesis",
        )
