"""Metric definitions and column-name helpers.

A SOV "metric" is a (type, cutoff) pair:
    type   in {sp, organic, sb, all}
    cutoff in {page_1, top_10, top_5, top_3, top_2}

For every (type, cutoff) the performance cube has:
    numerator   = f"{type}_{cutoff}_count"          (the brand's weighted count)
    denominator = f"total_{type}_{cutoff}_count"     (all-brands total = the SOV base)

Special case: Sponsored Brands (sb) appears once at the very top, so its
top_N counts equal its page_1 count, and only `total_sb_page_1_count` exists
as a denominator. We therefore map every sb cutoff to that single base.
"""
from __future__ import annotations

# Display order matters (broadest first).
METRIC_TYPES: dict[str, str] = {
    "sp": "Sponsored Products",
    "organic": "Organic",
    "sb": "Sponsored Brands",
    "all": "All (SP + Organic + SB)",
}

CUTOFFS: dict[str, str] = {
    "page_1": "Page 1",
    "top_10": "Top 10",
    "top_5": "Top 5",
    "top_3": "Top 3",
    "top_2": "Top 2",
}

# The three "headline" lenses we expose prominently in the UI.
HEADLINE_TYPES = ["sp", "organic", "all"]

CATEGORY_LEVELS = [f"digital_shelf_l{i}" for i in range(1, 11)]
CATEGORY_LABELS = {f"digital_shelf_l{i}": f"Category L{i}" for i in range(1, 11)}


def numerator_col(mtype: str, cutoff: str) -> str:
    _validate(mtype, cutoff)
    return f"{mtype}_{cutoff}_count"


def denominator_col(mtype: str, cutoff: str) -> str:
    _validate(mtype, cutoff)
    if mtype == "sb":
        # Only total_sb_page_1_count exists; sb top_N share the same base.
        return "total_sb_page_1_count"
    return f"total_{mtype}_{cutoff}_count"


def _validate(mtype: str, cutoff: str) -> None:
    if mtype not in METRIC_TYPES:
        raise ValueError(f"Unknown metric type: {mtype!r}")
    if cutoff not in CUTOFFS:
        raise ValueError(f"Unknown cutoff: {cutoff!r}")


def performance_metric_columns() -> list[str]:
    """All count columns present in the performance cube (for SELECT lists)."""
    cols: list[str] = []
    for t in ("sp", "organic", "all"):
        for c in CUTOFFS:
            cols.append(f"{t}_{c}_count")
            cols.append(f"total_{t}_{c}_count")
    for c in CUTOFFS:  # sb numerators at every cutoff
        cols.append(f"sb_{c}_count")
    cols.append("total_sb_page_1_count")  # sb single base
    return cols


def all_metric_pairs() -> list[tuple[str, str]]:
    return [(t, c) for t in METRIC_TYPES for c in CUTOFFS]


def numerator_columns() -> list[str]:
    """All brand-count (numerator) columns."""
    return [c for c in performance_metric_columns() if not c.startswith("total_")]


def total_columns() -> list[str]:
    """All all-brands (denominator/total) columns."""
    return [c for c in performance_metric_columns() if c.startswith("total_")]
