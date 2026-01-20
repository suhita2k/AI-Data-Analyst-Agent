import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, field_validator

# We intentionally do NOT import pandas here, so this file works
# even in light environments (e.g. Render demo) without pandas installed.

load_dotenv()

PROVIDER = os.getenv("ADA_LLM_PROVIDER", "gemini").lower()

# -----------------------------
# JSON spec schema
# -----------------------------

ALLOWED_CHARTS = {"line", "bar", "pie", "histogram", "scatter"}
ALLOWED_AGG = {"sum", "mean", "count", "median", "min", "max"}


class ChartSpec(BaseModel):
    chart_type: str
    x: str | None = None
    y: str | None = None
    group_by: str | None = None
    aggregation: str | None = None
    filters: Dict[str, Any] | None = None
    title: str | None = None

    @field_validator("chart_type")
    @classmethod
    def chart_in_whitelist(cls, v: str) -> str:
        if v not in ALLOWED_CHARTS:
            raise ValueError(f"chart_type must be one of {ALLOWED_CHARTS}")
        return v

    @field_validator("aggregation")
    @classmethod
    def agg_in_whitelist(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ALLOWED_AGG:
            raise ValueError(f"aggregation must be one of {ALLOWED_AGG}")
        return v


def _compose_prompt(question: str, meta: dict, df_sample: Any) -> str:
    """
    Build the text prompt we send to the LLM.

    df_sample is expected to be a small DataFrame-like object with
    .to_dict(orient="records"), but we treat it generically to avoid
    requiring pandas in this module.
    """
    cols = meta.get("columns", [])
    ltypes = meta.get("logical_types", {})

    if df_sample is not None and hasattr(df_sample, "to_dict"):
        sample = df_sample.to_dict(orient="records")
    else:
        sample = []

    guidance = f"""
You are ADA, an expert data analyst.

Task:
1. Understand the user's question about a single uploaded dataset.
2. Propose ONE chart specification and a simple English insight.
3. Use only existing columns and the allowed chart types and aggregations.

Allowed chart types: {list(ALLOWED_CHARTS)}
Allowed aggregations: {list(ALLOWED_AGG)}

Important rules:
- Choose appropriate x/y/group_by based on the question and data types.
- For time trends: x = datetime column, chart_type = "line", aggregation = sum/mean as appropriate.
- For best/worst product/region: chart_type = "bar", group_by = category, aggregation = sum or count of a numeric column.
- For distribution: use histogram with a numeric column.
- For correlation: use scatter with two numeric columns.
- If the question is vague, provide a reasonable default and explain assumptions.
- Do not invent columns that are not in the dataset.
- Only use the allowed chart types and aggregations.

You MUST output strictly in this JSON format:

{{
  "chart": {{
    "chart_type": "...",
    "x": "...",
    "y": "...",
    "group_by": "...",
    "aggregation": "...",
    "filters": {{}},
    "title": "..."
  }},
  "insight": "...",
  "suggested_questions": ["...", "..."]
}}

Dataset columns: {cols}
Logical types by column: {ltypes}
Sample rows (truncated): {sample}

User question: {question}
"""
    return guidance


def _validate_and_fix(spec_dict: dict, meta: dict) -> dict:
    """
    Validate LLM output and fix obvious problems:
    - Ensure columns exist
    - Fill missing x/y/aggregation with reasonable defaults
    - Fall back to a minimal safe spec if validation fails
    """
    cols = set(meta.get("columns", []))
    chart = (spec_dict or {}).get("chart", {}) or {}

    # Drop invalid columns
    for key in ("x", "y", "group_by"):
        val = chart.get(key)
        if val and val not in cols:
            chart[key] = None

    ltypes = meta.get("logical_types", {})

    # If missing x for line chart, try to pick a datetime column
    if chart.get("chart_type") == "line" and not chart.get("x"):
        dt = [c for c, t in ltypes.items() if t == "datetime"]
        if dt:
            chart["x"] = dt[0]

    # If missing y, pick first numeric
    if not chart.get("y"):
        nums = [c for c, t in ltypes.items() if t == "numeric"]
        if nums:
            chart["y"] = nums[0]

    # Default aggregation if missing
    if not chart.get("aggregation"):
        chart["aggregation"] = "sum"

    spec_dict["chart"] = chart

    # Validate with Pydantic
    try:
        ChartSpec(**chart)  # if this fails, we go to minimal fallback
        return spec_dict
    except ValidationError:
        # Minimal final fallback
        fallback_chart = {
            "chart_type": "bar",
            "x": None,
            "y": None,
            "group_by": None,
            "aggregation": "sum",
            "filters": {},
            "title": "Chart",
        }
        spec_dict["chart"] = fallback_chart
        return spec_dict


def generate_chart_spec_and_insight(
    question: str, meta: dict, df_sample: Any
) -> dict:
    """
    Main function used by the API:
    - Compose prompt
    - Call Gemini or OpenAI (depending on PROVIDER)
    - Parse JSON
    - Validate + fix spec
    - Return dict with "chart", "insight", "suggested_questions"
    """
    prompt = _compose_prompt(question, meta, df_sample)

    if PROVIDER == "gemini":
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set in the environment.")

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"response_mime_type": "application/json"},
        )

        resp = model.generate_content(prompt)
        text = resp.text
    else:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in the environment.")

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are ADA, a helpful data analyst."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        text = resp.choices[0].message.content

    try:
        spec = json.loads(text)
        spec = _validate_and_fix(spec, meta)
        return spec
    except Exception as e:
        # If parsing or validation fails, raise a clear error
        raise RuntimeError(f"LLM response parsing failed: {e}; raw={text[:500]}")
