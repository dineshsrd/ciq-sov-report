"""Parameterized SQL for Databricks.

Design: push the heavy SOV aggregation into SQL so result sets are small
(thousands of rows, not hundreds of thousands) and we avoid CloudFetch
throttling. The pandas layer then does final rollups/ranking.

Safety: literal values are always bound params (:name). The only interpolated
values are metric/category-level identifiers, all validated against fixed
allowlists, so there is no injection surface.
"""
from __future__ import annotations

from config import (CATALOG_COMMON, SCHEMA_ARAMUS, SETTINGS, TBL_INCR,
                    TBL_METADATA, TBL_PERFORMANCE, TBL_SKU,
                    TBL_SEARCH_VOLUME)

from .metrics import (CATEGORY_LEVELS, denominator_col, numerator_col,
                      numerator_columns, total_columns)


def _check_level(level: str) -> str:
    if level not in CATEGORY_LEVELS:
        raise ValueError(f"Illegal category level: {level!r}")
    return level


def _P() -> str:
    return SETTINGS.table(TBL_PERFORMANCE)


def _M() -> str:
    return SETTINGS.table(TBL_METADATA)


def _S() -> str:
    return SETTINGS.table(TBL_SKU)


def _meta_join(level: str | None, with_keyword_type: bool = True) -> str:
    """A metadata join that is de-duplicated to ONE row per (client_id,
    search_term). Metadata has duplicate rows (a keyword can be tagged under
    several category paths); joining raw would fan out the performance rows and
    inflate SOV past 100%. The GROUP BY collapses that. When `level` is given,
    the category filter happens *inside* the subquery (one keyword per category).
    """
    where = f"WHERE {_check_level(level)} = :catval" if level else ""
    kt = ", MAX(keyword_type) AS keyword_type" if with_keyword_type else ""
    return (f"JOIN (SELECT client_id, search_term{kt} FROM {_M()} {where} "
            f"GROUP BY client_id, search_term) m "
            f"ON p.client_id = m.client_id AND p.search_term = m.search_term")


# ── Accounts (labeled by the client's own brands; no client_id shown) ────
def accounts_query(days: int = 3) -> str:
    return f"""
SELECT client_id,
       slice(sort_array(collect_set(brand)), 1, 5) AS brands,
       COUNT(*) AS n
FROM {_P()}
WHERE feed_date >= date_sub(current_date(), {int(days)})
  AND lower(client_flag) = 'client'
GROUP BY client_id
ORDER BY n DESC
LIMIT 300
""".strip()


def client_brands_query() -> str:
    return (f"SELECT DISTINCT brand FROM {_P()} "
            f"WHERE client_id = :cid AND lower(client_flag) = 'client' LIMIT 50")


def brands_query(days: int = 7) -> str:
    """Every individual client brand (one per row), with its client_id and
    recent activity, so the UI can offer a single-brand picker."""
    return f"""
SELECT brand, client_id, COUNT(*) AS n
FROM {_P()}
WHERE feed_date >= date_sub(current_date(), {int(days)})
  AND lower(client_flag) = 'client' AND brand IS NOT NULL
GROUP BY brand, client_id
ORDER BY n DESC
LIMIT 8000
""".strip()


def l1_values_query() -> str:
    """Global distinct L1 categories (across the catalog) for the picker."""
    return (f"SELECT digital_shelf_l1 AS value, COUNT(DISTINCT search_term) AS kws "
            f"FROM {_M()} WHERE digital_shelf_l1 IS NOT NULL "
            f"GROUP BY digital_shelf_l1 ORDER BY kws DESC LIMIT 400")


def l2_values_query() -> str:
    """Distinct L2 categories under a chosen L1."""
    return (f"SELECT digital_shelf_l2 AS value, COUNT(DISTINCT search_term) AS kws "
            f"FROM {_M()} WHERE digital_shelf_l1 = :l1 AND digital_shelf_l2 IS NOT NULL "
            f"GROUP BY digital_shelf_l2 ORDER BY kws DESC LIMIT 400")


def brands_in_category_query(level: str, days: int = 21) -> str:
    """Every brand competing in the chosen category (client OR competitor),
    with the client_id where each is most active and whether it is that
    account's own ('client') brand — so the user can build a report for any
    brand in the leaderboard (Bigelow, Twinings, Yogi…)."""
    lvl = _check_level(level)
    return f"""
SELECT p.brand, p.client_id,
       MAX(CASE WHEN lower(p.client_flag) = 'client' THEN 1 ELSE 0 END) AS is_client,
       COUNT(*) AS n
FROM {_P()} p
JOIN (SELECT DISTINCT client_id, search_term FROM {_M()} WHERE {lvl} = :value) m
  ON p.client_id = m.client_id AND p.search_term = m.search_term
WHERE p.brand IS NOT NULL
  AND p.feed_date >= date_sub(current_date(), {int(days)})
GROUP BY p.brand, p.client_id
ORDER BY n DESC
LIMIT 8000
""".strip()


def best_client_for_category_query(level: str) -> str:
    """The client whose data in the chosen L1/L2 exposes the MOST distinct real
    brands — gives the richest category leaderboard. Ranking by keyword coverage
    alone could pick an account whose brand attribution is masked ('UNKNOWN'),
    producing a useless single-brand landscape."""
    lvl = _check_level(level)
    junk = ", ".join(f"'{b}'" for b in
                     ("unknown", "unknown_brand", "null_value", "generic",
                      "unbranded", "n/a", "na", "none", "other", "others", "misc", ""))
    return f"""SELECT p.client_id, COUNT(DISTINCT p.brand) AS brands
FROM {_P()} p
JOIN (SELECT DISTINCT client_id, search_term FROM {_M()} WHERE {lvl} = :value) m
  ON p.client_id = m.client_id AND p.search_term = m.search_term
WHERE p.brand IS NOT NULL
  AND lower(trim(p.brand)) NOT IN ({junk})
  AND p.feed_date >= date_sub(current_date(), 30)
GROUP BY p.client_id
ORDER BY brands DESC
LIMIT 1""".strip()


def subcat_level_counts_query(l1_level: str) -> str:
    """Count distinct sub-category values at L2/L3/L4 under a chosen L1 for a
    client — so the report can break down at the level with the most segments."""
    l1 = _check_level(l1_level)
    cols = ", ".join(
        f"COUNT(DISTINCT {lv}) AS {lv}"
        for lv in ("digital_shelf_l2", "digital_shelf_l3", "digital_shelf_l4"))
    return f"SELECT {cols} FROM {_M()} WHERE client_id = :cid AND {l1} = :catval"


def date_bounds_query() -> str:
    return (f"SELECT MIN(feed_date) AS min_d, MAX(feed_date) AS max_d "
            f"FROM {_P()} WHERE client_id = :cid")


# ── Ad Incrementality & Efficiency (aramus_ds.search_incrementality_report) ─
def _I() -> str:
    return SETTINGS.qualified(SCHEMA_ARAMUS, TBL_INCR)


# ── Search Term Volume (common_catalog.aramus_ds.search_term_volume) ──────────
def _V() -> str:
    """Always common_catalog.aramus_ds — not controlled by DATABRICKS_CATALOG."""
    return f"{CATALOG_COMMON}.{SCHEMA_ARAMUS}.{TBL_SEARCH_VOLUME}"


def search_term_volume_query(keywords: list[str]) -> str:
    """Average monthly predicted_volume for a specific set of keywords.

    Divides the total predicted_volume by the number of distinct calendar months
    in the date range so the result is a per-month figure regardless of whether
    the caller selects 1 month, 3 months, or 6 months.

    Keywords are interpolated into an IN-clause (safe — values come from our
    own DB, not raw user input).

    Params: :s (start date), :e (end date), :rid (retailer_id, Amazon US = 4)
    """
    if not keywords:
        raise ValueError("keywords must not be empty")
    quoted = ", ".join(f"'{kw.replace(chr(39), chr(39)*2)}'" for kw in keywords)
    return f"""
SELECT search_term,
       CAST(
           SUM(predicted_volume)
           / NULLIF(COUNT(DISTINCT DATE_TRUNC('month', feed_date)), 0)
       AS BIGINT) AS search_volume
FROM {_V()}
WHERE feed_date BETWEEN :s AND :e
  AND retailer_id = :rid
  AND search_term IN ({quoted})
GROUP BY search_term
""".strip()


def _incr_cte(level: str | None) -> str:
    join = ""
    if level:
        join = (f"JOIN (SELECT DISTINCT client_id, search_term FROM {_M()} "
                f"WHERE {_check_level(level)} = :value) m "
                f"ON t.client_id = m.client_id AND t.search = m.search_term")
    return f"""f AS (
  SELECT t.search, t.cost, t.attributedsales14d AS sales, t.incremental_sales,
         t.client_sponsored_weight AS csw, t.total_sponsored_weight AS tsw,
         t.clicks, t.impressions
  FROM {_I()} t
  {join}
  WHERE t.client_id = :cid AND t.report_date BETWEEN :s AND :e
)"""


def incr_summary_query(level: str | None) -> str:
    return f"""WITH {_incr_cte(level)}
SELECT 100.0 * SUM(csw) / NULLIF(SUM(tsw), 0) AS paid_sov,
       SUM(cost) AS spend, SUM(sales) AS sales, SUM(incremental_sales) AS inc_sales,
       SUM(clicks) AS clicks, SUM(impressions) AS impressions,
       COUNT(DISTINCT search) AS kws
FROM f""".strip()


def incr_keywords_query(level: str | None, top: int = 12) -> str:
    return f"""WITH {_incr_cte(level)}
SELECT search AS keyword,
       100.0 * SUM(csw) / NULLIF(SUM(tsw), 0) AS paid_sov,
       SUM(cost) AS spend, SUM(sales) AS sales, SUM(incremental_sales) AS inc_sales
FROM f GROUP BY search HAVING SUM(cost) > 0
ORDER BY spend DESC LIMIT {int(top)}""".strip()


def incr_bands_query(level: str | None) -> str:
    return f"""WITH {_incr_cte(level)},
kw AS (SELECT search, SUM(cost) AS spend, SUM(sales) AS sales,
              SUM(incremental_sales) AS inc FROM f GROUP BY search)
SELECT CASE WHEN sales <= 0 THEN 'Low'
            WHEN inc / sales >= 0.66 THEN 'High'
            WHEN inc / sales >= 0.33 THEN 'Mid' ELSE 'Low' END AS band,
       SUM(spend) AS spend, COUNT(*) AS kws
FROM kw GROUP BY 1""".strip()


def category_values_query(level: str) -> str:
    lvl = _check_level(level)
    return (f"SELECT {lvl} AS value, COUNT(DISTINCT search_term) AS kws "
            f"FROM {_M()} WHERE client_id = :cid AND {lvl} IS NOT NULL "
            f"GROUP BY {lvl} ORDER BY kws DESC LIMIT 500")


# ── Workhorse: keyword × brand aggregate (dates collapsed) ───────────────
def keyword_brand_agg_query(level: str | None) -> str:
    """One row per (search_term, brand) for a client/category/date-range.

    Numerators are summed over dates; totals are de-duplicated per
    (search_term, feed_date) then summed over dates — the correct SOV base.
    """
    nums = numerator_columns()
    tots = total_columns()

    f_cols = ",\n         ".join(f"p.{c}" for c in nums + tots)
    # kd: one total per (search_term, feed_date)
    kd_tot = ",\n         ".join(f"MAX({c}) AS {c}" for c in tots)
    # kt: sum totals + crawls over dates (per keyword)
    kt_tot = ",\n         ".join(f"SUM({c}) AS {c}" for c in tots)
    # kb: sum numerators over dates (per keyword, brand)
    kb_num = ",\n         ".join(f"SUM({c}) AS {c}" for c in nums)
    final_tot = ",\n       ".join(f"kt.{c}" for c in tots)

    return f"""
WITH f AS (
  SELECT p.search_term, p.feed_date, p.brand,
         lower(p.client_flag) AS client_flag, p.no_of_crawls,
         m.keyword_type,
         {f_cols}
  FROM {_P()} p
  {_meta_join(level)}
  WHERE p.client_id = :cid
    AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT search_term, feed_date, MAX(no_of_crawls) AS crawls,
         {kd_tot}
  FROM f GROUP BY search_term, feed_date
),
kt AS (
  SELECT search_term, SUM(crawls) AS no_of_crawls,
         {kt_tot}
  FROM kd GROUP BY search_term
),
ktop AS (
  -- Cap to the top keywords by crawl volume so the result set stays small
  -- (avoids CloudFetch throttling on very large categories). The reports
  -- focus on the highest-volume keywords anyway.
  SELECT search_term FROM kt ORDER BY no_of_crawls DESC LIMIT :kwlimit
),
kb AS (
  SELECT search_term, brand,
         MAX(client_flag) AS client_flag,
         MAX(keyword_type) AS keyword_type,
         {kb_num}
  FROM f
  WHERE search_term IN (SELECT search_term FROM ktop)
  GROUP BY search_term, brand
)
SELECT kb.*, kt.no_of_crawls,
       {final_tot}
FROM kb JOIN kt USING (search_term)
""".strip()


# ── Brand-level FULL-category leaderboard (all keywords, small result) ───
def brand_agg_query(level: str | None) -> str:
    """One row per brand for the WHOLE category (every keyword), plus the
    category-level totals. Used for an accurate leaderboard / KPIs / channel
    mix regardless of any keyword cap applied to the keyword-level pull."""
    nums = numerator_columns()
    tots = total_columns()
    f_cols = ",\n         ".join(f"p.{c}" for c in nums + tots)
    kd_tot = ",\n         ".join(f"MAX({c}) AS {c}" for c in tots)
    tot_sum = ",\n         ".join(f"SUM({c}) AS {c}" for c in tots)
    ba_num = ",\n         ".join(f"SUM({c}) AS {c}" for c in nums)
    return f"""
WITH f AS (
  SELECT p.search_term, p.feed_date, p.brand,
         lower(p.client_flag) AS client_flag, p.no_of_crawls,
         {f_cols}
  FROM {_P()} p
  {_meta_join(level, with_keyword_type=False)}
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT search_term, feed_date, MAX(no_of_crawls) AS crawls,
         {kd_tot}
  FROM f GROUP BY search_term, feed_date
),
tot AS (
  SELECT SUM(crawls) AS no_of_crawls, {tot_sum} FROM kd
),
ba AS (
  SELECT brand, MAX(client_flag) AS client_flag, {ba_num}
  FROM f GROUP BY brand
)
SELECT ba.*, tot.* FROM ba CROSS JOIN tot
""".strip()


# ── Trend: week × brand SOV (computed in SQL for one metric) ─────────────
def trend_query(level: str | None, mtype: str, cutoff: str) -> str:
    num = numerator_col(mtype, cutoff)
    den = denominator_col(mtype, cutoff)
    return f"""
WITH f AS (
  SELECT date_trunc('week', p.feed_date) AS period, p.search_term, p.brand,
         lower(p.client_flag) AS client_flag, p.{num} AS num, p.{den} AS den
  FROM {_P()} p
  {_meta_join(level, with_keyword_type=False)}
  WHERE p.client_id = :cid
    AND p.feed_date BETWEEN :s AND :e
),
den AS (
  SELECT period, search_term, MAX(den) AS t FROM f GROUP BY period, search_term
),
base AS (
  SELECT period, SUM(t) AS base FROM den GROUP BY period
),
num AS (
  SELECT period, brand, MAX(client_flag) AS cf, SUM(num) AS n
  FROM f GROUP BY period, brand
)
SELECT num.period, num.brand, (num.cf = 'client') AS is_client,
       100.0 * num.n / NULLIF(base.base, 0) AS sov_pct
FROM num JOIN base USING (period)
ORDER BY num.period, sov_pct DESC
""".strip()


# ── L1 (or any level) overview: client SOV across all categories ─────────
def overview_query(level: str, mtype: str, cutoff: str) -> str:
    lvl = _check_level(level)
    num = numerator_col(mtype, cutoff)
    den = denominator_col(mtype, cutoff)
    return f"""
WITH f AS (
  SELECT m.category, p.search_term, p.feed_date, p.brand, p.no_of_crawls,
         p.{num} AS num, p.{den} AS den
  FROM {_P()} p
  JOIN (SELECT DISTINCT client_id, search_term, {lvl} AS category
        FROM {_M()} WHERE {lvl} IS NOT NULL) m
    ON p.client_id = m.client_id AND p.search_term = m.search_term
  WHERE p.client_id = :cid
    AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT category, search_term, feed_date,
         MAX(den) AS t, MAX(no_of_crawls) AS cr,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand)) THEN num ELSE 0 END) AS client_n
  FROM f GROUP BY category, search_term, feed_date
)
SELECT category,
       100.0 * SUM(client_n) / NULLIF(SUM(t), 0) AS client_sov,
       SUM(cr) AS crawls,
       COUNT(DISTINCT search_term) AS keywords
FROM kd GROUP BY category
ORDER BY crawls DESC
LIMIT 50
""".strip()


# ── Relevant-set SOV: focus brand vs its TRUE per-keyword competitors ────
def relevant_set_query(level: str, mtype: str, cutoff: str) -> str:
    """Leaderboard computed only among each keyword's `relevant_brands`
    (its real competitive set), plus the focus brand — so SOV reflects the
    handful of rivals that actually matter, not all brands in the catalog."""
    lvl = _check_level(level)
    num = numerator_col(mtype, cutoff)
    return f"""
WITH rel AS (
  SELECT DISTINCT client_id, search_term, rbrand FROM (
    SELECT client_id, search_term, explode(relevant_brands) AS rbrand
    FROM {_M()} WHERE {lvl} = :catval AND relevant_brands IS NOT NULL
    UNION ALL
    SELECT client_id, search_term, :fbrand AS rbrand
    FROM {_M()} WHERE {lvl} = :catval
  )
),
f AS (
  SELECT p.brand, lower(p.client_flag) AS client_flag, p.{num} AS num
  FROM {_P()} p
  JOIN rel ON p.client_id = rel.client_id AND p.search_term = rel.search_term
          AND lower(trim(p.brand)) = lower(trim(rel.rbrand))
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
ba AS (SELECT brand, MAX(client_flag) AS client_flag, SUM(num) AS n FROM f GROUP BY brand),
tot AS (SELECT SUM(num) AS base FROM f)
SELECT ba.brand, ba.client_flag, ba.n,
       100.0 * ba.n / NULLIF(tot.base, 0) AS sov_pct
FROM ba CROSS JOIN tot
ORDER BY sov_pct DESC
""".strip()


# ── Sub-category leaders: leader + focus brand per child category ────────
def category_leaders_query(group_level: str, filter_level: str | None = None,
                           mtype: str = "all", cutoff: str = "page_1") -> str:
    grp = _check_level(group_level)
    num = numerator_col(mtype, cutoff)
    den = denominator_col(mtype, cutoff)
    flt = f" AND {_check_level(filter_level)} = :catval" if filter_level else ""
    return f"""
WITH meta_sub AS (
  SELECT DISTINCT client_id, search_term, {grp} AS grp
  FROM {_M()} WHERE {grp} IS NOT NULL{flt}
),
f AS (
  SELECT m.grp, p.search_term, p.feed_date, p.brand, p.no_of_crawls,
         p.{num} AS num, p.{den} AS den
  FROM {_P()} p
  JOIN meta_sub m ON p.client_id = m.client_id AND p.search_term = m.search_term
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT grp, search_term, feed_date, MAX(den) AS t, MAX(no_of_crawls) AS cr
  FROM f GROUP BY grp, search_term, feed_date
),
den AS (
  SELECT grp, SUM(t) AS base, SUM(cr) AS crawls, COUNT(DISTINCT search_term) AS kws
  FROM kd GROUP BY grp
),
bg AS (SELECT grp, brand, SUM(num) AS n FROM f GROUP BY grp, brand),
ranked AS (
  SELECT grp, brand, n, ROW_NUMBER() OVER (PARTITION BY grp ORDER BY n DESC) rn FROM bg
),
leader AS (SELECT grp, brand AS leader, n AS leader_n FROM ranked WHERE rn = 1),
focus AS (
  SELECT grp, SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand)) THEN n ELSE 0 END) AS focus_n
  FROM bg GROUP BY grp
)
SELECT d.grp AS category, l.leader,
       100.0 * l.leader_n / NULLIF(d.base, 0) AS leader_sov,
       100.0 * COALESCE(fo.focus_n, 0) / NULLIF(d.base, 0) AS focus_sov,
       d.crawls, d.kws
FROM den d JOIN leader l USING (grp) LEFT JOIN focus fo USING (grp)
ORDER BY d.crawls DESC
LIMIT 30
""".strip()


# ── Your winning products (focus brand's top SKUs) ───────────────────────
def winning_asins_query(level: str | None) -> str:
    where = f"WHERE {_check_level(level)} = :catval" if level else ""
    return f"""
SELECT s.sku, MAX(s.title) AS title,
       MAX(s.image_url) AS image_url,
       MAX(s.product_page_url) AS product_page_url,
       COUNT(DISTINCT s.search_term) AS keywords,
       MIN(s.overall_listing_rank) AS best_rank,
       SUM(CASE WHEN s.listing_page = 1 THEN 1 ELSE 0 END) AS page1_hits
FROM {_S()} s
JOIN (SELECT client_id, search_term FROM {_M()} {where}
      GROUP BY client_id, search_term) m
  ON s.client_id = m.client_id AND s.search_term = m.search_term
WHERE s.client_id = :cid AND lower(trim(s.brand)) = lower(trim(:fbrand))
  AND s.feed_date >= date_sub(current_date(), 14)
GROUP BY s.sku
ORDER BY page1_hits DESC, best_rank ASC
LIMIT 25
""".strip()


# ── SKU drill-down + geography (best-effort) ─────────────────────────────
def sku_query() -> str:
    return f"""
SELECT search_term, sku, listing_rank, listing_type, listing_page, crawl_hour,
       zipcode, zipcode_region, retailer_id, feed_date, brand, title,
       image_url, product_page_url, lower(client_flag) AS client_flag,
       brand_by_client_flag, overall_listing_rank
FROM {_S()}
WHERE client_id = :cid AND search_term = :search_term
  AND feed_date >= date_sub(current_date(), 14)
ORDER BY listing_page, overall_listing_rank
LIMIT 300
""".strip()


# ── SKU optimizer queries ─────────────────────────────────────────────────
def optimizable_skus_query(level: str | None) -> str:
    """Focus-brand SKUs with the most ranking UPSIDE — they already appear for
    category keywords but rank BELOW the top positions, so better listing copy
    can lift them. Ordered by opportunity (reach x rank-gap). Excludes SKUs
    that already rank top — optimizing a #1 listing is pointless.
    """
    where = f"WHERE {_check_level(level)} = :catval" if level else ""
    return f"""
WITH kw AS (
  SELECT s.sku, s.search_term,
         MIN(s.overall_listing_rank) AS best_rank,
         MAX(CASE WHEN s.listing_page = 1 THEN 1 ELSE 0 END) AS on_p1
  FROM {_S()} s
  JOIN (SELECT client_id, search_term FROM {_M()} {where}
        GROUP BY client_id, search_term) m
    ON s.client_id = m.client_id AND s.search_term = m.search_term
  WHERE s.client_id = :cid AND lower(trim(s.brand)) = lower(trim(:fbrand))
    AND s.feed_date >= date_sub(current_date(), 14)
    AND s.overall_listing_rank IS NOT NULL AND s.overall_listing_rank > 0
  GROUP BY s.sku, s.search_term
),
info AS (
  SELECT s.sku, MAX(s.title) AS title, MAX(s.image_url) AS image_url,
         MAX(s.product_page_url) AS product_page_url
  FROM {_S()} s
  WHERE s.client_id = :cid AND lower(trim(s.brand)) = lower(trim(:fbrand))
    AND s.feed_date >= date_sub(current_date(), 14)
  GROUP BY s.sku
)
SELECT k.sku, i.title, i.image_url, i.product_page_url,
       COUNT(*) AS keywords,
       ROUND(AVG(k.best_rank), 1) AS avg_rank,
       MIN(k.best_rank) AS best_rank,
       SUM(k.on_p1) AS page1_kws,
       collect_list(k.search_term) AS kw_list,
       collect_list(k.best_rank) AS rank_list
FROM kw k JOIN info i USING (sku)
GROUP BY k.sku, i.title, i.image_url, i.product_page_url
HAVING COUNT(*) >= 1 AND AVG(k.best_rank) > 3
ORDER BY (COUNT(*) * AVG(k.best_rank)) DESC
LIMIT 6
""".strip()


def sku_keywords_query() -> str:
    """Keywords where a specific ASIN ranks on page 1 — used for listing opt."""
    return f"""
SELECT search_term,
       MIN(overall_listing_rank) AS best_rank,
       SUM(CASE WHEN listing_page = 1 THEN 1 ELSE 0 END) AS page1_hits,
       COUNT(DISTINCT feed_date) AS days_tracked
FROM {_S()}
WHERE client_id = :cid AND sku = :sku
  AND feed_date >= date_sub(current_date(), 14)
GROUP BY search_term
ORDER BY page1_hits DESC, best_rank ASC
LIMIT 30
""".strip()


def competitor_titles_query() -> str:
    """Top competitor ASIN titles on the same keywords the focus SKU ranks on."""
    return f"""
WITH focus_kws AS (
  SELECT DISTINCT search_term FROM {_S()}
  WHERE client_id = :cid AND sku = :sku
    AND listing_page = 1
    AND feed_date >= date_sub(current_date(), 14)
  LIMIT 15
)
SELECT s.sku, MAX(s.title) AS title, MAX(s.brand) AS brand,
       COUNT(DISTINCT s.search_term) AS kw_count,
       AVG(s.overall_listing_rank) AS avg_rank
FROM {_S()} s
JOIN focus_kws k ON s.search_term = k.search_term
WHERE s.client_id = :cid
  AND s.sku != :sku
  AND s.listing_page = 1
  AND s.overall_listing_rank <= 5
  AND s.feed_date >= date_sub(current_date(), 14)
  AND s.title IS NOT NULL
GROUP BY s.sku
ORDER BY kw_count DESC, avg_rank ASC
LIMIT 5
""".strip()


# ── SOV-based incrementality (organic vs paid from shelf data only) ───────
def sov_incr_overview_query(level: str = "digital_shelf_l1") -> str:
    """Per-category organic vs paid SOV for a focus brand — computed from the
    SOV performance cube only (no ad-spend tables).
    Organic and Paid are BOTH measured as points of total_all (same denominator)
    so organic_sov + paid_sov ≈ combined_sov."""
    lvl = _check_level(level)
    return f"""
WITH f AS (
  SELECT m.category, p.search_term, p.feed_date, p.brand, p.no_of_crawls,
         p.organic_page_1_count AS org, p.sp_page_1_count AS sp,
         p.sb_page_1_count AS sb, p.all_page_1_count AS comb,
         p.total_all_page_1_count AS tot
  FROM {_P()} p
  JOIN (SELECT DISTINCT client_id, search_term, {lvl} AS category
        FROM {_M()} WHERE {lvl} IS NOT NULL) m
    ON p.client_id = m.client_id AND p.search_term = m.search_term
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT category, search_term, feed_date,
         MAX(tot) AS t, MAX(no_of_crawls) AS cr,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN org ELSE 0 END) AS f_org,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN sp + sb ELSE 0 END) AS f_paid,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN comb ELSE 0 END) AS f_comb
  FROM f GROUP BY category, search_term, feed_date
)
SELECT category,
       100.0 * SUM(f_org)  / NULLIF(SUM(t), 0) AS organic_sov,
       100.0 * SUM(f_paid) / NULLIF(SUM(t), 0) AS paid_sov,
       100.0 * SUM(f_comb) / NULLIF(SUM(t), 0) AS combined_sov,
       SUM(cr) AS crawls,
       COUNT(DISTINCT search_term) AS keywords
FROM kd GROUP BY category
HAVING SUM(f_comb) > 0
ORDER BY crawls DESC
LIMIT 30
""".strip()


def sov_incr_all_levels_query(max_level: int = 5,
                              l1_filter: list[str] | None = None) -> str:
    """Per-category organic vs paid SOV across L1-L{max_level} for a focus brand
    in ONE query. Each row carries the FULL ancestry path (l1, l2, l3, …)
    so the UI can render 'Pet Supplies > Dog Food > Wet Food'.

    If `l1_filter` is given, only keywords under those L1 values are included.
    """
    # Build the metadata sub-selects.  Each level carries all ancestor columns
    # so we can reconstruct the full path.
    l1_where = ""
    if l1_filter:
        # Parameterised filter built from the safe list length
        placeholders = ", ".join(f":l1f{i}" for i in range(len(l1_filter)))
        l1_where = f" AND digital_shelf_l1 IN ({placeholders})"

    parts: list[str] = []
    for depth in range(1, max_level + 1):
        col = f"digital_shelf_l{depth}"
        _check_level(col)
        # Ancestor columns: L1..L(depth-1) as context, L(depth) as `category`
        ancestor_cols = ", ".join(
            f"MAX(digital_shelf_l{j}) AS l{j}" for j in range(1, depth))
        ancestor_group = ""
        if depth > 1:
            ancestor_cols = ", " + ancestor_cols
            # group by all levels up to depth so the same leaf under different
            # parents stays separate
            ancestor_group = "".join(
                f", digital_shelf_l{j}" for j in range(1, depth))
        parts.append(
            f"SELECT 'L{depth}' AS lvl, {col} AS category{ancestor_cols}, "
            f"client_id, search_term "
            f"FROM {_M()} "
            f"WHERE client_id = :cid AND {col} IS NOT NULL{l1_where} "
            f"GROUP BY {col}{ancestor_group}, client_id, search_term")
    meta_union = " UNION ALL ".join(parts)

    # Pad missing ancestor columns so the UNION schema matches
    max_ancestors = max_level - 1
    padded_parts: list[str] = []
    for depth in range(1, max_level + 1):
        col = f"digital_shelf_l{depth}"
        _check_level(col)
        anc_select = []
        for j in range(1, max_ancestors + 1):
            if j < depth:
                anc_select.append(f"MAX(digital_shelf_l{j}) AS l{j}")
            else:
                anc_select.append(f"NULL AS l{j}")
        anc_str = ", ".join(anc_select)
        anc_group = "".join(
            f", digital_shelf_l{j}" for j in range(1, depth))
        padded_parts.append(
            f"SELECT 'L{depth}' AS lvl, {col} AS category, {anc_str}, "
            f"client_id, search_term "
            f"FROM {_M()} "
            f"WHERE client_id = :cid AND {col} IS NOT NULL{l1_where} "
            f"GROUP BY {col}{anc_group}, client_id, search_term")
    meta_union = " UNION ALL ".join(padded_parts)

    # Ancestor columns to SELECT / GROUP in outer queries
    anc_cols = ", ".join(f"m.l{j}" for j in range(1, max_ancestors + 1))
    anc_grp = ", ".join(f"l{j}" for j in range(1, max_ancestors + 1))

    return f"""
WITH meta AS ({meta_union}),
f AS (
  SELECT m.lvl, m.category, {anc_cols},
         p.search_term, p.feed_date, p.brand, p.no_of_crawls,
         p.organic_page_1_count AS org, p.sp_page_1_count AS sp,
         p.sb_page_1_count AS sb, p.all_page_1_count AS comb,
         p.total_all_page_1_count AS tot
  FROM {_P()} p
  JOIN meta m ON p.client_id = m.client_id AND p.search_term = m.search_term
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT lvl, category, {anc_grp}, search_term, feed_date,
         MAX(tot) AS t, MAX(no_of_crawls) AS cr,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN org ELSE 0 END) AS f_org,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN sp + sb ELSE 0 END) AS f_paid,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN comb ELSE 0 END) AS f_comb
  FROM f GROUP BY lvl, category, {anc_grp}, search_term, feed_date
)
SELECT lvl AS level, category, {anc_grp},
       100.0 * SUM(f_org)  / NULLIF(SUM(t), 0) AS organic_sov,
       100.0 * SUM(f_paid) / NULLIF(SUM(t), 0) AS paid_sov,
       100.0 * SUM(f_comb) / NULLIF(SUM(t), 0) AS combined_sov,
       SUM(cr) AS crawls,
       COUNT(DISTINCT search_term) AS keywords
FROM kd GROUP BY lvl, category, {anc_grp}
HAVING SUM(f_comb) > 0
ORDER BY lvl, crawls DESC
""".strip()


def sov_incr_keywords_query(level: str) -> str:
    """Per-keyword organic vs paid SOV for a focus brand in one category.
    Both channels as points of total_all (same denominator)."""
    return f"""
WITH f AS (
  SELECT p.search_term, p.feed_date, p.brand, p.no_of_crawls,
         p.organic_page_1_count AS org, p.sp_page_1_count AS sp,
         p.sb_page_1_count AS sb, p.all_page_1_count AS comb,
         p.total_all_page_1_count AS tot
  FROM {_P()} p
  JOIN (SELECT client_id, search_term FROM {_M()}
        WHERE {_check_level(level)} = :catval
        GROUP BY client_id, search_term) m
    ON p.client_id = m.client_id AND p.search_term = m.search_term
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT search_term, feed_date,
         MAX(tot) AS t, MAX(no_of_crawls) AS cr,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN org ELSE 0 END) AS f_org,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN sp + sb ELSE 0 END) AS f_paid,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN comb ELSE 0 END) AS f_comb
  FROM f GROUP BY search_term, feed_date
)
SELECT search_term,
       100.0 * SUM(f_org)  / NULLIF(SUM(t), 0) AS organic_sov,
       100.0 * SUM(f_paid) / NULLIF(SUM(t), 0) AS paid_sov,
       100.0 * SUM(f_comb) / NULLIF(SUM(t), 0) AS combined_sov,
       SUM(cr) AS crawls
FROM kd GROUP BY search_term
HAVING SUM(t) > 0
ORDER BY crawls DESC
LIMIT 200
""".strip()


def sov_incr_keywords_ranked_query(level: str) -> str:
    """Per-keyword organic vs paid SOV for a focus brand in one category,
    WITH the brand's rank among all brands on each keyword (by all_page_1_count).
    Returns: search_term, organic_sov, paid_sov, combined_sov, crawls, rank,
             keyword_type (branded/generic from metadata)."""
    return f"""
WITH f AS (
  SELECT p.search_term, p.feed_date, p.brand, p.no_of_crawls, m.keyword_type,
         p.organic_page_1_count AS org, p.sp_page_1_count AS sp,
         p.sb_page_1_count AS sb, p.all_page_1_count AS comb,
         p.total_all_page_1_count AS tot
  FROM {_P()} p
  JOIN (SELECT client_id, search_term, MAX(keyword_type) AS keyword_type FROM {_M()}
        WHERE {_check_level(level)} = :catval
        GROUP BY client_id, search_term) m
    ON p.client_id = m.client_id AND p.search_term = m.search_term
  WHERE p.client_id = :cid AND p.feed_date BETWEEN :s AND :e
),
kd AS (
  SELECT search_term, feed_date,
         MAX(keyword_type) AS keyword_type, MAX(tot) AS t, MAX(no_of_crawls) AS cr,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN org ELSE 0 END) AS f_org,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN sp + sb ELSE 0 END) AS f_paid,
         SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand))
                  THEN comb ELSE 0 END) AS f_comb
  FROM f GROUP BY search_term, feed_date
),
focus_sov AS (
  SELECT search_term, MAX(keyword_type) AS keyword_type,
         100.0 * SUM(f_org)  / NULLIF(SUM(t), 0) AS organic_sov,
         100.0 * SUM(f_paid) / NULLIF(SUM(t), 0) AS paid_sov,
         100.0 * SUM(f_comb) / NULLIF(SUM(t), 0) AS combined_sov,
         SUM(cr) AS crawls
  FROM kd GROUP BY search_term
  HAVING SUM(t) > 0
),
brand_kw AS (
  SELECT search_term, brand, SUM(comb) AS brand_comb
  FROM f GROUP BY search_term, brand
),
ranked AS (
  SELECT search_term, brand, brand_comb,
         ROW_NUMBER() OVER (PARTITION BY search_term ORDER BY brand_comb DESC) AS rk
  FROM brand_kw
),
focus_rank AS (
  SELECT search_term, rk AS rank
  FROM ranked
  WHERE lower(trim(brand)) = lower(trim(:fbrand))
)
SELECT fs.search_term, fs.organic_sov, fs.paid_sov, fs.combined_sov,
       fs.crawls, COALESCE(fr.rank, 999) AS rank, fs.keyword_type
FROM focus_sov fs
LEFT JOIN focus_rank fr ON fs.search_term = fr.search_term
ORDER BY fs.crawls DESC
LIMIT 200
""".strip()


def region_share_query(level: str | None) -> str:
    return f"""
WITH s AS (
  SELECT s.zipcode_region AS region, s.brand, s.listing_page
  FROM {_S()} s
  JOIN (SELECT client_id, search_term FROM {_M()}
        {('WHERE ' + _check_level(level) + ' = :catval') if level else ''}
        GROUP BY client_id, search_term) m
    ON s.client_id = m.client_id AND s.search_term = m.search_term
  WHERE s.client_id = :cid
    AND s.feed_date >= date_sub(current_date(), 14)
)
SELECT region,
       SUM(CASE WHEN lower(trim(brand)) = lower(trim(:fbrand)) AND listing_page = 1 THEN 1 ELSE 0 END) AS client_listings,
       SUM(CASE WHEN listing_page = 1 THEN 1 ELSE 0 END) AS total_listings
FROM s
WHERE region IS NOT NULL
GROUP BY region
HAVING total_listings > 0
ORDER BY total_listings DESC
LIMIT 40
""".strip()
