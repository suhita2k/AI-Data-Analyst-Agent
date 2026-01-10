from datetime import datetime

from flask import render_template


def build_html_report(dataset_meta: dict, history: list[dict]) -> str:
    """
    Render an HTML report using the report.html Jinja template.

    Parameters
    ----------
    dataset_meta : dict
        Profiling/summary info about the dataset.
    history : list[dict]
        List of question/insight/chart_spec records.

    Returns
    -------
    str
        The rendered HTML as a string.
    """
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # history items look like:
    # {
    #   "question": "...",
    #   "insight": "...",
    #   "chart_spec": {...},
    #   "timestamp": 1234567890.0
    # }

    return render_template(
        "report.html",
        meta=dataset_meta,
        history=history,
        generated_at=generated_at,
    )