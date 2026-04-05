"""API configuration (Streamlit secrets when available)."""

from __future__ import annotations

import os


def _normalize_secret(value: str) -> str:
    """Strip whitespace/newlines from pasted keys (common in TOML/UI)."""
    return (value or "").strip().strip('"').strip("'")


def get_gemini_key() -> str:
    try:
        import streamlit as st

        return _normalize_secret(str(st.secrets["GEMINI_API_KEY"]))
    except Exception:
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            return _normalize_secret(key)
        raise RuntimeError(
            "GEMINI_API_KEY not found. Set in .streamlit/secrets.toml or environment."
        ) from None


def get_serper_key() -> str:
    """API key from https://serper.dev/dashboard (Google search via Serper)."""
    try:
        import streamlit as st

        return _normalize_secret(str(st.secrets["SERPER_API_KEY"]))
    except Exception:
        key = os.environ.get("SERPER_API_KEY")
        if key:
            return _normalize_secret(key)
        raise RuntimeError(
            "SERPER_API_KEY not found. Get a key at https://serper.dev/dashboard "
            "and set it in .streamlit/secrets.toml or the SERPER_API_KEY environment variable."
        ) from None


def get_gemini_model_name() -> str:
    """Model id for google-generativeai, e.g. gemini-2.5-flash, gemini-2.5-flash-lite."""
    try:
        import streamlit as st

        if "GEMINI_MODEL" in st.secrets:
            return _normalize_secret(str(st.secrets["GEMINI_MODEL"]))
    except Exception:
        pass
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
