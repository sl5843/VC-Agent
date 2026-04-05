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

    prompt = f"""You are a VC partner drafting an investment memo for a professional reader.

Company: {search.company_name}

VERIFIED CLAIMS (only facts and URLs may come from here):
{json.dumps(claims_blob, ensure_ascii=False)}

COMPETITORS (may include uncertain details):
{json.dumps(competitors_json, ensure_ascii=False)}

Return JSON:
{{
  "executive_summary": "Clean prose only. After each sentence that needs a source, add a footnote marker like [1] or [2]. Do NOT paste raw URLs in this text. Do NOT use markdown links.",
  "executive_summary_footnotes": ["https://url-for-[1]", "https://url-for-[2]"],
  "recommendation": "Invest | Pass | Further diligence — short justification (no raw URLs in text)",
  "recommendation_confidence": 0.0-1.0,
  "sections": [
    {{
      "title": "string",
      "body_markdown": "Same style: professional prose, footnote markers [1][2] only, no raw URLs in the paragraph text.",
      "footnotes": ["url for [1]", "url for [2]"],
      "confidence": 0.0-1.0,
      "key_citations": []
    }}
  ]
}}

Rules:
- executive_summary_footnotes[i] is the source for marker [i+1] in executive_summary (first URL = [1], etc.).
- Each section footnotes[] order matches [1], [2] in that section's body_markdown (restart numbering at [1] per section).
- Write tight, memo-style sentences (no bullet dumps). Mark uncertain claims with "**Uncertain:**" before the sentence.
- key_citations may list the same URLs as footnotes for tooling; may be empty.
- No new URLs beyond VERIFIED CLAIMS (and competitor context where cited).
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
            fn = s.get("footnotes") or []
            if isinstance(fn, str):
                fn = [fn]
            footnotes = [str(x) for x in fn if x]
            sections.append(
                MemoSection(
                    title=title,
                    body_markdown=body,
                    confidence=max(0.0, min(1.0, conf)),
                    key_citations=kc,
                    footnotes=footnotes,
                )
            )

        rec_conf = float(payload.get("recommendation_confidence") or 0.5)
        rec_conf = max(0.0, min(1.0, rec_conf))

        es_fn = payload.get("executive_summary_footnotes") or []
        if isinstance(es_fn, str):
            es_fn = [es_fn]
        exec_foot = [str(x) for x in es_fn if x]

        out = SynthesisOutput(
            company_name=search.company_name,
            sections=sections,
            recommendation=str(payload.get("recommendation") or "Further diligence"),
            recommendation_confidence=rec_conf,
            executive_summary=str(payload.get("executive_summary") or ""),
            executive_summary_footnotes=exec_foot,
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
