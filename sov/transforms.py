"""SOV aggregations.

Works on either grain:
  * raw          : search_term x feed_date x brand  (sample mode / drill-downs)
  * keyword-brand: search_term x brand              (SQL pre-aggregated, live)

THE KEY RULE
------------
`total_*` columns are an all-brands total repeated on every brand row of a
keyword (and date). The numerator (a brand's own count) sums freely, but the
denominator must be de-duplicated to one value per keyword(+date) before
summing across keywords — else it inflates by the number of brands and SOV%
collapses. `_dedup_sum` / `_per_keyword` enforce this for both grains.
"""
from __future__ import annotations

import pandas as pd

from .metrics import (CUTOFFS, METRIC_TYPES, denominator_col, numerator_col)


def _keys(df: pd.DataFrame) -> list[str]:
    return [k for k in ("search_term", "feed_date") if k in df.columns]


JUNK_BRANDS = {"generic", "unbranded", "null_value", "n/a", "na", "none",
               "other", "others", "misc", "unknown", "unknown_brand", ""}


def is_junk_brand(name) -> bool:
    return str(name).strip().lower() in JUNK_BRANDS


def _is_client(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().eq("client")


def _client_any(series: pd.Series) -> bool:
    return bool(_is_client(series).any())


def _focus_mask(df: pd.DataFrame, focus_brand: str | None) -> pd.Series:
    """Row mask for the brand we report on: the selected brand if given,
    else any brand flagged 'client'. Case-insensitive (brand casing varies)."""
    if focus_brand is not None:
        return df["brand"].astype(str).str.strip().str.lower() == str(focus_brand).strip().lower()
    return _is_client(df["client_flag"])


def _dedup_sum(df: pd.DataFrame, col: str) -> float:
    """Sum a per-keyword(+date) value once, despite brand-row repetition.

    For the brand-level frame (no search_term/feed_date) the total column is a
    single category-level value repeated on every brand row, so we take it once.
    """
    if df.empty or col not in df.columns:
        return 0.0
    keys = _keys(df)
    if not keys:
        return float(pd.to_numeric(df[col], errors="coerce").max())
    return float(df.groupby(keys, dropna=False)[col].max().sum())


def _per_keyword(df: pd.DataFrame, col: str, agg: str = "max") -> pd.Series:
    """A per-keyword series (de-duplicated across brands, summed over dates)."""
    keys = _keys(df)
    s = df.groupby(keys, dropna=False)[col].agg(agg)
    if "feed_date" in keys:  # collapse the date dimension
        s = s.groupby("search_term").sum()
    return s


# ── Brand leaderboard ────────────────────────────────────────────────────
def brand_leaderboard(df: pd.DataFrame, mtype: str = "all",
                      cutoff: str = "page_1",
                      focus_brand: str | None = None) -> pd.DataFrame:
    cols = ["brand", "is_client", "count", "sov_pct", "rank"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    num = numerator_col(mtype, cutoff)
    base = _dedup_sum(df, denominator_col(mtype, cutoff))
    g = df.groupby("brand", dropna=False).agg(
        count=(num, "sum"),
        is_client=("client_flag", _client_any)).reset_index()
    if focus_brand is not None:  # highlight the selected brand specifically
        g["is_client"] = g["brand"].astype(str).str.strip().str.lower() == str(focus_brand).strip().lower()
    g["sov_pct"] = (100.0 * g["count"] / base) if base else 0.0
    g = g.sort_values("sov_pct", ascending=False).reset_index(drop=True)
    g["rank"] = g.index + 1
    return g[cols]


# ── Top keywords (volume / opportunity) ──────────────────────────────────
def top_keywords(df: pd.DataFrame, n: int = 10, mtype: str = "all",
                 cutoff: str = "page_1", rank_by: str = "crawls",
                 focus_brand: str | None = None) -> pd.DataFrame:
    cols = ["search_term", "crawls", "intensity", "client_count",
            "client_sov", "opportunity"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    num = numerator_col(mtype, cutoff)
    crawls = _per_keyword(df, "no_of_crawls", "max")
    intensity = _per_keyword(df, denominator_col(mtype, cutoff), "max")
    client_cnt = df[_focus_mask(df, focus_brand)].groupby("search_term")[num].sum()
    kw = pd.DataFrame({"crawls": crawls, "intensity": intensity,
                       "client_count": client_cnt}).fillna(0.0)
    kw["client_sov"] = 100.0 * kw["client_count"] / kw["intensity"].replace(0, pd.NA)
    kw["client_sov"] = kw["client_sov"].fillna(0.0)
    kw["opportunity"] = kw["intensity"] * (1.0 - kw["client_sov"] / 100.0)
    kw = kw.reset_index()
    sort_col = rank_by if rank_by in {"crawls", "intensity", "client_sov",
                                      "opportunity"} else "crawls"
    return kw.sort_values(sort_col, ascending=False).head(n).reset_index(drop=True)[cols]


# ── Low-SOV keywords — missed & underperforming opportunities ──────────────
def zero_sov_keywords(df: pd.DataFrame, n: int = 200, mtype: str = "all",
                      cutoff: str = "page_1",
                      focus_brand: str | None = None,
                      sov_threshold: float = 2.0) -> pd.DataFrame:
    """Keywords where the focus brand has less than ``sov_threshold``% SOV
    (default 2 %), ranked by crawl volume.

    Returns up to ``n`` candidates — the caller is expected to enrich with
    real search volume, filter to volume > 0, and cap to a display limit.
    ``client_sov`` is included in the output so the caller can build a
    combined ranking or display it alongside volume.
    """
    cols = ["search_term", "crawls", "intensity", "client_sov"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    num = numerator_col(mtype, cutoff)
    den = denominator_col(mtype, cutoff)
    crawls = _per_keyword(df, "no_of_crawls", "max")
    intensity = _per_keyword(df, den, "max")
    client_cnt = df[_focus_mask(df, focus_brand)].groupby("search_term")[num].sum()
    kw = pd.DataFrame({"crawls": crawls, "intensity": intensity,
                       "client_count": client_cnt}).fillna(0.0)
    kw["client_sov"] = (100.0 * kw["client_count"]
                        / kw["intensity"].replace(0, float("nan"))).fillna(0.0)
    kw = kw[kw["client_sov"] < sov_threshold].reset_index()
    return (kw.sort_values("crawls", ascending=False)
              .head(n)
              .reset_index(drop=True)[cols])


# ── Keyword positioning (where the brand ranks per keyword) ──────────────
def keyword_positioning(df: pd.DataFrame, n: int = 15, mtype: str = "all",
                        cutoff: str = "page_1",
                        focus_brand: str | None = None) -> pd.DataFrame:
    cols = ["search_term", "crawls", "client_sov", "client_rank",
            "leader", "leader_sov", "brands"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    num = numerator_col(mtype, cutoff)
    per = df.groupby(["search_term", "brand"], dropna=False).agg(
        cnt=(num, "sum"),
        is_client=("client_flag", _client_any)).reset_index()
    if focus_brand is not None:
        per["is_client"] = per["brand"].astype(str).str.strip().str.lower() == str(focus_brand).strip().lower()
    base = _per_keyword(df, denominator_col(mtype, cutoff), "max").rename("base")
    per = per.merge(base, on="search_term", how="left")
    per["sov"] = 100.0 * per["cnt"] / per["base"].replace(0, pd.NA)
    per["sov"] = per["sov"].fillna(0.0)
    per["rank"] = per.groupby("search_term")["cnt"].rank(ascending=False, method="min")

    crawls = _per_keyword(df, "no_of_crawls", "max")
    leaders = (per.sort_values("cnt", ascending=False)
               .groupby("search_term").first()[["brand", "sov"]]
               .rename(columns={"brand": "leader", "sov": "leader_sov"}))
    nbrands = per.groupby("search_term")["brand"].nunique().rename("brands")
    client = per[per["is_client"]].groupby("search_term").agg(
        client_sov=("sov", "sum"), client_rank=("rank", "min"))

    out = (pd.DataFrame({"crawls": crawls}).join([leaders, nbrands, client])
           .reset_index())
    out["client_sov"] = out["client_sov"].fillna(0.0)
    out["client_rank"] = out["client_rank"]  # NaN if brand absent
    return out.sort_values("crawls", ascending=False).head(n).reset_index(drop=True)[cols]


# ── Incrementality (paid lift = combined - organic) ──────────────────────
def incrementality(df: pd.DataFrame, n: int = 15, cutoff: str = "page_1",
                   focus_brand: str | None = None) -> pd.DataFrame:
    cols = ["search_term", "crawls", "organic_sov", "combined_sov",
            "incremental_sov", "paid_share", "classification"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    o_num, o_den = numerator_col("organic", cutoff), denominator_col("organic", cutoff)
    c_num, c_den = numerator_col("all", cutoff), denominator_col("all", cutoff)
    cl = df[_focus_mask(df, focus_brand)]
    org = 100.0 * cl.groupby("search_term")[o_num].sum() / _per_keyword(df, o_den, "max")
    comb = 100.0 * cl.groupby("search_term")[c_num].sum() / _per_keyword(df, c_den, "max")
    crawls = _per_keyword(df, "no_of_crawls", "max")
    out = pd.DataFrame({"crawls": crawls, "organic_sov": org,
                        "combined_sov": comb}).fillna(0.0).reset_index()
    out["incremental_sov"] = (out["combined_sov"] - out["organic_sov"]).clip(lower=0)
    out["paid_share"] = (out["incremental_sov"]
                         / out["combined_sov"].replace(0, pd.NA)).fillna(0.0)
    out["classification"] = out.apply(_classify_increment, axis=1)
    return out.sort_values("crawls", ascending=False).head(n).reset_index(drop=True)[cols]


def _classify_increment(r) -> str:
    if r["combined_sov"] < 2:
        return "Absent"
    if r["paid_share"] >= 0.6:
        return "Paid-dependent"
    if r["paid_share"] <= 0.15:
        return "Organic-led"
    return "Balanced"


def classify_incr(organic_sov: float, paid_sov: float,
                  combined_sov: float) -> str:
    """Classify a keyword or category by its organic vs paid balance.
    Used by the SOV-based incrementality report."""
    if combined_sov < 0.5:
        return "Dark Spot"
    paid_frac = paid_sov / combined_sov if combined_sov > 0 else 0
    if paid_frac >= 0.65:
        return "Paid-dependent"
    if paid_frac <= 0.15:
        return "Organic-led"
    if organic_sov >= 2.5 and paid_sov >= 1.5:
        return "Cannibalizing"
    return "Balanced"


# ── SOV trend over time (raw grain only) ─────────────────────────────────
def _period(s: pd.Series, freq: str) -> pd.Series:
    s = pd.to_datetime(s)
    return s.dt.to_period("W").dt.start_time if freq == "W" else s.dt.normalize()


def sov_trend(df: pd.DataFrame, mtype: str = "all", cutoff: str = "page_1",
              brands: list[str] | None = None, freq: str = "W") -> pd.DataFrame:
    cols = ["period", "brand", "is_client", "sov_pct"]
    if df.empty or "feed_date" not in df.columns:
        return pd.DataFrame(columns=cols)
    num, den = numerator_col(mtype, cutoff), denominator_col(mtype, cutoff)
    d = df.copy()
    d["_p"] = _period(d["feed_date"], freq)
    base = (d.groupby(["_p", "search_term"], dropna=False)[den].max()
            .groupby("_p").sum().rename("base"))
    nums = d.groupby(["_p", "brand"], dropna=False)[num].sum().reset_index()
    nums = nums.merge(base.reset_index(), on="_p", how="left")
    nums["sov_pct"] = (100.0 * nums[num] / nums["base"].replace(0, pd.NA)).fillna(0.0)
    cmap = d.groupby("brand")["client_flag"].apply(_client_any)
    nums["is_client"] = nums["brand"].map(cmap).fillna(False)
    nums = nums.rename(columns={"_p": "period"})
    if brands is not None:
        nums = nums[nums["brand"].isin(brands)]
    return nums[cols].sort_values(["period", "sov_pct"], ascending=[True, False])


# ── Win/loss from a trend frame (first period vs last) ───────────────────
def win_loss(trend: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["brand", "is_client", "start_sov", "end_sov", "delta"]
    if trend.empty:
        return pd.DataFrame(columns=cols)
    periods = sorted(trend["period"].unique())
    if len(periods) < 2:
        return pd.DataFrame(columns=cols)
    first, last = periods[0], periods[-1]
    a = trend[trend["period"] == first].set_index("brand")["sov_pct"]
    b = trend[trend["period"] == last].set_index("brand")["sov_pct"]
    cmap = trend.groupby("brand")["is_client"].any()
    out = pd.DataFrame({"start_sov": a, "end_sov": b}).fillna(0.0)
    out["delta"] = out["end_sov"] - out["start_sov"]
    out["is_client"] = out.index.map(cmap).fillna(False)
    out = out.reset_index().rename(columns={"index": "brand"})
    out = out.reindex(out["delta"].abs().sort_values(ascending=False).index)
    return out.head(n).reset_index(drop=True)[cols]


# ── Channel mix / position funnel / branded-generic ──────────────────────
def channel_mix(df: pd.DataFrame, cutoff: str = "page_1",
                focus_brand: str | None = None) -> pd.DataFrame:
    rows = []
    for t in ("sp", "organic", "sb", "all"):
        lb = brand_leaderboard(df, t, cutoff, focus_brand)
        rows.append({"type": t, "channel": METRIC_TYPES[t],
                     "sov_pct": float(lb[lb["is_client"]]["sov_pct"].sum())})
    return pd.DataFrame(rows)


def combined_leaderboard(df: pd.DataFrame, cutoff: str = "page_1",
                         focus_brand: str | None = None,
                         top: int = 15) -> pd.DataFrame:
    """THE single SOV leaderboard. One number per brand = Combined Share of
    Voice = brand's `all_*` weight / `total_all_*` (vs every brand), decomposed
    into organic and paid POINTS on the SAME denominator, so
    organic_pts + paid_pts == combined_sov. Ranked by combined_sov."""
    cols = ["brand", "combined_sov", "organic_pts", "paid_pts", "is_client", "rank"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    a_num = numerator_col("all", cutoff)
    base = _dedup_sum(df, denominator_col("all", cutoff))  # total_all (all brands)
    o_num = numerator_col("organic", cutoff)
    sp_num, sb_num = numerator_col("sp", cutoff), numerator_col("sb", cutoff)
    g = df.groupby("brand", dropna=False).agg(
        a=(a_num, "sum"), o=(o_num, "sum"), sp=(sp_num, "sum"), sb=(sb_num, "sum"),
        is_client=("client_flag", _client_any)).reset_index()
    if focus_brand is not None:
        g["is_client"] = g["brand"].astype(str).str.strip().str.lower() == str(focus_brand).strip().lower()
    g["combined_sov"] = (100.0 * g["a"] / base) if base else 0.0
    g["organic_pts"] = (100.0 * g["o"] / base) if base else 0.0
    g["paid_pts"] = (100.0 * (g["sp"] + g["sb"]) / base) if base else 0.0
    # drop unbranded/junk rows, but never the focus brand
    junk = g["brand"].map(is_junk_brand) & ~g["is_client"]
    g = g[~junk]
    g = g.sort_values("combined_sov", ascending=False).reset_index(drop=True)
    g["rank"] = g.index + 1
    return g.head(top)[cols]


def organic_paid_leaderboard(df: pd.DataFrame, cutoff: str = "page_1",
                             focus_brand: str | None = None,
                             top: int = 15) -> pd.DataFrame:
    """Per-brand Organic SOV vs Paid SOV (Paid = SP + SB) — the share-of-search
    centerpiece. Each column independently sums to ~100% across brands."""
    cols = ["brand", "organic_sov", "paid_sov", "is_client", "rank"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    o_num, o_den = numerator_col("organic", cutoff), denominator_col("organic", cutoff)
    sp_num, sp_den = numerator_col("sp", cutoff), denominator_col("sp", cutoff)
    sb_num, sb_den = numerator_col("sb", cutoff), denominator_col("sb", cutoff)
    o_base = _dedup_sum(df, o_den)
    paid_base = _dedup_sum(df, sp_den) + _dedup_sum(df, sb_den)
    g = df.groupby("brand", dropna=False).agg(
        o=(o_num, "sum"), sp=(sp_num, "sum"), sb=(sb_num, "sum"),
        is_client=("client_flag", _client_any)).reset_index()
    if focus_brand is not None:
        g["is_client"] = g["brand"].astype(str).str.strip().str.lower() == str(focus_brand).strip().lower()
    g["organic_sov"] = (100.0 * g["o"] / o_base) if o_base else 0.0
    g["paid_sov"] = (100.0 * (g["sp"] + g["sb"]) / paid_base) if paid_base else 0.0
    g["_blend"] = g["organic_sov"] + g["paid_sov"]
    g = g.sort_values("_blend", ascending=False).reset_index(drop=True)
    g["rank"] = g.index + 1
    return g.head(top)[cols]


def coverage(df: pd.DataFrame, mtype: str = "all", cutoff: str = "page_1",
             focus_brand: str | None = None) -> dict:
    """How many of the category's keywords the focus brand appears in at all."""
    if df.empty:
        return {"present": 0, "total": 0, "pct": 0.0}
    num = numerator_col(mtype, cutoff)
    total = int(df["search_term"].nunique())
    pres = df[_focus_mask(df, focus_brand) & (df[num] > 0)]["search_term"].nunique()
    return {"present": int(pres), "total": total,
            "pct": float(100.0 * pres / total) if total else 0.0}


def position_funnel(df: pd.DataFrame, mtype: str = "all",
                    focus_brand: str | None = None) -> pd.DataFrame:
    rows = []
    for c, label in CUTOFFS.items():
        lb = brand_leaderboard(df, mtype, c, focus_brand)
        rows.append({"cutoff": c, "label": label,
                     "sov_pct": float(lb[lb["is_client"]]["sov_pct"].sum())})
    return pd.DataFrame(rows)


def branded_vs_generic(df: pd.DataFrame, mtype: str = "all",
                       cutoff: str = "page_1",
                       focus_brand: str | None = None) -> pd.DataFrame:
    cols = ["kw_class", "client_sov", "keywords"]
    if df.empty or "keyword_type" not in df.columns:
        return pd.DataFrame(columns=cols)
    d = df.copy()
    branded = d["keyword_type"].astype(str).str.lower().str.contains("brand")
    d["kw_class"] = branded.map({True: "Branded", False: "Generic"})
    rows = []
    for cls, sub in d.groupby("kw_class", dropna=False):
        lb = brand_leaderboard(sub, mtype, cutoff, focus_brand)
        rows.append({"kw_class": cls,
                     "client_sov": float(lb[lb["is_client"]]["sov_pct"].sum()),
                     "keywords": int(sub["search_term"].nunique())})
    return pd.DataFrame(rows)


# ── Headline KPIs ────────────────────────────────────────────────────────
def kpi_summary(df: pd.DataFrame, mtype: str = "all", cutoff: str = "page_1",
                focus_brand: str | None = None) -> dict:
    lb = brand_leaderboard(df, mtype, cutoff, focus_brand)
    has_st = "search_term" in df.columns
    out = {
        "keywords": int(df["search_term"].nunique()) if (has_st and not df.empty) else None,
        "brands": int(df["brand"].nunique()) if not df.empty else 0,
        "crawls": _dedup_sum(df, "no_of_crawls"),
        "client_sov": 0.0, "client_rank": None, "client_brand": None,
        "top_brand": None, "top_brand_sov": 0.0, "leaderboard": lb,
    }
    if not lb.empty:
        out["top_brand"] = str(lb.iloc[0]["brand"])
        out["top_brand_sov"] = float(lb.iloc[0]["sov_pct"])
        cl = lb[lb["is_client"]]
        if not cl.empty:
            out["client_brand"] = str(cl.iloc[0]["brand"])
            out["client_sov"] = float(cl["sov_pct"].sum())
            out["client_rank"] = int(cl.iloc[0]["rank"])
    return out
