"""Category & Keyword Positioning — single-service Streamlit app (tables view).

Run:  streamlit run app.py
Pick ONE client brand; see where it stands across its L1/L2 categories and
keywords on Amazon as numbered tables; export a CommerceIQ-branded HTML/PDF.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import SETTINGS
from sov import branding as B
from sov import data, history, narrative, report, sku_optimizer, transforms
from sov.metrics import CATEGORY_LABELS, CUTOFFS

st.set_page_config(page_title="Category & Keyword Positioning",
                   page_icon="📊", layout="wide")

LENS = {"Combined (SP + Organic + SB)": "all",
        "Sponsored Products": "sp", "Organic": "organic"}
LEVELS = ["digital_shelf_l1", "digital_shelf_l2"]
OVERVIEW = "🌐 All categories (overview)"
MAX_DAYS = 120

st.markdown(f"""
<style>
  .stApp {{ background: {B.WHITE}; }}
  h1, h2, h3 {{ color: {B.DEEP_PURPLE}; }}
  div.stButton > button[kind="primary"] {{
      background: {B.ELECTRIC}; border: none; color: white;
      font-weight: 700; padding: .6rem 1.2rem; border-radius: 8px; }}
  div.stButton > button[kind="primary"]:hover {{ background: #A714E6; }}
  [data-testid="stMetricValue"] {{ color: {B.DEEP_PURPLE}; }}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading brands…")
def _brands():
    return data.get_brands()


@st.cache_data(show_spinner=False)
def _bounds(cid):
    return data.get_date_bounds(cid)


@st.cache_data(show_spinner="Loading L1 categories…")
def _l1_values():
    return data.get_l1_values()


@st.cache_data(show_spinner="Loading L2 categories…")
def _l2_values(l1):
    return data.get_l2_values(l1)


@st.cache_data(show_spinner="Finding brands in this category…")
def _brands_in_cat(level, value):
    return data.get_brands_in_category(level, value)


@st.cache_data(show_spinner=False)
def _best_cid_for_cat(level, value):
    return data.get_best_client_for_category(level, value)


@st.cache_data(show_spinner="Building category leaderboard…")
def _brand_agg(cid, level, catval, start, end):
    return data.get_brand_agg(cid, level, catval, start, end)


@st.cache_data(show_spinner="Pulling keyword detail…")
def _kb(cid, level, catval, start, end):
    return data.get_keyword_brand_agg(cid, level, catval, start, end)


@st.cache_data(show_spinner="Computing relevant-set SOV…")
def _relset(cid, level, catval, start, end, mtype, cutoff, fbrand):
    return data.get_relevant_set_leaderboard(cid, level, catval, start, end,
                                             mtype, cutoff, fbrand)


@st.cache_data(show_spinner="Finding your products…")
def _asins(cid, level, catval, fbrand):
    return data.get_winning_asins(cid, level, catval, fbrand)


@st.cache_data(show_spinner="Pulling ad incrementality & efficiency…")
def _incr(cid, level, catval, start, end):
    return data.get_incrementality(cid, level, catval, start, end)


@st.cache_data(show_spinner="Building trend…")
def _trend(cid, level, catval, start, end, mtype, cutoff, brands):
    return data.get_trend(cid, level, catval, start, end, mtype, cutoff,
                          brands=list(brands) if brands else None)


@st.cache_data(show_spinner="Computing category landscape…")
def _overview(cid, level, start, end, mtype, cutoff, fbrand):
    return data.get_overview(cid, level, start, end, mtype, cutoff, fbrand)


@st.cache_data(show_spinner="Fetching keyword rankings for ASIN…")
def _sku_kws(cid, sku):
    return data.get_sku_keywords(cid, sku)


@st.cache_data(show_spinner="Fetching competitor titles…")
def _comp_titles(cid, sku):
    return data.get_competitor_titles(cid, sku)


def _num(df: pd.DataFrame) -> pd.DataFrame:
    """Prepend a 1..N number column for display."""
    d = df.copy()
    d.insert(0, "#", range(1, len(d) + 1))
    return d


# ── Header ───────────────────────────────────────────────────────────────
st.title("📊 Category & Keyword Positioning")
st.caption("Pick a category, then a brand competing in it, to see where that "
           "brand stands on Amazon — tables only, easy to read. "
           "_First load may take up to a minute while the data connection warms up._")

_, scol = st.columns([3, 1])
with scol:
    if SETTINGS.is_live and SETTINGS.databricks_ready:
        st.success("🟢 Live · Databricks")
    elif SETTINGS.is_live:
        st.error("Live mode but Databricks not configured (.env).")
    else:
        st.info("🟡 Sample data mode")
    st.caption("AI insights: OpenAI ✅" if SETTINGS.openai_ready
               else "AI insights: rule-based")
if SETTINGS.is_live and not SETTINGS.databricks_ready:
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Mode selector ────────────────────────────────────────────────────
    report_mode = st.radio(
        "Report type",
        ["🔍 Brand Report", "📊 Category Report"],
        horizontal=True,
        help="**Brand Report** — pick one brand and see how it ranks vs competitors.\n\n"
             "**Category Report** — see the full category landscape with no focus brand; "
             "great for prospect outreach.")
    is_category_mode = report_mode == "📊 Category Report"

    st.divider()

    # ── 1 · Category pickers (shared by both modes) ──────────────────────
    st.header("1 · Choose a category")
    l1_pairs = _l1_values()
    if not l1_pairs:
        st.error("No categories found.")
        st.stop()
    l1_opts = [f"{v}  ({k:,} kw)" for v, k in l1_pairs]
    l1_lookup = {f"{v}  ({k:,} kw)": (v, k) for v, k in l1_pairs}
    l1_choice = st.selectbox("Category L1", l1_opts,
                             help="Pick the category you care about.")
    l1, l1_kw = l1_lookup[l1_choice]

    l2_pairs = _l2_values(l1)
    L2_ALL = f"— All of {l1} —"
    l2_opts = [L2_ALL] + [f"{v}  ({k:,} kw)" for v, k in l2_pairs]
    l2_lookup = {f"{v}  ({k:,} kw)": (v, k) for v, k in l2_pairs}
    l2_choice = st.selectbox("Category L2 (optional)", l2_opts)
    if l2_choice == L2_ALL:
        level, category_value, selected_kw = "digital_shelf_l1", l1, l1_kw
    else:
        l2v, l2k = l2_lookup[l2_choice]
        level, category_value, selected_kw = "digital_shelf_l2", l2v, l2k

    # ── 2 · Brand picker (brand mode only) ───────────────────────────────
    if not is_category_mode:
        st.header("2 · Pick a brand to analyze")
        cat_brands = _brands_in_cat(level, category_value)
        if not cat_brands:
            st.warning("No brands found competing in this category. Try another.")
            st.stop()
        names = [b["brand"] for b in cat_brands]
        brand_name = st.selectbox(
            f"Brands in {category_value}", names,
            help="Brands tracked in this category. The report highlights the one you pick.")
        focus = cat_brands[names.index(brand_name)]
        cid, focus_brand = focus["client_id"], focus["brand"]
        focus_is_client = bool(focus.get("is_client", True))
    else:
        # Category mode: resolve best client_id for date-range bounds
        focus_brand = None
        focus_is_client = False
        cid_for_bounds = _best_cid_for_cat(level, category_value)
        if not cid_for_bounds:
            st.warning("No data found for this category. Try a different one.")
            st.stop()
        cid = cid_for_bounds

    # ── 3 · Measure settings ─────────────────────────────────────────────
    step_label = "3 · How to measure" if not is_category_mode else "2 · Date range"
    st.header(step_label)
    lo, hi = _bounds(cid)
    earliest = max(lo, hi - dt.timedelta(days=MAX_DAYS))
    date_range = st.date_input(f"Date range (last {MAX_DAYS} days max)",
                               value=(earliest, hi),
                               min_value=earliest, max_value=hi)

    if not is_category_mode:
        lens_label = st.radio("Ad type", list(LENS.keys()), index=0)
        mtype = LENS[lens_label]
        cutoff = st.selectbox("Position", list(CUTOFFS.keys()), index=0,
                              format_func=lambda x: CUTOFFS[x])
        top_n = st.slider("Keywords to show", 5, 30, 15)
        _default_name = f"{focus_brand} — {category_value}"
    else:
        mtype, cutoff, top_n = "all", "page_1", 15
        _default_name = f"Category: {category_value}"

    report_name = st.text_input(
        "Report name", value="", placeholder=_default_name,
        help="Used for the saved history entry and the download filename. "
             "Leave blank to auto-name.")

    generate = st.button("🚀 Generate report", type="primary",
                         use_container_width=True)
    st.caption("Reports can take a few minutes on large categories.")

    st.divider()
    with st.expander("📜 Report history"):
        _hist = history.list_reports()
        if not _hist:
            st.caption("No saved reports yet — generate one to start the history.")
        else:
            _labels = [f"{(e.get('name') or (e['brand'] + ' · ' + e['category']))[:44]}"
                       f"  ·  {e['ts']}" for e in _hist]
            _hi = st.selectbox(f"{len(_hist)} saved", range(len(_hist)),
                               format_func=lambda i: _labels[i], key="hist_sel")
            if st.button("Open saved report", key="hist_open",
                         use_container_width=True):
                e = _hist[_hi]
                _html = history.load_html(e["id"])
                if _html:
                    st.session_state.pop("pdf_bytes", None)
                    st.session_state["report"] = {
                        "mode": "history", "html": _html, "source": e.get("source", ""),
                        "ts": e["ts"],
                        "scope": {"brand_label": e["brand"],
                                  "category_value": e["category"],
                                  "name": e.get("name", "")}}
                else:
                    st.warning("That report's file is missing.")


def _dates():
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        return date_range
    return None, None


def _scope(dmin, dmax):
    return {"brand_label": focus_brand, "level": level,
            "level_label": CATEGORY_LABELS[level],
            "category_value": category_value or "All categories",
            "metric": mtype, "metric_label": lens_label,
            "cutoff": cutoff, "cutoff_label": CUTOFFS[cutoff],
            "date_min": str(dmin), "date_max": str(dmax),
            "name": (report_name.strip() or f"{focus_brand} — {category_value}")}


# ── Display formatters (return tidy, rounded DataFrames) ──────────────────
def _f_leader(lb):
    d = lb.head(15).copy()
    d["You"] = d["is_client"].map({True: "★ YOU", False: ""})
    d = d.rename(columns={"brand": "Brand", "sov_pct": "SOV %"})
    d["SOV %"] = d["SOV %"].round(2)
    return d[["Brand", "SOV %", "You"]]


def _f_relset(rel):
    d = rel.head(15).copy()
    d["You"] = d["is_focus"].map({True: "★ YOU", False: ""})
    d = d.rename(columns={"brand": "Brand", "sov_pct": "SOV % (vs rivals)"})
    d["SOV % (vs rivals)"] = d["SOV % (vs rivals)"].round(2)
    return d[["Brand", "SOV % (vs rivals)", "You"]]


def _f_positioning(kp):
    d = kp.rename(columns={
        "search_term": "Keyword", "client_sov": "Your SOV %",
        "client_rank": "Your rank", "leader": "Leader",
        "leader_sov": "Leader SOV %", "crawls": "Crawls", "brands": "Brands"})
    for c in ["Your SOV %", "Leader SOV %"]:
        d[c] = d[c].round(1)
    d["Crawls"] = d["Crawls"].round(0).astype(int)
    d["Your rank"] = d["Your rank"].astype("Int64")
    return d[["Keyword", "Your SOV %", "Your rank", "Leader", "Leader SOV %",
              "Crawls"]]


def _f_inc(inc):
    d = inc.rename(columns={
        "search_term": "Keyword", "organic_sov": "Organic SoV %",
        "incremental_sov": "Paid SoV %", "combined_sov": "Combined SoV %",
        "classification": "Profile", "crawls": "Crawls"})
    for c in ["Organic SoV %", "Paid SoV %", "Combined SoV %"]:
        d[c] = d[c].round(1)
    d["Crawls"] = d["Crawls"].round(0).astype(int)
    return d[["Keyword", "Organic SoV %", "Paid SoV %", "Combined SoV %",
              "Profile", "Crawls"]]


def _f_whitespace(ws):
    d = ws.rename(columns={"search_term": "Keyword", "crawls": "Crawls",
                           "client_sov": "Your SOV %", "opportunity": "Opportunity"})
    d["Your SOV %"] = d["Your SOV %"].round(1)
    d["Crawls"] = d["Crawls"].round(0).astype(int)
    d["Opportunity"] = d["Opportunity"].round(3)
    return d[["Keyword", "Crawls", "Your SOV %", "Opportunity"]]


def _f_movers(wl):
    d = wl.copy()
    d["You"] = d["is_client"].map({True: "★ YOU", False: ""})
    d = d.rename(columns={"brand": "Brand", "start_sov": "Start SOV %",
                          "end_sov": "End SOV %", "delta": "Δ pts"})
    for c in ["Start SOV %", "End SOV %", "Δ pts"]:
        d[c] = d[c].round(2)
    return d[["Brand", "Start SOV %", "End SOV %", "Δ pts", "You"]]


def _f_simple(df, namecol, valcol, names):
    d = df.rename(columns={namecol: names[0], valcol: names[1]})
    d[names[1]] = d[names[1]].round(2)
    return d[[names[0], names[1]]]


def _f_asins(a):
    d = a.copy()
    if d.empty:
        return d
    d["title"] = d["title"].astype(str).str.slice(0, 70)
    d = d.rename(columns={"sku": "ASIN", "title": "Title", "keywords": "Keywords",
                          "best_rank": "Best rank", "page1_hits": "Page-1 hits"})
    return d[["ASIN", "Title", "Keywords", "Best rank", "Page-1 hits"]]


def _f_orgpaid(op):
    d = op.copy()
    d["You"] = d["is_client"].map({True: "★ YOU", False: ""})
    d = d.rename(columns={"brand": "Brand", "organic_sov": "Organic SOV %",
                          "paid_sov": "Paid SOV %"})
    d["Organic SOV %"] = d["Organic SOV %"].round(2)
    d["Paid SOV %"] = d["Paid SOV %"].round(2)
    return d[["Brand", "Organic SOV %", "Paid SOV %", "You"]]


def _f_leaders(ld):
    d = ld.rename(columns={"category": "Sub-category", "leader": "Leader",
                           "leader_sov": "Leader SOV %", "focus_sov": "Your SOV %",
                           "crawls": "Crawls"})
    for c in ["Leader SOV %", "Your SOV %"]:
        d[c] = d[c].round(1)
    d["Crawls"] = d["Crawls"].round(0).astype(int)
    return d[["Sub-category", "Leader", "Leader SOV %", "Your SOV %", "Crawls"]]


# ── Build report ───────────────────────────────────────────────────────--
def _build_overview(start, end):
    ov = _overview(cid, level, start, end, mtype, cutoff, focus_brand)
    if ov.empty:
        st.warning("No category data for this selection.")
        return None
    scope = _scope(start, end)
    active = ov[ov["crawls"] > 0]
    best = ov.sort_values("client_sov", ascending=False).iloc[0]
    worst = active.sort_values("client_sov").iloc[0] if not active.empty else best
    cards = [
        ("Categories", f"{len(ov):,}", B.COBALT),
        ("Strongest", f"{best['category']} · {best['client_sov']:.1f}%", B.ELECTRIC),
        ("Weakest", f"{worst['category']} · {worst['client_sov']:.1f}%", B.DEEP_PURPLE),
        ("Total crawls", f"{ov['crawls'].sum():,.0f}", B.SKY),
    ]
    ov_tbl = ov.rename(columns={"category": "Category", "client_sov": "Your SOV %",
                                "crawls": "Crawls", "keywords": "Keywords"})
    ov_tbl["Your SOV %"] = ov_tbl["Your SOV %"].round(2)
    ov_tbl["Crawls"] = ov_tbl["Crawls"].round(0).astype(int)
    ov_tbl = ov_tbl[["Category", "Your SOV %", "Crawls", "Keywords"]]
    tables = [(f"Category landscape — {focus_brand} SOV by category", ov_tbl)]
    context = {"scope": scope, "overview": ov.head(20).to_dict("records")}
    with st.spinner("Writing insights…"):
        narr, src = narrative.generate_narrative(context)
    html = report.build_html_report(scope, cards, narr, tables=tables,
                                    narrative_source=src)
    return {"mode": "overview", "scope": scope, "cards": cards,
            "tables": tables, "narrative": narr, "source": src, "html": html}


def _build_deepdive(start, end):
    brandagg = _brand_agg(cid, level, category_value, start, end)
    if brandagg.empty:
        st.warning("No data for this category/date range.")
        return None
    kb = _kb(cid, level, category_value, start, end)
    scope = _scope(start, end)

    # THE single SOV number: Combined SOV vs all brands, split into organic+paid pts
    cl = transforms.combined_leaderboard(brandagg, cutoff, focus_brand, top=15)
    kp = transforms.keyword_positioning(kb, top_n, mtype, cutoff, focus_brand)
    ws = transforms.top_keywords(kb, top_n, mtype, cutoff, "opportunity", focus_brand)
    cov = transforms.coverage(kb, mtype, cutoff, focus_brand)

    frow = cl[cl["is_client"]]
    your_sov = float(frow["combined_sov"].sum()) if not frow.empty else 0.0
    org_pts = float(frow["organic_pts"].sum()) if not frow.empty else 0.0
    paid_pts = float(frow["paid_pts"].sum()) if not frow.empty else 0.0
    your_rank = int(frow["rank"].min()) if not frow.empty else None
    nbrands = int(brandagg["brand"].nunique())
    rivals = [{"brand": str(r["brand"]), "sov": float(r["combined_sov"])}
              for _, r in cl[~cl["is_client"]].head(5).iterrows()]
    top_rival = rivals[0] if rivals else None

    lvl_n = int(level.rsplit("l", 1)[-1])
    child_level = f"digital_shelf_l{lvl_n + 1}" if lvl_n < 10 else None
    leaders = (data.get_category_leaders(cid, child_level, level, category_value,
                                         start, end, "all", cutoff, focus_brand)
               if child_level else None)
    if leaders is not None and leaders.empty:
        leaders = None

    # Ad incrementality only for a brand that is an actual client with ad data
    incr = _incr(cid, level, category_value, start, end) if focus_is_client else None

    context = {
        "scope": {"brand_label": focus_brand, "category_value": category_value,
                  "metric_label": lens_label},
        "sov": {"combined_pct": round(your_sov, 2), "organic_pts": round(org_pts, 2),
                "paid_pts": round(paid_pts, 2), "rank": your_rank, "brands": nbrands},
        "top_brands_ahead": rivals,
        "subcategory_leaders": (leaders.head(8).to_dict("records")
                                if leaders is not None else []),
        "top_keywords": ws.to_dict("records"),
        "coverage": cov,
    }
    if incr:
        s = incr["summary"]
        context["ad_efficiency"] = {"paid_sov_pct": round(s.get("paid_sov", 0), 1),
                                    "roas": round(s.get("roas", 0), 1),
                                    "iroas": round(s.get("iroas", 0), 1),
                                    "incremental_pct": round(s.get("inc_frac", 0) * 100)}
    with st.spinner("Writing insights with AI…"):
        ins, src = narrative.generate_sectioned_insights(context)

    # Deterministic headline — guaranteed to match the numbers shown
    if your_rank == 1 or (top_rival and your_sov >= top_rival["sov"]):
        ins["verdict"] = (f"{focus_brand} leads {category_value} with {your_sov:.1f}% "
                          f"Share of Voice ({org_pts:.1f} pts organic · "
                          f"{paid_pts:.1f} pts paid).")
    else:
        gap = (top_rival["sov"] - your_sov) if top_rival else 0.0
        ins["verdict"] = (
            f"{focus_brand} holds {your_sov:.1f}% Share of Voice in {category_value}"
            + (f", ranking #{your_rank} of {nbrands} brands" if your_rank else "")
            + (f" — {top_rival['brand']} leads at {top_rival['sov']:.1f}% "
               f"(a {gap:.1f} pt gap)." if top_rival else ".")
            + f" Your share is {org_pts:.1f} pts organic and {paid_pts:.1f} pts paid.")

    themed = {
        "hero": {"your_sov": your_sov, "rank": your_rank,
                 "organic": org_pts, "paid": paid_pts},
        "leaderboard": [{"brand": r["brand"], "combined_sov": float(r["combined_sov"]),
                         "organic_pts": float(r["organic_pts"]),
                         "paid_pts": float(r["paid_pts"]),
                         "is_focus": bool(r["is_client"])}
                        for _, r in cl.iterrows()],
        "subcats": ([{"sub": r["category"], "leader": r["leader"],
                      "leader_sov": float(r["leader_sov"]),
                      "focus_sov": float(r["focus_sov"])}
                     for _, r in leaders.head(6).iterrows()]
                    if leaders is not None else []),
        "whitespace": [{"kw": r["search_term"], "your_sov": float(r["client_sov"]),
                        "crawls": float(r["crawls"])} for _, r in ws.head(10).iterrows()],
    }
    if incr:
        s = incr["summary"]
        themed["incr"] = {
            "summary": s,
            "intro": (f"{focus_brand} captures {s['paid_sov']:.1f}% paid Share of Voice "
                      f"from its ad activity at ROAS {s['roas']:.1f}x; about "
                      f"{s['inc_frac'] * 100:.0f}% of those ad-driven sales are incremental "
                      f"(iROAS {s['iroas']:.1f}x). Ad-attribution data from this brand's own "
                      f"ad account."),
            "keywords": [{"kw": r["keyword"], "paid_sov": float(r["paid_sov"]),
                          "roas": float(r["roas"]), "iroas": float(r["iroas"])}
                         for _, r in incr["keywords"].iterrows()],
            "bands": [{"band": r["band"], "kws": float(r["kws"]),
                       "spend": float(r["spend"])} for _, r in incr["bands"].iterrows()],
        }
    html = report.build_themed_report(scope, ins, themed, src)
    return {"mode": "deepdive", "scope": scope, "html": html, "kp": kp, "source": src}


def _build_category_report(start, end):
    """Category-landscape report — no focus brand."""
    best_cid = _best_cid_for_cat(level, category_value)
    if best_cid is None:
        st.warning("No data found for this category/date range.")
        return None

    brandagg = _brand_agg(best_cid, level, category_value, start, end)
    if brandagg.empty:
        st.warning("No data for this category/date range.")
        return None

    scope = {
        "level": level,
        "level_label": CATEGORY_LABELS[level],
        "category_value": category_value,
        "metric_label": "Combined SOV",
        "date_min": str(start),
        "date_max": str(end),
        "name": (report_name.strip() or f"Category: {category_value}"),
    }

    # Full leaderboard — no focus brand; clear is_client so no "YOU" tag
    cl = transforms.combined_leaderboard(brandagg, "page_1", focus_brand=None, top=15)
    cl = cl.copy()
    cl["is_client"] = False  # no "YOU" in category mode

    nbrands = int(brandagg["brand"].nunique())
    top1 = cl.iloc[0] if not cl.empty else None

    # Sub-category leaders (child level)
    lvl_n = int(level.rsplit("l", 1)[-1])
    child_level = f"digital_shelf_l{lvl_n + 1}" if lvl_n < 10 else None
    leaders = (data.get_category_leaders(best_cid, child_level, level,
                                         category_value, start, end,
                                         "all", "page_1", "")
               if child_level else None)
    if leaders is not None and leaders.empty:
        leaders = None

    # Top keywords by demand volume
    kb = _kb(best_cid, level, category_value, start, end)
    kp_rows: list[dict] = []
    if not kb.empty and "search_term" in kb.columns and "no_of_crawls" in kb.columns:
        kw_vol = (kb.groupby("search_term")["no_of_crawls"]
                  .max().sort_values(ascending=False).head(10))
        kp_rows = [{"kw": kw, "crawls": float(v)} for kw, v in kw_vol.items()]

    context = {
        "scope": {"category_value": category_value},
        "hero": {
            "top_brand": str(top1["brand"]) if top1 is not None else "—",
            "top_sov": float(top1["combined_sov"]) if top1 is not None else 0.0,
            "brands": nbrands,
            "keywords": selected_kw,
        },
        "leaderboard": [{"brand": str(r["brand"]), "sov": float(r["combined_sov"])}
                        for _, r in cl.iterrows()],
        "subcategory_leaders": ([{"sub": r["category"], "leader": r["leader"],
                                   "leader_sov": float(r["leader_sov"])}
                                  for _, r in leaders.head(8).iterrows()]
                                 if leaders is not None else []),
        "top_keywords": kp_rows,
    }

    with st.spinner("Writing category insights…"):
        ins, src = narrative.generate_category_insights(context)

    themed = {
        "hero": context["hero"],
        "leaderboard": [{"brand": r["brand"],
                          "combined_sov": float(r["combined_sov"]),
                          "organic_pts": float(r["organic_pts"]),
                          "paid_pts": float(r["paid_pts"]),
                          "is_focus": False}
                         for _, r in cl.iterrows()],
        "subcats": ([{"sub": r["category"], "leader": r["leader"],
                      "leader_sov": float(r["leader_sov"])}
                     for _, r in leaders.head(6).iterrows()]
                    if leaders is not None else []),
        "keywords": kp_rows,
    }

    html = report.build_category_report(scope, ins, themed, src)
    return {"mode": "category", "scope": scope, "html": html, "source": src}


if generate:
    st.session_state.pop("pdf_bytes", None)
    start, end = _dates()
    if start is None:
        st.warning("Please pick a start and end date.")
    else:
        if is_category_mode:
            rep_ = _build_category_report(start, end)
        else:
            rep_ = _build_deepdive(start, end)
        st.session_state["report"] = rep_
        if rep_:
            try:
                # Normalise scope so history always has brand_label + category
                _scope_for_hist = dict(rep_["scope"])
                if "brand_label" not in _scope_for_hist:
                    _scope_for_hist["brand_label"] = "📊 Category"
                history.save_report(_scope_for_hist, rep_["html"],
                                    rep_.get("source", ""))
            except Exception:
                pass


# ── Render ─────────────────────────────────────────────────────────────--
rep = st.session_state.get("report")
if not rep:
    st.info("👈 Pick a **category** (L1, optional L2), then a **brand** that "
            "competes in it, and click **Generate report**. "
            "Past reports are saved under **📜 Report history** in the sidebar.")
    st.stop()

if rep.get("mode") == "history":
    st.info(f"📜 Viewing a saved report — **{rep['scope'].get('brand_label','')}** · "
            f"{rep['scope'].get('category_value','')} · generated {rep.get('ts','')}")
elif rep.get("mode") == "category":
    st.info(f"📊 **Category Report** — {rep['scope'].get('category_value','')} · "
            f"{rep['scope'].get('date_min','')} → {rep['scope'].get('date_max','')}")

components.html(rep["html"], height=5200, scrolling=True)

if rep.get("mode") not in ("history", "category") and "kp" in rep:
    with st.expander("🛒 Product shelf — see the products winning a keyword"):
        kws = rep["kp"]["search_term"].tolist()
        if kws:
            kw = st.selectbox("Keyword", kws, key="shelf_kw")
            if st.button("Load shelf", key="load_shelf"):
                with st.spinner("Fetching products…"):
                    sku = data.get_sku_detail(cid, kw)
                if sku.empty:
                    st.info("No product listings found.")
                else:
                    show = sku[sku["listing_page"] == 1][
                        ["overall_listing_rank", "listing_type", "brand", "title"]].head(20)
                    show = show.rename(columns={
                        "overall_listing_rank": "Rank", "listing_type": "Type",
                        "brand": "Brand", "title": "Title"})
                    st.dataframe(_num(show), use_container_width=True, hide_index=True)

# ── SKU Optimizer ─────────────────────────────────────────────────────--
# Shown for any brand deepdive report — client or competitor — whenever a
# focus brand is set.  focus_is_client gate intentionally removed.
if rep.get("mode") == "deepdive" and focus_brand:
    st.divider()
    with st.expander("🛍️ SKU Optimizer — Rufus-style listing recommendations",
                     expanded=False):
        st.caption(
            f"Pick an ASIN from **{focus_brand}**'s tracked products. "
            "The optimizer analyses the current title against page-1 keyword "
            "rankings and competitor listings, then generates an optimized title, "
            "5 benefit bullets, backend keywords, and Rufus Q&A prep — "
            "ready to share with the brand's content team.")

        asins_df = _asins(cid, level, category_value, focus_brand)

        if asins_df.empty:
            st.info("No tracked ASINs found for this brand in this category. "
                    "Try expanding the date range or switching to 'All categories'.")
        else:
            sku_opts = asins_df["sku"].tolist()
            # Build a per-SKU info dict for the product card
            sku_info = {
                r["sku"]: {
                    "title": str(r.get("title", "") or ""),
                    "image_url": str(r.get("image_url", "") or ""),
                    "product_page_url": str(r.get("product_page_url", "") or ""),
                    "keywords": int(r.get("keywords", 0) or 0),
                    "best_rank": int(r.get("best_rank", 0) or 0),
                    "page1_hits": int(r.get("page1_hits", 0) or 0),
                }
                for _, r in asins_df.iterrows()
            }

            sel_sku = st.selectbox(
                "Choose an ASIN to optimize", sku_opts,
                format_func=lambda s: (
                    f"{s}  —  {sku_info.get(s, {}).get('title', '')[:60]}"),
                key="opt_sku_sel")

            # ── Product card ────────────────────────────────────────────
            info = sku_info.get(sel_sku, {})
            c_img, c_text = st.columns([1, 4])
            with c_img:
                img = info.get("image_url", "")
                if img:
                    st.image(img, width=130)
                else:
                    st.markdown(
                        "<div style='width:130px;height:130px;background:#ece4f5;"
                        "border-radius:8px;display:flex;align-items:center;"
                        "justify-content:center;font-size:2.5rem;'>📦</div>",
                        unsafe_allow_html=True)
            with c_text:
                product_title = info.get("title", sel_sku)
                url = info.get("product_page_url", "")
                link = (f' <a href="{url}" target="_blank" '
                        f'style="color:#5AAFFE;font-size:.82em">↗ View on Amazon</a>'
                        if url else "")
                st.markdown(
                    f"<p style='font-weight:600;margin:0 0 6px'>"
                    f"{product_title[:160]}</p>{link}",
                    unsafe_allow_html=True)
                st.caption(
                    f"ASIN: `{sel_sku}` &nbsp;·&nbsp; "
                    f"Keywords tracked: **{info.get('keywords', 0)}** &nbsp;·&nbsp; "
                    f"Best rank: **#{info.get('best_rank', '—')}** &nbsp;·&nbsp; "
                    f"Page-1 appearances: **{info.get('page1_hits', 0)}**")
            st.markdown("")

            if st.button("✨ Optimize listing title & content", key="sku_opt_btn",
                         type="primary", use_container_width=False):
                with st.spinner("Pulling keyword data and generating recommendations…"):
                    current_title = info.get("title", "")

                    # Page-1 keywords for this ASIN
                    kw_df = _sku_kws(cid, sel_sku)
                    ranking_kws = kw_df.to_dict("records") if not kw_df.empty else []

                    # Competitor titles (top ASINs on the same keywords)
                    comp_df = _comp_titles(cid, sel_sku)
                    comp_title_list = [
                        str(r["title"]) for _, r in comp_df.iterrows()
                        if r.get("title") and str(r["title"]).strip()
                    ]

                    # Missing = high-vol category keywords where this ASIN doesn't rank
                    ranked_set = set(
                        str(r.get("search_term", "")).lower()
                        for r in ranking_kws
                    )
                    kp = rep.get("kp")
                    if kp is not None and not kp.empty and "search_term" in kp.columns:
                        sort_col = ("crawls" if "crawls" in kp.columns else
                                    kp.columns[1])
                        missing_kws = [
                            str(r["search_term"])
                            for _, r in kp.sort_values(sort_col, ascending=False).iterrows()
                            if str(r["search_term"]).lower() not in ranked_set
                        ][:15]
                    else:
                        missing_kws = []

                    result, src = sku_optimizer.optimize_sku(
                        sku=sel_sku,
                        current_title=current_title,
                        brand=focus_brand,
                        category=category_value,
                        ranking_keywords=ranking_kws,
                        competitor_titles=comp_title_list,
                        missing_keywords=missing_kws,
                    )
                    st.session_state["sku_opt"] = {
                        "sku": sel_sku,
                        "current_title": current_title,
                        "result": result,
                        "source": src,
                    }

            # ── Display results ──────────────────────────────────────────
            opt = st.session_state.get("sku_opt")
            if opt and opt.get("sku") == sel_sku:
                r = opt["result"]
                src_badge = ("🤖 AI-optimized · GPT" if opt["source"] == "openai"
                             else "📋 Rule-based · OpenAI not configured")
                st.caption(src_badge)

                # Title comparison
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.markdown("**Current title**")
                    st.code(opt["current_title"] or "(no title on record)",
                            language=None)
                with tc2:
                    opt_t = r.get("optimized_title", "")
                    char_color = "green" if len(opt_t) <= 200 else "red"
                    st.markdown(
                        f"**Optimized title ✨** "
                        f"<span style='color:{char_color};font-size:.82em'>"
                        f"({len(opt_t)}/200 chars)</span>",
                        unsafe_allow_html=True)
                    st.code(opt_t, language=None)

                if r.get("analysis"):
                    st.info(f"📊 **Why this matters:** {r['analysis']}")

                # Bullet points
                bullets = r.get("bullets", [])
                if bullets:
                    st.markdown("**Recommended bullet points**")
                    for i, b in enumerate(bullets, 1):
                        st.markdown(f"{i}. {b}")

                # Backend keywords + byte counter
                bk = r.get("backend_keywords", "")
                if bk:
                    bk_bytes = len(bk.encode())
                    bc1, bc2 = st.columns([3, 1])
                    with bc1:
                        st.markdown("**Backend search terms**")
                        st.text_area(
                            "Paste into Seller Central → Keywords → Search Terms",
                            bk, height=90, key="bk_field")
                    with bc2:
                        bk_color = "normal" if bk_bytes <= 249 else "inverse"
                        st.metric("Bytes used", f"{bk_bytes} / 249",
                                  delta=f"{249 - bk_bytes} remaining",
                                  delta_color=bk_color)

                # Rufus Q&A
                qa_list = r.get("rufus_qa", [])
                if qa_list:
                    st.markdown("**Rufus Q&A — prepare your listing for these questions**")
                    st.caption("These are questions Amazon Rufus shoppers commonly ask. "
                               "Work these answers into your listing copy.")
                    for qa in qa_list:
                        with st.expander(f"❓ {qa.get('q', '')}"):
                            st.write(qa.get("a", ""))

                # Download brief
                brief = sku_optimizer.build_brief_html(
                    sku=sel_sku,
                    current_title=opt["current_title"],
                    brand=focus_brand,
                    category=category_value,
                    result=r,
                )
                st.download_button(
                    "⬇️ Download optimization brief (HTML)",
                    brief,
                    file_name=f"sku_optimization_{sel_sku}.html",
                    mime="text/html",
                    use_container_width=True,
                    key="sku_opt_dl",
                )


# ── Downloads ──────────────────────────────────────────────────────────--
st.markdown("### 📤 Download & share")
d1, d2 = st.columns(2)
_nm = (rep["scope"].get("name")
       or f"{rep['scope'].get('brand_label', '')} {rep['scope'].get('category_value', '')}")
fname = "".join(c if (c.isalnum() or c in " -_") else "_"
                for c in _nm).strip().replace(" ", "_") or "report"
with d1:
    st.download_button("⬇️ Download interactive HTML", rep["html"],
                       file_name=f"{fname}.html", mime="text/html",
                       use_container_width=True)
with d2:
    # PDF requires a local Chromium install (playwright). On Streamlit Community
    # Cloud this isn't available — show a friendly note instead.
    _playwright_ok = False
    try:
        import playwright  # noqa: F401
        _playwright_ok = True
    except ImportError:
        pass

    if not _playwright_ok:
        st.info("💡 PDF export requires a local install.\n\n"
                "Use **Download HTML** above — it opens perfectly in any browser "
                "and can be printed to PDF from there (Cmd+P → Save as PDF).",
                icon="ℹ️")
    elif "pdf_bytes" in st.session_state:
        st.download_button("⬇️ Download PDF", st.session_state["pdf_bytes"],
                           file_name=f"{fname}.pdf", mime="application/pdf",
                           use_container_width=True)
    elif st.button("🖨️ Prepare PDF", use_container_width=True):
        try:
            with st.spinner("Rendering PDF…"):
                out = Path(f"/tmp/{fname}.pdf")
                report.html_to_pdf(rep["html"], out)
                st.session_state["pdf_bytes"] = out.read_bytes()
            st.rerun()
        except Exception as e:
            st.error(f"Could not render PDF: {e}\n\nInstall once: "
                     "`python -m playwright install chromium`. HTML always works.")
