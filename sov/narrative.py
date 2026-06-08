"""Narrative generation.

Uses OpenAI when OPENAI_API_KEY is set; otherwise falls back to a deterministic
rule-based summary so the report always has readable insights.
"""
from __future__ import annotations

import json

from config import SETTINGS


SECTION_KEYS = ["verdict", "leaderboard", "organic_paid", "subcategories",
                "keywords", "incrementality", "readiness", "how_you_win"]


def generate_sectioned_insights(context: dict) -> tuple[dict, str]:
    """Return ({section_key: insight_text}, source). One sharp insight per
    report section, in CommerceIQ style, grounded only in the provided numbers."""
    if SETTINGS.openai_ready:
        try:
            return _openai_sectioned(context), "openai"
        except Exception:
            return _template_sectioned(context), "template"
    return _template_sectioned(context), "template"


def _openai_sectioned(context: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    system = (
        "You are a senior retail-media analyst at CommerceIQ writing a "
        "Share-of-Search positioning report shown TO a brand about its presence "
        "on Amazon. Write sharp, declarative, executive insight — name specific "
        "competitors and cite the exact numbers provided. Use ONLY the data in "
        "the JSON; never invent figures, brands, categories, or client IDs. "
        "Tone: confident, competitive but not hostile, action-oriented. "
        "Return a JSON object with EXACTLY these string keys: "
        + ", ".join(SECTION_KEYS) + ". Guidance per key: "
        "'verdict' = 2-3 sentence headline on where the brand stands and the gap "
        "to the leader; 'leaderboard' = who is ahead and by how much; "
        "'organic_paid' = read on organic vs paid share and which lever is the "
        "faster opening; 'subcategories' = which sub-categories the brand can "
        "win vs where rivals dominate (note no single brand owns every "
        "sub-category); 'keywords' = the biggest keyword opportunities / "
        "whitespace; 'incrementality' = how much presence is earned (organic) vs "
        "bought (paid); 'readiness' = catalog/content coverage gaps; "
        "'how_you_win' = a 2-4 sentence playbook to close the gap and a nudge to "
        "talk to CommerceIQ (do NOT name specific CommerceIQ products). "
        "Each value 1-3 sentences, under 60 words. "
        "CRITICAL: cite ONLY the exact numbers in the JSON. NEVER say a brand has "
        "'no', 'zero', 'negligible', or 'no measurable' share unless the value is "
        "exactly 0 — if it has 1% say 1%. The single SOV number is `sov.combined_pct`; "
        "organic and paid are POINTS of that one number (they add up to it), so never "
        "present them as separate competing SOV figures."
    )
    resp = client.chat.completions.create(
        model=SETTINGS.openai_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(context, default=str)}],
        temperature=0.4, max_tokens=900,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    return {k: str(data.get(k, "")).strip() for k in SECTION_KEYS}


def _template_sectioned(ctx: dict) -> dict:
    brand = ctx.get("scope", {}).get("brand_label", "Your brand")
    cat = ctx.get("scope", {}).get("category_value", "this category")
    sv = ctx.get("sov", {})
    combined = sv.get("combined_pct", 0.0)
    org = sv.get("organic_pts", 0.0)
    paid = sv.get("paid_pts", 0.0)
    rank = sv.get("rank")
    rivals = ctx.get("top_brands_ahead", [])
    lead = rivals[0] if rivals else None
    subs = ctx.get("subcategory_leaders", [])
    kws = ctx.get("top_keywords", [])
    cov = ctx.get("coverage", {})
    ae = ctx.get("ad_efficiency")

    verdict = (f"In {cat}, {brand} holds {combined:.1f}% Share of Voice"
               + (f", ranking #{rank}." if rank else ".")
               + (f" Leader: {lead['brand']} at {lead['sov']:.1f}%." if lead else ""))
    organic_paid = (f"{brand}'s {combined:.1f}% Share of Voice is {org:.1f} pts organic "
                    f"and {paid:.1f} pts paid. Paid is the faster lever — open to any "
                    "brand willing to target the right terms.")
    leaderboard = ("Ahead of you: "
                   + "; ".join(f"{r['brand']} {r['sov']:.1f}%" for r in rivals[:3])
                   if rivals else f"{brand} leads this category.")
    if subs:
        won = [s for s in subs if s.get("focus_sov", 0) >= s.get("leader_sov", 0)]
        subcategories = (f"No single brand owns every sub-category. Strongest opening: "
                         f"{subs[0]['category']}."
                         + (f" You already lead {len(won)}." if won else ""))
    else:
        subcategories = "Sub-category breakdown is in the table below."
    weak = [m for m in kws if m.get("client_sov", 0) < 10][:3]
    keywords = ("Whitespace (high volume, low share): "
                + "; ".join(m["search_term"] for m in weak) if weak
                else "See the keyword opportunities below.")
    incrementality = (
        f"{ae['paid_sov_pct']:.0f}% paid Share of Voice at ROAS {ae['roas']:.1f}x; "
        f"{ae['incremental_pct']:.0f}% of ad-driven sales are incremental "
        f"(iROAS {ae['iroas']:.1f}x)." if ae else
        "Ad-efficiency data is available for this brand's own ad account only.")
    readiness = (f"You appear in {cov.get('present', 0)} of {cov.get('total', 0)} "
                 f"tracked keywords ({cov.get('pct', 0):.0f}% coverage) — expanding "
                 "coverage is the clearest growth path.")
    how_you_win = ("Defend the keywords you lead, win the high-volume keywords where "
                   "you're absent, and balance organic content with targeted paid. "
                   "CommerceIQ can turn this into an automated plan — let's talk.")
    return {"verdict": verdict, "leaderboard": leaderboard,
            "organic_paid": organic_paid, "subcategories": subcategories,
            "keywords": keywords, "incrementality": incrementality,
            "readiness": readiness, "how_you_win": how_you_win}


CATEGORY_SECTION_KEYS = ["verdict", "leaderboard", "organic_paid",
                          "subcategories", "keywords", "how_you_win"]


def generate_category_insights(context: dict) -> tuple[dict, str]:
    """Category-mode insights — no focus brand. Returns ({section_key: text}, source)."""
    if SETTINGS.openai_ready:
        try:
            return _openai_category(context), "openai"
        except Exception:
            return _template_category(context), "template"
    return _template_category(context), "template"


def _openai_category(context: dict) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    system = (
        "You are a senior retail-media analyst at CommerceIQ writing a Category "
        "Share-of-Search intelligence report. This is a CATEGORY landscape view — "
        "there is NO single focus brand. Write sharp, executive insights describing "
        "who owns the category, where share is concentrated vs fragmented, and where "
        "the opportunity is for any brand competing in this space. "
        "Use ONLY the numbers in the JSON. Never invent figures or brand names. "
        "Tone: authoritative, data-led, designed to make a brand want to know "
        "exactly where they stand. "
        "Return a JSON object with EXACTLY these string keys: "
        + ", ".join(CATEGORY_SECTION_KEYS) + ". "
        "Guidance per key: "
        "'verdict' = 2-3 sentence headline naming the leader and describing competitive intensity; "
        "'leaderboard' = what the top brand SOV levels reveal about market concentration; "
        "'organic_paid' = how organic vs paid share are balanced across the category; "
        "'subcategories' = which sub-categories are contested vs dominated; "
        "'keywords' = what the highest-demand terms reveal about shopper intent; "
        "'how_you_win' = 2-4 sentence playbook for gaining share in this category "
        "plus a nudge to talk to CommerceIQ (do NOT name specific products). "
        "Each value 1-3 sentences, under 60 words. Cite only exact numbers from JSON."
    )
    resp = client.chat.completions.create(
        model=SETTINGS.openai_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(context, default=str)}],
        temperature=0.4, max_tokens=800,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    return {k: str(data.get(k, "")).strip() for k in CATEGORY_SECTION_KEYS}


def _template_category(ctx: dict) -> dict:
    cat = ctx.get("scope", {}).get("category_value", "this category")
    lb = ctx.get("leaderboard", [])
    top = lb[0] if lb else None
    top2 = lb[1] if len(lb) > 1 else None
    h = ctx.get("hero", {})
    nbr = h.get("brands", 0)
    nkw = h.get("keywords", 0)
    subs = ctx.get("subcategory_leaders", [])
    kws = ctx.get("top_keywords", [])

    verdict = (
        f"{top['brand']} leads {cat} with {top['sov']:.1f}% Combined Share of Voice"
        + (f", ahead of {top2['brand']} at {top2['sov']:.1f}%." if top2 else ".")
        + f" {nbr:,} brands compete across {nkw:,} tracked keywords."
        if top else f"No clear leader has emerged in {cat} — {nbr:,} brands are competing."
    )
    leaderboard = (
        f"The top brand in {cat} holds {top['sov']:.1f}% share — "
        + (f"a {'concentrated' if top['sov'] > 20 else 'fragmented'} market where "
           f"the top 3 brands {'dominate' if top['sov'] > 15 else 'share'} the space.")
        if top else "Share is fragmented across many brands."
    )
    organic_paid = (
        f"The top brands in {cat} win through a mix of organic content coverage "
        "and paid search placements. Organic share compounds over time; paid share "
        "is available immediately to any brand investing in the right search terms."
    )
    subcategories = (
        f"No single brand dominates every sub-category in {cat}. "
        + (f"{subs[0]['leader']} leads {subs[0]['sub']}, but challenger brands "
           "find their opening in adjacent sub-categories." if subs else
           "This creates multiple entry points for challenger brands.")
    )
    keywords = (
        "Highest-demand search terms: " + ", ".join(f'"{k["kw"]}"' for k in kws[:3]) + "."
        if kws else f"High shopper intent across {nkw:,} tracked keywords in {cat}."
    )
    how_you_win = (
        f"To win share in {cat}, rank organically on the highest-traffic terms and "
        "use sponsored placements to capture searches where organic rank is low. "
        "CommerceIQ can show exactly where your brand stands today and automate "
        "the path to more share — across both organic content and paid campaigns."
    )
    return {"verdict": verdict, "leaderboard": leaderboard,
            "organic_paid": organic_paid, "subcategories": subcategories,
            "keywords": keywords, "how_you_win": how_you_win}


def generate_narrative(context: dict) -> tuple[str, str]:
    """Return (narrative_markdown, source) where source is 'openai' or 'template'."""
    if SETTINGS.openai_ready:
        try:
            return _openai_narrative(context), "openai"
        except Exception as e:
            return (_template_narrative(context)
                    + f"\n\n*(Note: OpenAI was unavailable — {type(e).__name__}. "
                    "Showing a rule-based summary instead.)*"), "template"
    return _template_narrative(context), "template"


# ── OpenAI path ──────────────────────────────────────────────────────────
def _openai_narrative(context: dict) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    system = (
        "You are a retail-media analyst at CommerceIQ writing the insights "
        "section of a Share-of-Voice (SOV) positioning report shown TO a brand "
        "about its presence on Amazon. Be precise, executive-ready, and "
        "specific with numbers. Use the provided data ONLY — never invent "
        "figures, brand names, or categories. Output GitHub-flavored Markdown "
        "with short sections: a 1-2 sentence headline, 'What's working', "
        "'Where you're losing share', and 'Recommended actions' (2-4 bullets). "
        "The tone should make the brand want to act on the gaps. Do not mention "
        "client IDs. Keep it under ~250 words."
    )
    user = (
        "Here is the computed SOV data as JSON. Write the insights.\n\n"
        + json.dumps(context, default=str, indent=2)
    )
    resp = client.chat.completions.create(
        model=SETTINGS.openai_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.3,
        max_tokens=700,
    )
    return resp.choices[0].message.content.strip()


# ── Template fallback ──────────────────────────────────────────────────────
def _template_narrative(ctx: dict) -> str:
    if ctx.get("overview"):
        return _template_overview(ctx)
    k = ctx.get("kpis", {})
    scope = ctx.get("scope", {})
    client_brand = k.get("client_brand") or "Your brand"
    client_sov = k.get("client_sov", 0.0)
    rank = k.get("client_rank")
    top_brand = k.get("top_brand")
    top_sov = k.get("top_brand_sov", 0.0)
    cat = scope.get("category_value", "the selected category")
    lens = scope.get("metric_label", "Combined")

    lines = [f"### Headline",
             f"In **{cat}** ({lens} SOV), **{client_brand}** holds "
             f"**{client_sov:.1f}%** share of voice"
             + (f", ranking **#{rank}** of {k.get('brands', 0)} brands."
                if rank else ".")]

    if top_brand and rank and rank > 1:
        lines.append(f"The category leader is **{top_brand}** at "
                     f"**{top_sov:.1f}%** — a gap of "
                     f"**{top_sov - client_sov:.1f} pts**.")

    movers = ctx.get("top_keywords", [])[:5]
    if movers:
        lines.append("\n### Top keywords by volume")
        for m in movers:
            lines.append(f"- **{m['search_term']}** — your SOV "
                         f"{m['client_sov']:.1f}% ({m['crawls']:.0f} crawls)")

    weak = [m for m in ctx.get("top_keywords", []) if m["client_sov"] < 10][:3]
    if weak:
        lines.append("\n### Whitespace (high volume, low share)")
        for m in weak:
            lines.append(f"- **{m['search_term']}** — only "
                         f"{m['client_sov']:.1f}% despite {m['crawls']:.0f} crawls")

    lines.append("\n### Recommended actions")
    if rank and rank > 1:
        lines.append(f"- Close the gap to {top_brand}: target the high-volume "
                     "keywords above with Sponsored Products bids.")
    lines.append("- Defend keywords where you already lead to protect share.")
    if weak:
        lines.append("- Prioritize the whitespace keywords for new ad coverage.")
    return "\n".join(lines)


def _template_overview(ctx: dict) -> str:
    brand = ctx.get("scope", {}).get("brand_label", "Your brand")
    ov = ctx.get("overview", [])
    if not ov:
        return "No category data available for the selected scope."
    ranked = sorted(ov, key=lambda r: r.get("client_sov", 0), reverse=True)
    best = ranked[0]
    worst = [r for r in ranked if r.get("crawls", 0) > 0][-1]
    lines = [
        "### Headline",
        f"Across **{len(ov)}** categories, **{brand}** is strongest in "
        f"**{best['category']}** at **{best['client_sov']:.1f}%** SOV and weakest in "
        f"**{worst['category']}** at **{worst['client_sov']:.1f}%**.",
        "\n### Strongest categories",
    ]
    for r in ranked[:3]:
        lines.append(f"- **{r['category']}** — {r['client_sov']:.1f}% SOV "
                     f"({r['keywords']} keywords)")
    lines.append("\n### Biggest opportunities (high volume, low share)")
    opp = sorted(ov, key=lambda r: r.get("crawls", 0) * (1 - r.get("client_sov", 0) / 100),
                 reverse=True)[:3]
    for r in opp:
        lines.append(f"- **{r['category']}** — only {r['client_sov']:.1f}% SOV "
                     f"across {r['keywords']} keywords")
    lines.append("\n### Recommended actions")
    lines.append("- Drill into the high-opportunity categories to find the "
                 "specific keywords where competitors are winning.")
    lines.append("- Protect and extend the lead in your strongest categories.")
    return "\n".join(lines)
