"""Plotly visualizations for scores and competitive market map."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go

DIMENSION_LABELS = [
    ("market_size", "Market size"),
    ("traction", "Traction"),
    ("team", "Team"),
    ("competition", "Competition"),
    ("business_model", "Business model"),
    ("risk", "Risk (higher = more risk)"),
]


def _radial_r_values(
    dimension_scores: Dict[str, Optional[int]], keys: List[str]
) -> List[float]:
    out: List[float] = []
    for k in keys:
        v = dimension_scores.get(k)
        if v is None:
            out.append(float("nan"))
        else:
            out.append(float(max(0, min(10, int(v)))))
    return out


def create_dimension_radar(
    dimension_scores: Dict[str, Optional[int]], company_name: str
) -> go.Figure:
    keys = [k for k, _ in DIMENSION_LABELS]
    labels = [lbl for _, lbl in DIMENSION_LABELS]
    values = _radial_r_values(dimension_scores, keys)
    if all(math.isnan(v) for v in values):
        fig = go.Figure()
        fig.update_layout(
            title=f"{company_name} — dimension scores",
            annotations=[
                dict(
                    text="No numeric scores: sources did not support a 0-10 rating on any dimension.",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=14, color="#555"),
                )
            ],
            height=420,
        )
        return fig
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]
    has_missing = any(math.isnan(v) for v in values)

    fig = go.Figure(
        data=go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            fill="toself",
            line_color="#667eea",
            fillcolor="rgba(102, 126, 234, 0.35)",
            connectgaps=False,
            name=company_name,
        )
    )
    layout_kw: Dict[str, Any] = dict(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        showlegend=False,
        title=f"{company_name} — dimension scores",
        height=420,
    )
    if has_missing:
        layout_kw["margin"] = dict(l=48, r=48, t=56, b=72)
        layout_kw["annotations"] = [
            dict(
                text="Gaps indicate dimensions that were not scored — insufficient evidence in retrieved sources (not a score of zero).",
                xref="paper",
                yref="paper",
                x=0.5,
                y=-0.12,
                yanchor="top",
                showarrow=False,
                font=dict(size=11, color="#555"),
                align="center",
            )
        ]
    fig.update_layout(**layout_kw)
    return fig


def create_market_map(
    company_name: str,
    competitors: Optional[List[Dict[str, Any]]],
) -> go.Figure:
    """Scatter positions: target company at center; competitors by threat radius."""
    comps = competitors or []
    threat_radius = {"High": 1.0, "Medium": 0.58, "Low": 0.28}
    colors = {"High": "#e74c3c", "Medium": "#f39c12", "Low": "#27ae60"}

    xs = [0.0]
    ys = [0.0]
    names = [company_name]
    marker_sizes = [28]
    marker_colors = ["#2c3e50"]
    texts = [f"<b>{company_name}</b><br>(target)"]

    n = max(len(comps), 1)
    for i, c in enumerate(comps[:12]):
        name = str(c.get("name") or f"Competitor {i+1}")
        threat = str(c.get("threat_level") or "Medium")
        r = threat_radius.get(threat, 0.5)
        angle = (2 * math.pi * i) / max(n, 3)
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        xs.append(x)
        ys.append(y)
        names.append(name)
        marker_sizes.append(16)
        marker_colors.append(colors.get(threat, "#95a5a6"))
        desc = str(c.get("description") or "")[:120]
        texts.append(f"<b>{name}</b><br>{threat}<br>{desc}")

    fig = go.Figure(
        data=go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=names,
            textposition="top center",
            marker=dict(size=marker_sizes, color=marker_colors, line=dict(width=1, color="#fff")),
            hovertext=texts,
            hoverinfo="text",
        )
    )
    fig.update_layout(
        title=f"Market map — {company_name} vs competitors",
        xaxis=dict(
            visible=True,
            zeroline=True,
            showticklabels=False,
            title="",
            range=[-1.25, 1.25],
        ),
        yaxis=dict(
            visible=True,
            zeroline=True,
            showticklabels=False,
            title="",
            range=[-1.25, 1.25],
        ),
        height=480,
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor="#f8f9fb",
    )
    return fig


def create_comparison_radar(
    all_scores: Dict[str, Dict[str, Optional[int]]],
) -> go.Figure:
    palette = ["#667eea", "#f093fb", "#4facfe", "#43e97b", "#fa709a"]
    fig = go.Figure()
    keys = [k for k, _ in DIMENSION_LABELS]
    labels = [lbl for _, lbl in DIMENSION_LABELS]
    labels_closed = labels + [labels[0]]
    any_missing = False

    for i, (startup, scores) in enumerate(all_scores.items()):
        values = _radial_r_values(scores, keys)
        if any(math.isnan(v) for v in values):
            any_missing = True
        values_closed = values + [values[0]]
        color = palette[i % len(palette)]
        fig.add_trace(
            go.Scatterpolar(
                r=values_closed,
                theta=labels_closed,
                fill="toself",
                name=startup,
                line_color=color,
                opacity=0.35,
                connectgaps=False,
            )
        )

    layout_kw: Dict[str, Any] = dict(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        title="Startup comparison — dimension scores",
        height=500,
    )
    if any_missing:
        layout_kw["margin"] = dict(l=48, r=48, t=56, b=72)
        layout_kw["annotations"] = [
            dict(
                text="Polygon gaps: that startup had no defensible score for that dimension given available sources.",
                xref="paper",
                yref="paper",
                x=0.5,
                y=-0.12,
                yanchor="top",
                showarrow=False,
                font=dict(size=11, color="#555"),
                align="center",
            )
        ]
    fig.update_layout(**layout_kw)
    return fig
