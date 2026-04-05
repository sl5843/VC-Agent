"""Shared Gemini client."""

from __future__ import annotations

import os
from typing import Any, Optional

import google.generativeai as genai

from vc_research.config import get_gemini_key, get_gemini_model_name

_model = None
_model_id: Optional[str] = None

# Per-request cap so the UI cannot hang forever on a stuck HTTP call (seconds).
_GEMINI_TIMEOUT = int(os.environ.get("GEMINI_REQUEST_TIMEOUT", "120"))


def get_model():
    global _model, _model_id
    name = get_gemini_model_name()
    if _model is None or _model_id != name:
        genai.configure(api_key=get_gemini_key())
        _model = genai.GenerativeModel(name)
        _model_id = name
    return _model


def _response_text(response: Any) -> str:
    try:
        t = (response.text or "").strip()
    except ValueError as e:
        fb = getattr(response, "prompt_feedback", None)
        cand = None
        if getattr(response, "candidates", None):
            cand = response.candidates[0]
        block = getattr(cand, "finish_reason", None) if cand else None
        raise ValueError(
            f"Gemini returned no text (blocked, empty, or unsupported). "
            f"prompt_feedback={fb!r} finish_reason={block!r}"
        ) from e
    if not t:
        raise ValueError("Empty model response text")
    return t


def _generate_content(model, prompt: str, cfg) -> Any:
    """Call Gemini with a timeout when the installed SDK supports it."""
    try:
        return model.generate_content(
            prompt,
            generation_config=cfg,
            request_options={"timeout": _GEMINI_TIMEOUT},
        )
    except TypeError:
        return model.generate_content(prompt, generation_config=cfg)


def generate_json_prompt(prompt: str, max_retries: int = 1) -> str:
    """Ask Gemini for JSON-only output."""
    model = get_model()
    cfg = genai.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.35,
    )
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            response = _generate_content(model, prompt, cfg)
            return _response_text(response)
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f"Gemini JSON generation failed after {max_retries + 1} attempt(s): {last_err}"
    ) from last_err
