"""Share-of-Voice (SOV) analytics package.

Core pipeline (pandas + plotly only, no heavy deps at import time):
    data  ->  transforms  ->  charts  ->  report

Heavy / optional integrations (databricks, openai, playwright) are imported
lazily inside the functions that use them, so the core pipeline imports
cleanly even when those packages are absent.
"""

__all__ = [
    "metrics",
    "branding",
    "transforms",
    "charts",
    "data",
    "narrative",
    "report",
]
