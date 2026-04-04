"""Agent 1: Serper-backed web search → structured JSON sources."""

from __future__ import annotations

from typing import List

import requests

from vc_research.config import get_serper_key
from vc_research.models.schemas import AgentResult, SearchOutput, SourceDoc

SERPER_URL = "https://google.serper.dev/search"


def _serper_error_detail(response: requests.Response) -> str:
    text = (response.text or "").strip()
    if len(text) > 400:
        text = text[:400] + "…"
    if not text:
        return ""
    return f" API response: {text}"


def _serper_search(query: str, num: int, api_key: str) -> dict:
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": num}
    response = requests.post(SERPER_URL, headers=headers, json=payload, timeout=45)
    if response.status_code >= 400:
        detail = _serper_error_detail(response)
        if response.status_code == 403:
            try:
                body = response.json()
            except (ValueError, TypeError):
                body = {}
            if isinstance(body, dict) and body.get("message") == "Unauthorized.":
                hint = (
                    "Serper says Unauthorized — the API key is wrong, expired, or not pasted correctly. "
                    "Copy the key again from https://serper.dev/dashboard (field labeled API key), "
                    "set Streamlit secret name exactly `SERPER_API_KEY`, no spaces, then reboot the app."
                )
            else:
                hint = (
                    "Serper returned 403 — invalid key, revoked key, or account issue. "
                    "Verify SERPER_API_KEY at https://serper.dev/dashboard and that your plan has credits."
                )
            raise requests.exceptions.RequestException(hint + detail)
        response.raise_for_status()
    return response.json()


def run_search_agent(company_name: str, num_per_query: int = 6) -> AgentResult:
    """
    Retrieve funding news, competitor hints, and market signals via multiple queries.
    Returns deduplicated structured sources with stable IDs for downstream citation.
    """
    name = (company_name or "").strip()
    if not name:
        return AgentResult(
            ok=False,
            error="Company name is required.",
            agent_name="search",
        )

    queries = [
        f"{name} startup funding round investment news",
        f"{name} competitors alternatives comparison",
        f"{name} market TAM industry trends growth",
    ]

    try:
        api_key = get_serper_key()
    except Exception as e:
        return AgentResult(
            ok=False,
            error=str(e),
            agent_name="search",
        )

    seen_urls: set[str] = set()
    sources: List[SourceDoc] = []
    idx = 0

    try:
        for q in queries:
            data = _serper_search(q, num_per_query, api_key)
            organic = data.get("organic") or []
            for item in organic:
                if not isinstance(item, dict):
                    continue
                url = (item.get("link") or item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                sid = f"src_{idx}"
                idx += 1
                sources.append(
                    SourceDoc(
                        source_id=sid,
                        url=url,
                        title=(item.get("title") or "")[:500],
                        snippet=(item.get("snippet") or "")[:2000],
                        query=q,
                    )
                )
    except requests.RequestException as e:
        return AgentResult(
            ok=False,
            error=f"Serper request failed: {e}",
            agent_name="search",
        )
    except Exception as e:
        return AgentResult(
            ok=False,
            error=f"Search agent error: {e}",
            agent_name="search",
        )

    if not sources:
        return AgentResult(
            ok=False,
            error="No search results returned. Check the company name or Serper quota.",
            agent_name="search",
        )

    out = SearchOutput(
        company_name=name,
        sources=sources,
        raw_queries=queries,
    )
    return AgentResult(ok=True, data=out, agent_name="search")
