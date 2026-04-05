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


def _scored_arc_runs(scored: List[bool]) -> List[List[int]]:
    """
    Group dimension indices that are contiguous on the polar circle (wrapping at n-1 -> 0).
    Example: scored at market, traction and competition..risk merges into one arc 3,4,5,0,1 when team is missing.
    """
    n = len(scored)
    s = sorted(i for i in range(n) if scored[i])
    if not s:
        return []
    if len(s) == n:
        return [list(range(n))]
    chunks: List[List[int]] = []
    chunk = [s[0]]
    for k in range(1, len(s)):
        if s[k] - s[k - 1] == 1:
            chunk.append(s[k])
        else:
            chunks.append(chunk)
            chunk = [s[k]]
    chunks.append(chunk)
    if len(chunks) >= 2 and chunks[0][0] == 0 and chunks[-1][-1] == n - 1:
        chunks = [chunks[-1] + chunks[0]] + chunks[1:-1]
    return chunks


def _hex_to_fill_rgba(hex_color: str, alpha: float = 0.35) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(102, 126, 234,{alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _add_radar_traces(
    fig: go.Figure,
    labels: List[str],
    values: List[float],
    line_color: str,
    fillcolor: str,
    name: str,
    *,
    show_legend: bool = True,
) -> bool:
    """
    Add filled wedges for each contiguous scored arc, then outline+markers.
    Plotly cannot fill across NaN in one trace; NaN breaks toself and drops wedges
    between valid neighbors (e.g. market size vs traction when team is missing).
    Returns True if any dimension was unscored.
    """
    n = len(labels)
    scored = [not math.isnan(values[i]) for i in range(n)]
    if not any(scored):
        return False
    runs = _scored_arc_runs(scored)
    has_missing = not all(scored)

    for run in runs:
        if len(run) < 2:
            continue
        thetas = [labels[i] for i in run]
        rs = [values[i] for i in run]
        fig.add_trace(
            go.Scatterpolar(
                r=rs + [0.0, 0.0],
                theta=thetas + [thetas[-1], thetas[0]],
                fill="toself",
                fillcolor=fillcolor,
                line=dict(width=0),
                mode="lines",
                hoverinfo="skip",
                showlegend=False,
            )
        )

    line_theta: List[Any] = []
    line_r: List[Any] = []
    for ri, run in enumerate(runs):
        if ri > 0:
            line_theta.append(None)
            line_r.append(None)
        if len(run) == 1:
            line_theta.append(labels[run[0]])
            line_r.append(values[run[0]])
        else:
            line_theta.extend(labels[i] for i in run)
            line_r.extend(values[i] for i in run)

    fig.add_trace(
        go.Scatterpolar(
            r=line_r,
            theta=line_theta,
            fill="none",
            mode="lines+markers",
            line=dict(color=line_color, width=2),
            marker=dict(size=7, color=line_color),
            connectgaps=False,
            name=name,
            showlegend=show_legend,
        )
    )
    return has_missing


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

    fig = go.Figure()
    line_color = "#667eea"
    fillcolor = _hex_to_fill_rgba(line_color, 0.35)
    has_missing = _add_radar_traces(
        fig, labels, values, line_color, fillcolor, company_name, show_legend=False
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
                text="Missing axis: not scored from sources (not zero). Shaded regions follow scored dimensions only.",
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
    any_missing = False

    for i, (startup, scores) in enumerate(all_scores.items()):
        values = _radial_r_values(scores, keys)
        color = palette[i % len(palette)]
        if _add_radar_traces(
            fig,
            labels,
            values,
            color,
            _hex_to_fill_rgba(color, 0.35),
            startup,
            show_legend=True,
        ):
            any_missing = True

    layout_kw: Dict[str, Any] = dict(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        title="Startup comparison — dimension scores",
        height=500,
    )
    if any_missing:
        layout_kw["margin"] = dict(l=48, r=48, t=56, b=72)
        layout_kw["annotations"] = [
            dict(
                text="Missing axes: not scored from sources. Shaded regions follow scored dimensions only.",
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
