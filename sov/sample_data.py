"""Synthetic but internally-consistent sample data.

Lets the whole app run end-to-end without a live Databricks connection.
The generated `total_*` columns are exact sums of the per-brand counts for
each (search_term, feed_date), so SOV% behaves exactly as in production.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from .metrics import CUTOFFS

CLIENT_ID = 1001
CLIENT_BRAND = "AromaGold"

# L1 -> L2 -> [keywords]
TAXONOMY: dict[str, dict[str, list[str]]] = {
    "Coffee": {
        "Ground Coffee": ["ground coffee", "dark roast coffee", "espresso ground",
                          "french roast", "medium roast coffee", "colombian coffee"],
        "Coffee Pods": ["coffee pods", "k cups", "espresso pods", "decaf pods",
                        "compostable coffee pods", "flavored coffee pods"],
        "Whole Bean": ["whole bean coffee", "arabica beans", "espresso beans",
                       "organic whole bean coffee"],
        "Instant Coffee": ["instant coffee", "instant espresso", "decaf instant",
                          "instant latte"],
    },
    "Tea": {
        "Green Tea": ["green tea", "matcha", "green tea bags", "sencha green tea"],
        "Black Tea": ["black tea", "earl grey", "english breakfast tea", "chai tea"],
        "Herbal Tea": ["herbal tea", "chamomile tea", "peppermint tea", "rooibos tea"],
    },
    "Breakfast": {
        "Cereal": ["breakfast cereal", "granola cereal", "kids cereal", "high fiber cereal"],
        "Oatmeal": ["instant oatmeal", "steel cut oats", "overnight oats", "rolled oats"],
        "Granola": ["granola", "protein granola", "granola clusters", "low sugar granola"],
    },
}

COMPETITORS = ["BrewMaster", "BeanCo", "MorningRoast", "CafeNoir", "DailyGrind",
               "PureLeaf", "SteepWell", "CrunchCo", "OatHaus", "NutriMorn"]

CUTOFF_KEYS = list(CUTOFFS.keys())  # page_1, top_10, top_5, top_3, top_2
# How much each narrower cutoff shrinks vs. the previous one.
_SHRINK = {"top_10": (0.6, 0.95), "top_5": (0.5, 0.9),
           "top_3": (0.5, 0.9), "top_2": (0.4, 0.9)}


def _cutoff_counts(rng: np.random.Generator, page1: float) -> dict[str, float]:
    out = {"page_1": page1}
    prev = page1
    for c in ("top_10", "top_5", "top_3", "top_2"):
        lo, hi = _SHRINK[c]
        prev = round(prev * rng.uniform(lo, hi), 4)
        out[c] = prev
    return out


@lru_cache(maxsize=1)
def _build() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(42)

    # 9 weekly crawl dates ending today-ish.
    end = date(2026, 6, 6)
    dates = [end - timedelta(days=7 * i) for i in range(9)][::-1]

    # Stable per-brand strengths so trends look coherent.
    brand_strength = {CLIENT_BRAND: {"sp": 0.9, "organic": 0.7}}
    for b in COMPETITORS:
        brand_strength[b] = {"sp": rng.uniform(0.2, 0.8),
                             "organic": rng.uniform(0.2, 0.9)}

    # Stable ASIN pool per brand. The SAME product recurs across many keywords
    # (as in production) — this is what makes SKU-level optimization meaningful:
    # an ASIN accumulates a best-rank per keyword, and the laggards become the
    # optimization targets. Titles are deliberately generic / keyword-poor so the
    # "optimized title" recommendation has something to improve.
    _GENERIC = ["Classic Variety Pack", "Family Size Value Pack", "Premium Selection",
                "Everyday Essentials", "Original Blend Pack", "Signature Assortment",
                "Bulk Saver Pack", "Deluxe Gift Box"]
    # Each ASIN gets a stable `quality` in [0,1]; weaker products consistently
    # rank lower (higher rank number) and become the optimization targets, while
    # strong ones stay top-ranked (correctly excluded as "nothing to fix").
    sku_pool: dict[str, list[dict]] = {}
    for b in [CLIENT_BRAND] + COMPETITORS:
        # The focus brand has a deeper catalog (as a real account would), so the
        # report always has a healthy set of optimization candidates to show.
        n_sku = int(rng.integers(12, 15)) if b == CLIENT_BRAND else int(rng.integers(6, 9))
        pool = []
        for i in range(n_sku):
            asin = f"B0{rng.integers(10000000, 99999999)}"
            frag = _GENERIC[i % len(_GENERIC)]
            pool.append({
                "asin": asin,
                "title": f"{b} {frag}",
                "image_url": f"https://picsum.photos/seed/{abs(hash(asin)) % 9999}/200/200",
                "url": f"https://www.amazon.com/dp/{asin}",
                # Skew quality toward the low end so laggard SKUs (the ones worth
                # optimizing) are well represented in the demo data.
                "quality": float(rng.uniform(0.0, 1.0) ** 1.6),
            })
        sku_pool[b] = pool

    perf_rows: list[dict] = []
    meta_rows: list[dict] = []
    sku_rows: list[dict] = []

    profile_id = 7001
    for l1, l2map in TAXONOMY.items():
        for l2, keywords in l2map.items():
            for kw in keywords:
                # Metadata (one row per client x search_term).
                is_branded = rng.random() < 0.18
                participants = [CLIENT_BRAND] + list(
                    rng.choice(COMPETITORS, size=rng.integers(4, 8), replace=False))
                meta_rows.append({
                    "client_id": CLIENT_ID, "search_term": kw,
                    "digital_shelf_l1": l1, "digital_shelf_l2": l2,
                    "digital_shelf_l3": None, "digital_shelf_l4": None,
                    "keyword_type": "branded" if is_branded else "generic",
                    "profile_id": profile_id, "profile_name": f"{l1} US Profile",
                    "tag_type": "core", "relevant_brands": participants,
                    "intraday_frequency": 6 if rng.random() < 0.3 else None,
                    "is_intraday": 1 if rng.random() < 0.3 else 0,
                })

                kw_drift = {b: rng.uniform(0.85, 1.15) for b in participants}
                sb_brands = list(rng.choice(
                    participants, size=min(3, len(participants)), replace=False))

                for d in dates:
                    crawls = int(rng.integers(1, 3))
                    # First pass: per-brand counts.
                    brand_counts: dict[str, dict[str, float]] = {}
                    for b in participants:
                        s = brand_strength[b]
                        drift = kw_drift[b] * rng.uniform(0.9, 1.1)
                        sp_p1 = round(max(0.0, s["sp"] * drift * rng.uniform(0.0, 0.012)), 4)
                        org_p1 = round(max(0.0, s["organic"] * drift * rng.uniform(0.0, 0.014)), 4)
                        sp = _cutoff_counts(rng, sp_p1)
                        org = _cutoff_counts(rng, org_p1)
                        sb = {c: (33.0 if b in sb_brands else 0.0) for c in CUTOFF_KEYS}
                        allc = {c: round(sp[c] + org[c] + sb[c], 4) for c in CUTOFF_KEYS}
                        brand_counts[b] = {"sp": sp, "organic": org, "sb": sb, "all": allc}

                    # Totals across brands for this keyword-date.
                    totals = {t: {c: round(sum(brand_counts[b][t][c]
                                               for b in participants), 4)
                                  for c in CUTOFF_KEYS}
                              for t in ("sp", "organic", "all")}
                    total_sb_p1 = round(sum(brand_counts[b]["sb"]["page_1"]
                                            for b in participants), 4)

                    for b in participants:
                        bc = brand_counts[b]
                        row = {
                            "client_id": CLIENT_ID, "search_term": kw,
                            "feed_date": d,
                            "client_flag": "CLIENT" if b == CLIENT_BRAND else "COMPETITOR",
                            "brand": b, "no_of_crawls": crawls,
                        }
                        for t in ("sp", "organic", "all"):
                            for c in CUTOFF_KEYS:
                                row[f"{t}_{c}_count"] = bc[t][c]
                                row[f"total_{t}_{c}_count"] = totals[t][c]
                        for c in CUTOFF_KEYS:
                            row[f"sb_{c}_count"] = bc["sb"][c]
                        row["total_sb_page_1_count"] = total_sb_p1
                        perf_rows.append(row)

                # SKU mapping for the latest date (drill-down sample).
                # Each participating brand fields ONE of its pool ASINs. Rank is
                # driven by brand strength + that ASIN's stable quality + noise,
                # so weak ASINs reliably rank low across keywords (= optimizable)
                # and strong ASINs stay near the top (= nothing to fix).
                latest = dates[-1]
                scored = []
                for b in participants:
                    pool = sku_pool[str(b)]
                    prod = pool[int(rng.integers(0, len(pool)))]
                    # Listing rank is driven by the individual product's quality
                    # (a strong brand can still have weak SKUs), plus noise.
                    score = prod["quality"] + rng.uniform(0.0, 0.5)
                    scored.append((score, str(b), prod))
                scored.sort(key=lambda x: x[0], reverse=True)  # best score = rank 1
                for rank, (_score, b, prod) in enumerate(scored, start=1):
                    page = 1 if rank <= 9 else 2
                    ltype = "SPONSORED" if rng.random() < 0.3 else "ORGANIC"
                    sku_rows.append({
                        "client_id": CLIENT_ID, "search_term": kw,
                        "sku": prod["asin"],
                        "listing_rank": rank, "listing_type": ltype,
                        "listing_page": page, "crawl_hour": 6,
                        "zipcode": "10001", "zipcode_region": "Northeast",
                        "retailer_id": 4, "feed_date": latest, "brand": b,
                        "title": prod["title"],
                        "image_url": prod["image_url"],
                        "product_page_url": prod["url"],
                        "client_flag": "CLIENT" if b == CLIENT_BRAND else "COMPETITOR",
                        "brand_by_client_flag": b,
                        "overall_listing_rank": rank,
                    })
            profile_id += 1

    perf = pd.DataFrame(perf_rows)
    perf["feed_date"] = pd.to_datetime(perf["feed_date"])
    meta = pd.DataFrame(meta_rows)
    sku = pd.DataFrame(sku_rows)
    sku["feed_date"] = pd.to_datetime(sku["feed_date"])
    return {"performance": perf, "metadata": meta, "sku": sku}


def performance() -> pd.DataFrame:
    return _build()["performance"].copy()


def metadata() -> pd.DataFrame:
    return _build()["metadata"].copy()


def sku() -> pd.DataFrame:
    return _build()["sku"].copy()
