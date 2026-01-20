"""
Chart building utilities using Plotly.

Designed to work in two modes:

1. Full mode (local development):
   - pandas, plotly.express, plotly.io are installed
   - build real charts from DataFrames

2. Light mode (Render demo using requirements-render.txt without pandas):
   - pandas may be missing
   - we avoid import-time crashes and instead raise RuntimeError
     when a chart is requested.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

# Try to import pandas/plotly; if not available (e.g. on Render demo), fall back gracefully
try:
    import pandas as pd  # type: ignore
    import plotly.express as px  # type: ignore
    import plotly.io as pio  # type: ignore
except ImportError:  # pragma: no cover - only in light environments
    pd = None  # type: ignore
    px = None  # type: ignore
    pio = None  # type: ignore


def _ensure_plot_deps() -> None:
    """
    Raise a clear error if pandas/plotly are not available.
    Used to avoid import-time crashes in light environments.
    """
    if pd is None or px is None or pio is None:
        raise RuntimeError(
            "Plotting dependencies (pandas/plotly) are not installed in this environment. "
            "Chart rendering is disabled in this hosted demo. "
            "Run the project locally with full requirements.txt to enable charts."
        )


def figure_to_json(fig):
    """
    Convert a Plotly figure to a pure JSON object
    that can be sent to the frontend.
    """
    _ensure_plot_deps()
    return json.loads(pio.to_json(fig))


def _apply_filters(df, filters: Dict[str, Any] | None):
    """
    Apply simple filter rules to a DataFrame.
    Supported operators per column:
      - eq, ne, gt, lt, in (list)
    Example filters:
      {"Region": {"eq": "North"},
       "Sales": {"gt": 1000}}
    """
    _ensure_plot_deps()
    if not filters:
        return df

    out = df.copy()
    for col, rule in filters.items():
        if col not in out.columns:
            continue

        if isinstance(rule, dict):
            # simple operators: eq, ne, gt, lt, in
            if "eq" in rule:
                out = out[out[col] == rule["eq"]]
            if "ne" in rule:
                out = out[out[col] != rule["ne"]]
            if "gt" in rule:
                out = out[out[col] > rule["gt"]]
            if "lt" in rule:
                out = out[out[col] < rule["lt"]]
            if "in" in rule and isinstance(rule["in"], list):
                out = out[out[col].isin(rule["in"])]

    return out


def _aggregate(
    df,
    x: str | None,
    y: str | None,
    group_by: str | None,
    aggregation: str | None,
) -> Tuple[Any, str]:
    """
    Aggregate data for plotting.
    If y is None, we'll produce counts by category.
    """
    _ensure_plot_deps()

    if group_by and group_by != x:
        group_cols = [c for c in [x, group_by] if c]
    else:
        group_cols = [c for c in [x] if c]

    if y:
        if aggregation:
            agg_func = aggregation
            grouped = df.groupby(group_cols, dropna=False)[y].agg(agg_func).reset_index()
        else:
            grouped = df.groupby(group_cols, dropna=False)[y].sum().reset_index()
    else:
        # e.g. count by category when y is missing
        grouped = df.groupby(group_cols, dropna=False).size().reset_index(name="count")
        y = "count"

    return grouped, y


def build_figure_from_spec(df, chart_spec: Dict[str, Any]):
    """
    Build a Plotly figure from a validated chart spec.

    chart_spec keys:
      - chart_type: "line" | "bar" | "pie" | "histogram" | "scatter"
      - x, y, group_by, aggregation, filters, title
    """
    _ensure_plot_deps()

    chart_type = chart_spec.get("chart_type", "bar")
    x = chart_spec.get("x")
    y = chart_spec.get("y")
    group_by = chart_spec.get("group_by")
    aggregation = chart_spec.get("aggregation")
    filters = chart_spec.get("filters") or {}
    title = chart_spec.get("title") or "Chart"

    # Apply filters and drop rows where x/y are missing
    df2 = _apply_filters(df, filters).dropna(subset=[c for c in [x, y] if c])

    # Ensure datetime x is sorted
    if x and pd is not None and pd.api.types.is_datetime64_any_dtype(df2[x]):
        df2 = df2.sort_values(x)

    grouped, y_col = _aggregate(df2, x, y, group_by, aggregation)

    # Prepare previews
    data_preview = df2.head(10)
    agg_preview = grouped.head(30)

    # Build figure by chart type
    if chart_type == "line":
        fig = px.line(grouped, x=x, y=y_col, color=group_by, title=title)
    elif chart_type == "bar":
        fig = px.bar(
            grouped,
            x=(group_by or x),
            y=y_col,
            color=(None if group_by else None),
            title=title,
        )
    elif chart_type == "pie":
        # For pie: require grouping, y as value
        label_col = group_by or x
        value_col = y_col
        fig = px.pie(grouped, names=label_col, values=value_col, title=title, hole=0.3)
    elif chart_type == "histogram":
        fig = px.histogram(df2, x=y or y_col, title=title)
    elif chart_type == "scatter":
        # Expect x, y numeric
        fig = px.scatter(df2, x=x, y=y, color=group_by, title=title, trendline="ols")
    else:
        # Fallback to bar
        fig = px.bar(grouped, x=(group_by or x), y=y_col, title=title)

    fig.update_layout(margin=dict(l=30, r=10, t=60, b=30), legend_title=None)

    return fig, data_preview, agg_preview


def fallback_spec(question: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Very simple heuristic chart spec used when the LLM fails
    or returns something invalid.
    """
    ltypes = meta.get("logical_types", {})
    cols = meta.get("columns", []) or []

    # Separate columns by logical type
    dt = [c for c, t in ltypes.items() if t == "datetime"]
    nums = [c for c, t in ltypes.items() if t == "numeric"]
    cats = [c for c, t in ltypes.items() if t in ("categorical", "text")]

    spec: Dict[str, Any] = {
        "insight": "Here is an automatic visualization based on your data and question.",
        "suggested_questions": [
            "Show sales trend",
            "Top 10 products by revenue",
            "Distribution of order values",
        ],
    }

    q = (question or "").lower()

    if ("trend" in q or "over time" in q) and dt and nums:
        spec["chart"] = {
            "chart_type": "line",
            "x": dt[0],
            "y": nums[0],
            "aggregation": "sum",
            "group_by": None,
            "filters": {},
            "title": "Trend over time",
        }
    elif ("best" in q or "top" in q) and nums and cats:
        spec["chart"] = {
            "chart_type": "bar",
            "x": cats[0],
            "y": nums[0],
            "aggregation": "sum",
            "group_by": None,
            "filters": {},
            "title": "Top categories",
        }
    elif ("distribution" in q or "hist" in q) and nums:
        spec["chart"] = {
            "chart_type": "histogram",
            "x": None,
            "y": nums[0],
            "aggregation": None,
            "group_by": None,
            "filters": {},
            "title": "Distribution",
        }
    elif any(word in q for word in ("share", "percentage", "pie")):
        label = cats[0] if cats else (cols[0] if cols else None)
        value = nums[0] if nums else None
        spec["chart"] = {
            "chart_type": "pie",
            "x": label,
            "y": value,
            "aggregation": "sum",
            "group_by": label,
            "filters": {},
            "title": "Share",
        }
    else:
        # default: overview bar
        label = cats[0] if cats else (cols[0] if cols else None)
        value = nums[0] if nums else None
        spec["chart"] = {
            "chart_type": "bar",
            "x": label,
            "y": value,
            "aggregation": "sum",
            "group_by": None,
            "filters": {},
            "title": "Overview",
        }

    return spec
