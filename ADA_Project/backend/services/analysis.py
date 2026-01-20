"""
Data loading and simple profiling utilities.

Designed to work in two modes:

1. Full mode (local development):
   - pandas and numpy are installed via requirements.txt
   - real CSV/XLSX loading and profiling

2. Light mode (Render demo using requirements-render.txt without pandas):
   - pandas / numpy may be missing
   - we avoid import-time crashes and return friendly placeholders
"""

from __future__ import annotations

from typing import Any, Dict

# Try to import pandas/numpy; if not available (e.g. on Render demo), fall back gracefully
try:
    import pandas as pd
    import numpy as np
except ImportError:  # pragma: no cover - only in light environments
    pd = None  # type: ignore
    np = None  # type: ignore


def _ensure_pandas() -> None:
    """
    Raise a clear error if pandas is not available.
    Used in environments where uploads should not hard-crash.
    """
    if pd is None:
        raise RuntimeError(
            "Pandas is not installed in this environment. "
            "Data upload and analysis are disabled in this hosted demo. "
            "Run the project locally with 'requirements.txt' to enable full functionality."
        )


def load_dataset(path: str):
    """
    Load a dataset from CSV or Excel into a Pandas DataFrame.

    In light environments (no pandas), raises a RuntimeError with a clear message.
    """
    _ensure_pandas()  # will raise if pandas is missing

    if path.lower().endswith(".csv"):
        df = pd.read_csv(path, low_memory=False)
    else:
        # Excel: .xlsx or .xls
        df = pd.read_excel(path, engine="openpyxl")

    # Try to parse dates based on column name
    for col in df.columns:
        col_lower = col.lower()
        if "date" in col_lower or "time" in col_lower:
            try:
                df[col] = pd.to_datetime(df[col], errors="ignore")
            except Exception:
                # If parsing fails, just leave as-is
                pass

    return df


def profile_dataset(df) -> Dict[str, Any]:
    """
    Basic profiling of the dataset:
    - number of rows and columns
    - data types
    - logical types (numeric / categorical / datetime / text)
    - missing value counts
    - sample rows

    If pandas is not available, returns a minimal placeholder structure.
    """
    if pd is None:
        # Light environment: return a dummy profile
        return {
            "rows": 0,
            "cols": 0,
            "columns": [],
            "dtypes": {},
            "logical_types": {},
            "missing": {},
            "sample": [],
            "summary": {},
        }

    dtypes = df.dtypes.astype(str).to_dict()
    n_rows, n_cols = df.shape
    missing = df.isna().sum().to_dict()

    col_types: Dict[str, str] = {}
    for c in df.columns:
        series = df[c]
        if pd.api.types.is_datetime64_any_dtype(series):
            col_types[c] = "datetime"
        elif pd.api.types.is_numeric_dtype(series):
            col_types[c] = "numeric"
        else:
            # treat as categorical if few unique values
            nunique = series.nunique(dropna=True)
            threshold = min(50, max(10, int(0.05 * len(series))))
            col_types[c] = "categorical" if nunique <= threshold else "text"

    sample_rows = df.head(10).to_dict(orient="records")

    return {
        "rows": n_rows,
        "cols": n_cols,
        "columns": list(df.columns),
        "dtypes": dtypes,
        "logical_types": col_types,
        "missing": missing,
        "sample": sample_rows,
    }


def summarize_dataset(df) -> Dict[str, Any]:
    """
    Create a quick numeric and categorical summary,
    plus a simple trend if there is at least one datetime + numeric column.

    If pandas/numpy are not available, returns an empty summary.
    """
    if pd is None or np is None:
        return {}

    summary: Dict[str, Any] = {}

    # Numeric summary
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if numeric_cols:
        desc = df[numeric_cols].describe().to_dict()
        summary["numeric_summary"] = desc

    # Categorical top values
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    if non_numeric_cols:
        top_cats: Dict[str, Dict[Any, int]] = {}
        for c in non_numeric_cols:
            vc = df[c].value_counts(dropna=True).head(5)
            top_cats[c] = vc.to_dict()
        summary["categorical_top_values"] = top_cats

    # Quick trend: first datetime + first numeric column
    dt_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    if dt_cols and numeric_cols:
        dt = dt_cols[0]
        num = numeric_cols[0]
        tmp = df[[dt, num]].dropna()
        tmp = tmp.sort_values(dt)
        if len(tmp) >= 3:
            tmp["idx"] = range(1, len(tmp) + 1)
            # Simple linear trend
            coef = np.polyfit(tmp["idx"], tmp[num], 1)[0]
            trend = "increasing" if coef > 0 else "decreasing"
            summary["quick_trend"] = f"{num} appears {trend} over time ({dt})."

    return summary
