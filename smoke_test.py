"""Pipeline smoke test (no Streamlit). Run: python smoke_test.py"""
from __future__ import annotations

import datetime as dt
import warnings

warnings.filterwarnings("ignore")

from sov import data, narrative, report, transforms

brands = data.get_brands()
focus = brands[0]
cid, focus_brand = focus["client_id"], focus["brand"]
lo, hi = data.get_date_bounds(cid)
start = max(lo, hi - dt.timedelta(days=120))
level = "digital_shelf_l1"
cat = data.get_category_values(level, cid)[0][0]
print(f"brand={focus_brand} | category={cat} | {start}->{hi}")

ba = data.get_brand_agg(cid, level, cat, start, hi)
op = transforms.organic_paid_leaderboard(ba, "page_1", focus_brand)
print(f"organic sum={op['organic_sov'].sum():.1f}  paid sum={op['paid_sov'].sum():.1f} (each ~100)")
kb = data.get_keyword_brand_agg(cid, level, cat, start, hi)
cov = transforms.coverage(kb, "all", "page_1", focus_brand)
print("coverage:", cov)
leaders = data.get_category_leaders(cid, "digital_shelf_l2", level, cat, start, hi,
                                    "all", "page_1", focus_brand)
print(f"sub-category leaders rows={len(leaders)}")
if not leaders.empty:
    print(leaders.head(3)[["category", "leader", "leader_sov", "focus_sov"]].to_string(index=False))

rel = data.get_relevant_set_leaderboard(cid, level, cat, start, hi, "all", "page_1", focus_brand)
ws = transforms.top_keywords(kb, 8, "all", "page_1", "opportunity", focus_brand)
fop = op[op["is_client"]]
org = float(fop["organic_sov"].iloc[0]) if not fop.empty else 0
paid = float(fop["paid_sov"].iloc[0]) if not fop.empty else 0
context = {
    "scope": {"brand_label": focus_brand, "category_value": cat, "metric_label": "Combined"},
    "kpis": {"client_sov": float(rel[rel.is_focus]["sov_pct"].iloc[0]) if (not rel.empty and rel.is_focus.any()) else 0},
    "top_brands_ahead": [{"brand": str(r["brand"]), "sov": float(r["sov_pct"])}
                         for _, r in rel[~rel.is_focus].head(3).iterrows()] if not rel.empty else [],
    "organic_paid_focus": {"organic_sov": org, "paid_sov": paid},
    "subcategory_leaders": leaders.head(6).to_dict("records") if not leaders.empty else [],
    "top_keywords": ws.to_dict("records"),
    "incrementality_summary": {"paid_share_pct": 100 * paid / (org + paid) if (org + paid) else 0},
    "coverage": cov,
}
ins, src = narrative.generate_sectioned_insights(context)
print(f"\nINSIGHTS source = {src}")
print("verdict:", ins["verdict"][:200])
print("organic_paid:", ins["organic_paid"][:160])

sections = [{"title": "Organic vs Paid", "insight": ins["organic_paid"], "table": op.head(8)},
            {"title": "Sub-category leaders", "insight": ins["subcategories"],
             "table": leaders.head(8) if not leaders.empty else None}]
html = report.build_sectioned_report(
    {"brand_label": focus_brand, "level_label": "Category L1", "category_value": cat,
     "metric_label": "Combined", "cutoff_label": "Page 1",
     "date_min": str(start), "date_max": str(hi)},
    [("Organic SOV", f"{org:.1f}%", "#5AAFFE"), ("Paid SOV", f"{paid:.1f}%", "#210235")],
    ins["verdict"], sections, ins["how_you_win"], src)
with open("/tmp/ciq_sectioned_report.html", "w") as f:
    f.write(html)
print(f"\nsectioned report: {len(html):,} bytes -> /tmp/ciq_sectioned_report.html")
assert "Talk to CommerceIQ" in html and "01</span>" in html and "How you win" in html
print("ALL SMOKE CHECKS PASSED ✅")
