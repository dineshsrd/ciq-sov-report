"""Data access layer. Returns identical frames in sample and live mode.

Main frames:
  * accounts            : selectable brands (labeled by their own brand names)
  * keyword-brand agg   : search_term x brand (the workhorse for most reports)
  * trend               : week x brand x sov_pct
  * overview            : category (L1) x client_sov  (across all categories)
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from config import SETTINGS

from . import sample_data, transforms
from .metrics import (CATEGORY_LEVELS, denominator_col, numerator_col,
                      numerator_columns, total_columns)

_NUMERIC = numerator_columns() + total_columns() + ["no_of_crawls"]


def _to_date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return pd.to_datetime(v).date()


def _numify(df: pd.DataFrame) -> pd.DataFrame:
    """Databricks returns DECIMAL; cast count columns to float for math."""
    for c in df.columns:
        if c in _NUMERIC:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _run(sql: str, params: dict | None = None) -> pd.DataFrame:
    from .connection import run_query
    return run_query(sql, params)


import json as _json
import pathlib as _pathlib
import time as _time

_CACHE_DIR = _pathlib.Path(__file__).resolve().parent.parent / ".cache"


def _disk_cached(key: str, ttl_sec: int, producer):
    """Persist small startup lookups to disk so launches are instant and don't
    re-hit (and re-warm) the Databricks warehouse. Falls back gracefully."""
    f = _CACHE_DIR / f"{key}.json"
    try:
        if f.exists() and (_time.time() - f.stat().st_mtime) < ttl_sec:
            return _json.loads(f.read_text())
    except Exception:
        pass
    val = producer()
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        f.write_text(_json.dumps(val, default=str))
    except Exception:
        pass
    return val


import hashlib as _hashlib


def _hash(s: str) -> str:
    return _hashlib.md5(str(s).encode()).hexdigest()[:12]


# ── Category-first pickers: choose category, then brands in it ───────────
def get_l1_values() -> list[tuple[str, int]]:
    """All L1 categories (catalog-wide) -> [(value, keyword_count), ...]."""
    if SETTINGS.is_live:
        def _p():
            from . import queries
            df = _run(queries.l1_values_query())
            return [[str(v), int(k)] for v, k in zip(df["value"], df["kws"])]
        return [(v, int(k)) for v, k in _disk_cached("l1_values", 12 * 3600, _p)]
    meta = sample_data.metadata()
    vc = meta.groupby("digital_shelf_l1")["search_term"].nunique().sort_values(ascending=False)
    return [(str(v), int(k)) for v, k in vc.items() if pd.notna(v)]


def get_l2_values(l1: str) -> list[tuple[str, int]]:
    """L2 categories under a chosen L1 -> [(value, keyword_count), ...]."""
    if SETTINGS.is_live:
        def _p():
            from . import queries
            df = _run(queries.l2_values_query(), {"l1": l1})
            return [[str(v), int(k)] for v, k in zip(df["value"], df["kws"])]
        key = f"l2_{_hash(l1)}"
        return [(v, int(k)) for v, k in _disk_cached(key, 12 * 3600, _p)]
    meta = sample_data.metadata()
    sub = meta[meta["digital_shelf_l1"].astype(str) == str(l1)]
    vc = sub.groupby("digital_shelf_l2")["search_term"].nunique().sort_values(ascending=False)
    return [(str(v), int(k)) for v, k in vc.items() if pd.notna(v)]


def get_best_client_for_category(level: str, value: str) -> int | None:
    """Returns the client_id with the most keyword coverage in the given L1/L2.
    Used as the data source for category-mode reports."""
    if SETTINGS.is_live:
        def _p():
            from . import queries
            df = _run(queries.best_client_for_category_query(level), {"value": value})
            if df.empty:
                return None
            return int(df.iloc[0]["client_id"])
        key = f"bestclient_{_hash(level + '|' + value)}"
        return _disk_cached(key, 6 * 3600, _p)
    return sample_data.CLIENT_ID


def get_brands_in_category(level: str, value: str) -> list[dict]:
    """Every brand competing in the category -> [{brand, client_id, is_client}].
    Per brand we keep the most relevant account: prefer one where it is the
    account's own ('client') brand (so ad data is available), else the account
    that tracks it most. `is_client` gates the ad-incrementality section."""
    if SETTINGS.is_live:
        def _p():
            from . import queries
            df = _run(queries.brands_in_category_query(level), {"value": value})
            if df.empty:
                return []
            df = df.copy()
            df["brand_clean"] = df["brand"].astype(str).str.strip()
            df = df[df["brand_clean"].ne("")
                    & ~df["brand_clean"].map(transforms.is_junk_brand)]
            df["is_client"] = pd.to_numeric(df["is_client"], errors="coerce").fillna(0).astype(int)
            df["n"] = pd.to_numeric(df["n"], errors="coerce").fillna(0)
            df["_key"] = df["brand_clean"].str.lower()
            # prefer the account where the brand is 'client', then most activity
            df = df.sort_values(["is_client", "n"], ascending=False).drop_duplicates("_key")
            df = df.sort_values(["n"], ascending=False)
            return [{"brand": r.brand_clean, "client_id": int(r.client_id),
                     "is_client": bool(r.is_client)} for r in df.itertuples()]
        key = f"brandscat3_{_hash(level + '|' + value)}"
        return _disk_cached(key, 6 * 3600, _p)
    return [{"brand": sample_data.CLIENT_BRAND, "client_id": sample_data.CLIENT_ID,
             "is_client": True}]


# ── Accounts (no client_id exposed; labeled by brand names) ──────────────
def get_accounts() -> list[dict]:
    if SETTINGS.is_live:
        from . import queries
        df = _run(queries.accounts_query())
        out = []
        for _, r in df.iterrows():
            brands = r["brands"]
            if isinstance(brands, str):
                items = [b for b in brands.strip("[]").replace('"', "")
                         .replace("'", "").split(",")]
            elif hasattr(brands, "__iter__"):  # list / numpy array
                items = [str(b) for b in brands]
            else:
                items = [str(brands)]
            items = [b.strip() for b in items if b and str(b).strip()
                     and str(b).strip().upper() != "NULL_VALUE"]
            label = ", ".join(items) or f"Account {int(r['client_id'])}"
            out.append({"client_id": int(r["client_id"]), "label": label})
        return out
    return [{"client_id": sample_data.CLIENT_ID,
             "label": f"{sample_data.CLIENT_BRAND} (sample)"}]


def get_brands() -> list[dict]:
    """Individual client brands (one per entry) -> {brand, client_id}.

    A brand is mapped to the client_id where it is most active recently.
    """
    if SETTINGS.is_live:
        def _producer():
            from . import queries
            df = _run(queries.brands_query())
            if df.empty:
                return []
            df = df.copy()
            df["brand_clean"] = df["brand"].astype(str).str.strip()
            df = df[df["brand_clean"].ne("")
                    & df["brand_clean"].str.upper().ne("NULL_VALUE")]
            df["_key"] = df["brand_clean"].str.lower()
            df = df.sort_values("n", ascending=False).drop_duplicates("_key")
            items = [{"brand": r.brand_clean, "client_id": int(r.client_id)}
                     for r in df.itertuples()]
            return sorted(items, key=lambda x: x["brand"].lower())
        return _disk_cached("brands_live", 12 * 3600, _producer)
    return [{"brand": sample_data.CLIENT_BRAND, "client_id": sample_data.CLIENT_ID}]


def get_client_brands(client_id: int) -> list[str]:
    if SETTINGS.is_live:
        from . import queries
        df = _run(queries.client_brands_query(), {"cid": int(client_id)})
        return [str(b) for b in df["brand"].dropna().tolist()]
    return [sample_data.CLIENT_BRAND]


def get_date_bounds(client_id: int) -> tuple[dt.date, dt.date]:
    if SETTINGS.is_live:
        def _producer():
            from . import queries
            df = _run(queries.date_bounds_query(), {"cid": int(client_id)})
            return [str(_to_date(df.iloc[0]["min_d"])),
                    str(_to_date(df.iloc[0]["max_d"]))]
        res = _disk_cached(f"bounds_{client_id}", 12 * 3600, _producer)
        return _to_date(res[0]), _to_date(res[1])
    perf = sample_data.performance()
    return _to_date(perf["feed_date"].min()), _to_date(perf["feed_date"].max())


def get_category_values(level: str, client_id: int) -> list[tuple[str, int]]:
    """Returns [(category_value, keyword_count), ...] sorted by count desc."""
    if level not in CATEGORY_LEVELS:
        raise ValueError(level)
    if SETTINGS.is_live:
        def _producer():
            from . import queries
            df = _run(queries.category_values_query(level), {"cid": int(client_id)})
            return [[str(v), int(k)] for v, k in zip(df["value"], df["kws"])]
        res = _disk_cached(f"catvals_{client_id}_{level}", 12 * 3600, _producer)
        return [(str(v), int(k)) for v, k in res]
    meta = sample_data.metadata()
    sub = meta[meta["client_id"] == client_id]
    vc = sub.groupby(level)["search_term"].nunique().sort_values(ascending=False)
    return [(str(v), int(k)) for v, k in vc.items() if pd.notna(v)]


# ── Workhorse: keyword x brand aggregate ─────────────────────────────────
def get_keyword_brand_agg(client_id: int, level: str | None,
                          category_value: str | None,
                          start: dt.date, end: dt.date,
                          kw_limit: int = 500) -> pd.DataFrame:
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "s": str(start), "e": str(end),
                  "kwlimit": int(kw_limit)}
        if level and category_value is not None:
            params["catval"] = category_value
            sql = queries.keyword_brand_agg_query(level)
        else:
            sql = queries.keyword_brand_agg_query(None)
        return _numify(_run(sql, params))
    raw = _sample_raw(client_id, level, category_value, start, end)
    return _agg_kb(raw)


def get_brand_agg(client_id: int, level: str | None, category_value: str | None,
                  start: dt.date, end: dt.date) -> pd.DataFrame:
    """Brand-level FULL-category aggregate (all keywords) for the leaderboard."""
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "s": str(start), "e": str(end)}
        if level and category_value is not None:
            params["catval"] = category_value
            sql = queries.brand_agg_query(level)
        else:
            sql = queries.brand_agg_query(None)
        return _numify(_run(sql, params))
    return _agg_brand(_sample_raw(client_id, level, category_value, start, end))


def get_relevant_set_leaderboard(client_id: int, level: str,
                                 category_value: str, start: dt.date,
                                 end: dt.date, mtype: str, cutoff: str,
                                 focus_brand: str) -> pd.DataFrame:
    """Leaderboard among each keyword's relevant_brands (true competitors)."""
    if SETTINGS.is_live:
        from . import queries
        df = _run(queries.relevant_set_query(level, mtype, cutoff),
                  {"cid": int(client_id), "catval": category_value,
                   "fbrand": focus_brand, "s": str(start), "e": str(end)})
        if not df.empty:
            df["sov_pct"] = pd.to_numeric(df["sov_pct"], errors="coerce").fillna(0.0)
    else:
        df = _sample_relevant_set(client_id, level, category_value, start, end,
                                  mtype, cutoff, focus_brand)
    if df.empty:
        return df
    df = df.sort_values("sov_pct", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["is_focus"] = df["brand"].astype(str).str.strip().str.lower() == str(focus_brand).strip().lower()
    return df


def get_winning_asins(client_id: int, level: str | None,
                      category_value: str | None,
                      focus_brand: str) -> pd.DataFrame:
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "fbrand": focus_brand}
        lvl = level if (level and category_value is not None) else None
        if lvl:
            params["catval"] = category_value
        df = _run(queries.winning_asins_query(lvl), params)
        for c in ("keywords", "best_rank", "page1_hits"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        return df
    sku = sample_data.sku()
    sub = sku[(sku["client_id"] == client_id) & (sku["brand"] == focus_brand)]
    if sub.empty:
        return sub
    g = sub.groupby("sku", as_index=False).agg(
        title=("title", "max"),
        image_url=("image_url", "max"),
        product_page_url=("product_page_url", "max"),
        keywords=("search_term", "nunique"),
        best_rank=("overall_listing_rank", "min"),
        page1_hits=("listing_page", lambda s: int((s == 1).sum())))
    return g.sort_values(["page1_hits", "best_rank"],
                         ascending=[False, True]).reset_index(drop=True)


def get_category_leaders(client_id: int, group_level: str,
                         filter_level: str | None, category_value: str | None,
                         start: dt.date, end: dt.date, mtype: str, cutoff: str,
                         focus_brand: str) -> pd.DataFrame:
    """Per sub-category: the leading brand + the focus brand's SOV."""
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "s": str(start), "e": str(end),
                  "fbrand": focus_brand}
        if filter_level and category_value is not None:
            params["catval"] = category_value
            sql = queries.category_leaders_query(group_level, filter_level, mtype, cutoff)
        else:
            sql = queries.category_leaders_query(group_level, None, mtype, cutoff)
        df = _run(sql, params)
        for c in ("leader_sov", "focus_sov", "crawls", "kws"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        return df
    return _sample_category_leaders(client_id, group_level, filter_level,
                                    category_value, start, end, mtype, cutoff,
                                    focus_brand)


def get_incrementality(client_id: int, level: str | None, value: str | None,
                       start: dt.date, end: dt.date) -> dict | None:
    """Ad incrementality & efficiency from aramus_ds.search_incrementality_report.
    Returns None if the client has no rows (graceful — section is omitted)."""
    if not SETTINGS.is_live:
        return None
    from . import queries
    params = {"cid": int(client_id), "s": str(start), "e": str(end)}
    if level and value is not None:
        params["value"] = value
        lvl = level
    else:
        lvl = None
    try:
        summ = _run(queries.incr_summary_query(lvl), params)
        if summ.empty:
            return None
        s = {k: (float(v) if v is not None else 0.0)
             for k, v in summ.iloc[0].items()}
        if not s.get("spend"):
            return None
        s["roas"] = s["sales"] / s["spend"] if s["spend"] else 0.0
        s["iroas"] = s["inc_sales"] / s["spend"] if s["spend"] else 0.0
        s["inc_frac"] = s["inc_sales"] / s["sales"] if s.get("sales") else 0.0
        kw = _run(queries.incr_keywords_query(lvl), params)
        for c in ("paid_sov", "spend", "sales", "inc_sales"):
            if c in kw.columns:
                kw[c] = pd.to_numeric(kw[c], errors="coerce").fillna(0.0)
        kw["roas"] = kw["sales"] / kw["spend"].replace(0, pd.NA)
        kw["iroas"] = kw["inc_sales"] / kw["spend"].replace(0, pd.NA)
        kw = kw.fillna(0.0)
        bands = _run(queries.incr_bands_query(lvl), params)
        for c in ("spend", "kws"):
            if c in bands.columns:
                bands[c] = pd.to_numeric(bands[c], errors="coerce").fillna(0.0)
        return {"summary": s, "keywords": kw, "bands": bands}
    except Exception:
        return None


def get_trend(client_id: int, level: str | None, category_value: str | None,
              start: dt.date, end: dt.date, mtype: str, cutoff: str,
              brands: list[str] | None = None) -> pd.DataFrame:
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "s": str(start), "e": str(end)}
        lvl = level if (level and category_value is not None) else None
        if lvl:
            params["catval"] = category_value
        df = _run(queries.trend_query(lvl, mtype, cutoff), params)
        if df.empty:
            return df
        df["period"] = pd.to_datetime(df["period"])
        df["sov_pct"] = pd.to_numeric(df["sov_pct"], errors="coerce").fillna(0.0)
        df["is_client"] = df["is_client"].astype(bool)
        if brands is not None:
            df = df[df["brand"].isin(brands)]
        return df.sort_values(["period", "sov_pct"], ascending=[True, False])
    raw = _sample_raw(client_id, level, category_value, start, end)
    return transforms.sov_trend(raw, mtype, cutoff, brands=brands, freq="W")


def get_overview(client_id: int, level: str, start: dt.date, end: dt.date,
                 mtype: str, cutoff: str, focus_brand: str) -> pd.DataFrame:
    if SETTINGS.is_live:
        from . import queries
        df = _run(queries.overview_query(level, mtype, cutoff),
                  {"cid": int(client_id), "s": str(start), "e": str(end),
                   "fbrand": focus_brand})
        if not df.empty:
            df["client_sov"] = pd.to_numeric(df["client_sov"], errors="coerce").fillna(0.0)
            df["crawls"] = pd.to_numeric(df["crawls"], errors="coerce").fillna(0.0)
            df["keywords"] = pd.to_numeric(df["keywords"], errors="coerce").fillna(0).astype(int)
        return df
    return _sample_overview(client_id, level, start, end, mtype, cutoff, focus_brand)


def get_sku_detail(client_id: int, search_term: str) -> pd.DataFrame:
    if SETTINGS.is_live:
        from . import queries
        return _run(queries.sku_query(),
                    {"cid": int(client_id), "search_term": search_term})
    sku = sample_data.sku()
    out = sku[(sku["client_id"] == client_id) & (sku["search_term"] == search_term)]
    return out.reset_index(drop=True)


def _as_list(v) -> list:
    """Normalise a Databricks array cell (list / numpy / JSON-string) to a list."""
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = _json.loads(v)
        except Exception:
            return []
    try:
        return list(v)
    except TypeError:
        return []


def _zip_kw_ranked(kw_list, rank_list) -> list[dict]:
    """Pair the parallel keyword / rank arrays into [{'term','rank'}], sorted
    best-rank-first, capped at 10. Tolerant of length mismatch."""
    kws, rks = _as_list(kw_list), _as_list(rank_list)
    out = []
    for i, term in enumerate(kws):
        if term is None:
            continue
        try:
            rank = float(rks[i]) if i < len(rks) and rks[i] is not None else 0.0
        except (TypeError, ValueError):
            rank = 0.0
        out.append({"term": str(term), "rank": rank})
    out.sort(key=lambda x: x["rank"])
    return out[:10]


def get_optimizable_skus(client_id: int, level: str | None,
                         category_value: str | None,
                         focus_brand: str) -> pd.DataFrame:
    """Focus-brand SKUs with the most ranking upside (appear but rank low).
    Adds a 'kw_ranked' column: [{'term','rank'}] sorted best-rank-first."""
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "fbrand": focus_brand}
        lvl = level if (level and category_value is not None) else None
        if lvl:
            params["catval"] = category_value
        df = _run(queries.optimizable_skus_query(lvl), params)
        if df.empty:
            return df
        for c in ("keywords", "best_rank", "page1_kws"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        if "avg_rank" in df.columns:
            df["avg_rank"] = pd.to_numeric(df["avg_rank"], errors="coerce").fillna(0.0)
        # Build kw_ranked = [{term, rank}] sorted best-rank-first from the two
        # parallel collect_list arrays. Inlined (no module-level helper) so a
        # partial Streamlit hot-reload can never leave this referencing an
        # undefined name.
        import json as _j

        def _norm(v):
            if v is None:
                return []
            if isinstance(v, str):
                try:
                    v = _j.loads(v)
                except Exception:
                    return []
            try:
                return list(v)
            except TypeError:
                return []

        def _pair(kw_list, rank_list):
            kws, rks = _norm(kw_list), _norm(rank_list)
            out = []
            for i, term in enumerate(kws):
                if term is None:
                    continue
                try:
                    rank = float(rks[i]) if i < len(rks) and rks[i] is not None else 0.0
                except (TypeError, ValueError):
                    rank = 0.0
                out.append({"term": str(term), "rank": rank})
            out.sort(key=lambda x: x["rank"])
            return out[:10]

        df["kw_ranked"] = [
            _pair(kw, rk)
            for kw, rk in zip(df.get("kw_list", [None] * len(df)),
                              df.get("rank_list", [None] * len(df)))
        ]
        return df.drop(columns=[c for c in ("kw_list", "rank_list")
                                if c in df.columns]).reset_index(drop=True)
    return _sample_optimizable_skus(client_id, level, category_value, focus_brand)


def _sample_optimizable_skus(client_id, level, category_value,
                             focus_brand) -> pd.DataFrame:
    """Sample-mode equivalent: per-SKU best rank per keyword, keep the laggards."""
    sku = sample_data.sku()
    sub = sku[(sku["client_id"] == client_id) & (sku["brand"] == focus_brand)]
    if category_value is not None and level is not None:
        meta = sample_data.metadata()
        kws = set(meta[meta[level].astype(str) == str(category_value)]["search_term"])
        sub = sub[sub["search_term"].isin(kws)]
    if sub.empty:
        return pd.DataFrame(columns=["sku", "title", "image_url",
                                     "product_page_url", "keywords", "avg_rank",
                                     "best_rank", "page1_kws", "kw_ranked"])
    rows = []
    for skuid, g in sub.groupby("sku"):
        kw = g.groupby("search_term").agg(
            best_rank=("overall_listing_rank", "min"),
            on_p1=("listing_page", lambda s: int((s == 1).any())))
        if len(kw) < 1 or kw["best_rank"].mean() <= 3:
            continue
        kw_ranked = [{"term": t, "rank": float(r)} for t, r in
                     kw["best_rank"].sort_values().head(10).items()]
        rows.append({
            "sku": skuid, "title": str(g["title"].iloc[0]),
            "image_url": str(g["image_url"].iloc[0]),
            "product_page_url": str(g["product_page_url"].iloc[0]),
            "keywords": int(len(kw)), "avg_rank": round(float(kw["best_rank"].mean()), 1),
            "best_rank": int(kw["best_rank"].min()),
            "page1_kws": int(kw["on_p1"].sum()), "kw_ranked": kw_ranked})
    if not rows:
        return pd.DataFrame(columns=["sku", "title", "image_url",
                                     "product_page_url", "keywords", "avg_rank",
                                     "best_rank", "page1_kws", "kw_ranked"])
    df = pd.DataFrame(rows)
    df["_opp"] = df["keywords"] * df["avg_rank"]
    return (df.sort_values("_opp", ascending=False).drop(columns="_opp")
            .head(6).reset_index(drop=True))


def get_sku_keywords(client_id: int, sku: str) -> pd.DataFrame:
    """Keywords where this ASIN ranks on page 1 — for listing optimization."""
    if SETTINGS.is_live:
        from . import queries
        df = _run(queries.sku_keywords_query(),
                  {"cid": int(client_id), "sku": sku})
        for c in ("best_rank", "page1_hits", "days_tracked"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        return df.sort_values("page1_hits", ascending=False).reset_index(drop=True)
    return pd.DataFrame(columns=["search_term", "best_rank", "page1_hits", "days_tracked"])


def get_competitor_titles(client_id: int, sku: str) -> pd.DataFrame:
    """Top competitor ASIN titles on the same keywords as the focus SKU."""
    if SETTINGS.is_live:
        from . import queries
        df = _run(queries.competitor_titles_query(),
                  {"cid": int(client_id), "sku": sku})
        for c in ("kw_count", "avg_rank"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        return df
    return pd.DataFrame(columns=["sku", "title", "brand", "kw_count", "avg_rank"])


def get_region_share(client_id: int, level: str | None,
                     category_value: str | None,
                     focus_brand: str) -> pd.DataFrame:
    if SETTINGS.is_live:
        from . import queries
        params = {"cid": int(client_id), "fbrand": focus_brand}
        lvl = level if (level and category_value is not None) else None
        if lvl:
            params["catval"] = category_value
        df = _run(queries.region_share_query(lvl), params)
        for c in ("client_listings", "total_listings"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        if not df.empty:
            df["share"] = 100.0 * df["client_listings"] / df["total_listings"].replace(0, pd.NA)
            df["share"] = df["share"].fillna(0.0)
        return df
    sku = sample_data.sku()
    sub = sku[sku["client_id"] == client_id]
    g = sub.assign(is_c=sub["brand"].astype(str) == str(focus_brand)).groupby("zipcode_region")
    df = g.agg(client_listings=("is_c", "sum"), total_listings=("sku", "count")).reset_index()
    df = df.rename(columns={"zipcode_region": "region"})
    df["share"] = 100.0 * df["client_listings"] / df["total_listings"].replace(0, pd.NA)
    return df.fillna(0.0)


# ── Sample helpers ───────────────────────────────────────────────────────
def _sample_raw(client_id, level, category_value, start, end) -> pd.DataFrame:
    perf = sample_data.performance()
    meta = sample_data.metadata()
    cat_cols = [c for c in CATEGORY_LEVELS if c in meta.columns] + ["keyword_type"]
    df = perf.merge(meta[["client_id", "search_term"] + cat_cols],
                    on=["client_id", "search_term"], how="left")
    df = df[df["client_id"] == client_id]
    if start is not None:
        df = df[df["feed_date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["feed_date"] <= pd.Timestamp(end)]
    if level and category_value is not None:
        df = df[df[level].astype(str) == str(category_value)]
    df["client_flag"] = df["client_flag"].astype(str).str.lower()
    return df.reset_index(drop=True)


def _agg_kb(raw: pd.DataFrame) -> pd.DataFrame:
    nums, tots = numerator_columns(), total_columns()
    if raw.empty:
        return raw
    kb = raw.groupby(["search_term", "brand"], as_index=False).agg(
        {**{c: "sum" for c in nums},
         "client_flag": "first", "keyword_type": "first"})
    kd = raw.groupby(["search_term", "feed_date"], as_index=False)[tots + ["no_of_crawls"]].max()
    kt = kd.groupby("search_term", as_index=False)[tots + ["no_of_crawls"]].sum()
    return kb.merge(kt, on="search_term", how="left")


def _agg_brand(raw: pd.DataFrame) -> pd.DataFrame:
    """Brand-level full-category aggregate (sample mode)."""
    nums, tots = numerator_columns(), total_columns()
    if raw.empty:
        return raw
    ba = raw.groupby("brand", as_index=False).agg(
        {**{c: "sum" for c in nums}, "client_flag": "first"})
    kd = raw.groupby(["search_term", "feed_date"], as_index=False)[tots + ["no_of_crawls"]].max()
    tot = kd[tots + ["no_of_crawls"]].sum()
    for c in tots + ["no_of_crawls"]:
        ba[c] = float(tot[c])
    return ba


def _sample_relevant_set(cid, level, catval, start, end, mtype, cutoff,
                         focus_brand) -> pd.DataFrame:
    raw = _sample_raw(cid, level, catval, start, end)
    if raw.empty:
        return raw
    meta = sample_data.metadata()
    num = numerator_col(mtype, cutoff)
    rel: dict[str, set] = {}
    for _, r in meta[meta["client_id"] == cid].iterrows():
        rb = r["relevant_brands"]
        s = set(map(str, rb)) if (hasattr(rb, "__iter__") and not isinstance(rb, str)) else set()
        s.add(str(focus_brand))
        rel[r["search_term"]] = s
    mask = raw.apply(lambda x: str(x["brand"]) in rel.get(x["search_term"],
                                                          {str(focus_brand)}), axis=1)
    sub = raw[mask]
    base = float(sub[num].sum())
    g = sub.groupby("brand", as_index=False)[num].sum().rename(columns={num: "n"})
    g["sov_pct"] = (100.0 * g["n"] / base) if base else 0.0
    return g


def _sample_category_leaders(cid, group_level, filter_level, catval, start, end,
                             mtype, cutoff, focus_brand) -> pd.DataFrame:
    raw = (_sample_raw(cid, filter_level, catval, start, end) if filter_level
           else _sample_raw(cid, None, None, start, end))
    num, den = numerator_col(mtype, cutoff), denominator_col(mtype, cutoff)
    rows = []
    for grp, sub in raw.groupby(group_level, dropna=False):
        if pd.isna(grp):
            continue
        base = transforms._dedup_sum(sub, den)
        bg = sub.groupby("brand")[num].sum()
        if bg.empty or base == 0:
            continue
        rows.append({
            "category": str(grp), "leader": str(bg.idxmax()),
            "leader_sov": float(100 * bg.max() / base),
            "focus_sov": float(100 * sub[sub["brand"] == focus_brand][num].sum() / base),
            "crawls": transforms._dedup_sum(sub, "no_of_crawls"),
            "kws": int(sub["search_term"].nunique())})
    return pd.DataFrame(rows).sort_values("crawls", ascending=False).reset_index(drop=True)


def _sample_overview(client_id, level, start, end, mtype, cutoff,
                     focus_brand) -> pd.DataFrame:
    raw = _sample_raw(client_id, None, None, start, end)
    num, den = numerator_col(mtype, cutoff), denominator_col(mtype, cutoff)
    rows = []
    for cat, sub in raw.groupby(level, dropna=False):
        if pd.isna(cat):
            continue
        base = transforms._dedup_sum(sub, den)
        cl = sub[sub["brand"].astype(str) == str(focus_brand)]
        rows.append({"category": str(cat),
                     "client_sov": float(100 * cl[num].sum() / base) if base else 0.0,
                     "crawls": transforms._dedup_sum(sub, "no_of_crawls"),
                     "keywords": int(sub["search_term"].nunique())})
    return pd.DataFrame(rows).sort_values("crawls", ascending=False).reset_index(drop=True)
