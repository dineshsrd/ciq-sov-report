"""SKU content optimizer — Rufus-style listing optimization.

Given a brand's ASIN, its current title, page-1 ranking keywords, and
competitor titles, uses GPT to generate an optimized Amazon listing:
optimized title, 5 benefit-led bullets, backend keywords, and Rufus Q&A.

Falls back to a deterministic template when OpenAI is not configured.
"""
from __future__ import annotations

import html as _html
import json

from config import SETTINGS


def optimize_sku(
    sku: str,
    current_title: str,
    brand: str,
    category: str,
    ranking_keywords: list[dict],   # [{search_term, best_rank, page1_hits, days_tracked}]
    competitor_titles: list[str],   # [title, ...]
    missing_keywords: list[str],    # high-vol category keywords this ASIN doesn't rank for
) -> tuple[dict, str]:
    """Returns (result_dict, source).  source = 'openai' | 'template'."""
    if SETTINGS.openai_ready:
        try:
            return (_openai_optimize(sku, current_title, brand, category,
                                     ranking_keywords, competitor_titles,
                                     missing_keywords),
                    "openai")
        except Exception:
            pass
    return (_template_optimize(sku, current_title, brand, category,
                                ranking_keywords, missing_keywords),
            "template")


# ── OpenAI path ──────────────────────────────────────────────────────────
def _openai_optimize(sku, current_title, brand, category, ranking_kws,
                     comp_titles, missing_kws) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=SETTINGS.openai_api_key)

    context = {
        "sku": sku,
        "brand": brand,
        "category": category,
        "current_title": current_title,
        "top_ranking_keywords": [
            {"kw": str(r.get("search_term", "")),
             "page1_hits": int(r.get("page1_hits", 0)),
             "best_rank": int(r.get("best_rank", 999))}
            for r in ranking_kws[:20]
        ],
        "competitor_titles": [str(t) for t in comp_titles[:5]],
        "missing_high_volume_keywords": [str(k) for k in missing_kws[:15]],
    }

    system = (
        "You are an Amazon search-rank optimization expert at CommerceIQ. "
        "Your ONLY goal is to improve this product's Amazon search rank — "
        "helping it appear higher (ideally page 1, position 1–3) for the "
        "provided target keywords. You do this by crafting listing copy that "
        "maximises Amazon A10 index weight: exact-match primary keyword first, "
        "high-value secondary keywords woven in naturally, no filler words.\n\n"
        "Return a JSON object with EXACTLY these keys:\n"
        "  'analysis': 2–3 sentences. Explain which high-volume keywords the "
        "current title fails to index for, and what the title change will do to "
        "rank for those terms.\n"
        "  'optimized_title': Rewritten Amazon title. Hard rules: ≤200 chars; "
        "Brand name first, then the exact primary keyword phrase, then the most "
        "important differentiator; be specific (pack size / count / format where "
        "inferable from context); readable as a sentence; NO keyword stuffing.\n"
        "  'bullets': JSON array of exactly 5 strings. Each: ALL-CAPS benefit "
        "hook (3–5 words), dash, then shopper-facing sentence that embeds "
        "1–2 target keywords. Max 200 chars each.\n"
        "  'backend_keywords': Single space-separated string of search terms "
        "NOT already present in title/bullets — prioritise the "
        "'missing_high_volume_keywords' list. Max 249 bytes total.\n"
        "  'rufus_qa': JSON array of exactly 3 objects {\"q\": ..., \"a\": ...}. "
        "Questions Amazon Rufus shoppers ask (e.g. 'Is this good for X?', "
        "'How does this compare to Y?'). Answers ≤40 words, concrete and "
        "product-specific — Rufus surfaces these in conversational search.\n"
        "Use only provided data — do not invent specs or claims."
    )

    resp = client.chat.completions.create(
        model=SETTINGS.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, default=str)},
        ],
        temperature=0.45,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    raw = json.loads(resp.choices[0].message.content)

    # Normalise bullets / rufus_qa (some models return them as JSON strings)
    bullets = raw.get("bullets", [])
    if isinstance(bullets, str):
        try:
            bullets = json.loads(bullets)
        except Exception:
            bullets = [b.strip("•- ") for b in bullets.split("\n") if b.strip()]

    rufus_qa = raw.get("rufus_qa", [])
    if isinstance(rufus_qa, str):
        try:
            rufus_qa = json.loads(rufus_qa)
        except Exception:
            rufus_qa = []

    return {
        "analysis": str(raw.get("analysis", "")).strip(),
        "optimized_title": str(raw.get("optimized_title", "")).strip()[:200],
        "bullets": (bullets[:5] if isinstance(bullets, list) else []),
        "backend_keywords": str(raw.get("backend_keywords", "")).strip()[:249],
        "rufus_qa": (rufus_qa[:3] if isinstance(rufus_qa, list) else []),
    }


# ── Template / deterministic fallback ────────────────────────────────────
def _template_optimize(sku, current_title, brand, category,
                        ranking_kws, missing_kws) -> dict:
    top_kw = ranking_kws[0]["search_term"] if ranking_kws else category
    top_kws_str = ", ".join(str(r["search_term"]) for r in ranking_kws[:5])
    missing_str = " ".join(str(k) for k in missing_kws[:8])

    # Build a slightly improved title
    base = current_title[:80].rsplit(" — ", 1)[0].rsplit(" | ", 1)[0].strip()
    opt_title = f"{brand} {top_kw.title()}"
    if base and base.lower() not in opt_title.lower():
        opt_title += f" — {base}"
    if len(ranking_kws) > 1:
        opt_title += f" | {ranking_kws[1]['search_term'].title()}"
    opt_title = opt_title[:200]

    return {
        "analysis": (
            f"The current title doesn't front-load '{top_kw}', the highest "
            f"page-1 keyword for this ASIN. Amazon's A10 algorithm weights "
            "title position heavily — moving the primary keyword to characters "
            "1–80 can lift rank without any ad spend increase."
        ),
        "optimized_title": opt_title,
        "bullets": [
            f"TOP SEARCH VISIBILITY — Page-1 presence for: {top_kws_str}",
            f"TRUSTED {brand.upper()} QUALITY — Proven performer in {category}",
            "EASY TO USE — Ready out of the box; clear setup for everyday use",
            "GREAT VALUE — Compare with top alternatives in this category",
            "SATISFACTION BACKED — Quality commitment from the brand",
        ],
        "backend_keywords": (missing_str or top_kw)[:249],
        "rufus_qa": [
            {
                "q": f"Is this {top_kw} good for everyday use?",
                "a": (f"Yes — this {brand} {category} product holds page-1 rankings "
                      "for this search term and is designed for regular use."),
            },
            {
                "q": f"How does this compare to other {category} options?",
                "a": (f"{brand} maintains strong search visibility across "
                      f"{len(ranking_kws)} keywords, indicating broad relevance."),
            },
            {
                "q": "What makes this different from competitors?",
                "a": (f"Consistent page-1 presence across key {category} search "
                      "terms — a signal of high customer engagement."),
            },
        ],
    }


# ── Downloadable HTML brief ───────────────────────────────────────────────
def build_brief_html(sku: str, current_title: str, brand: str,
                     category: str, result: dict) -> str:
    """Return a self-contained HTML file the user can share with their content team."""
    e = _html.escape
    bullets_html = "\n".join(
        f"  <li>{e(str(b))}</li>" for b in result.get("bullets", [])
    )
    qa_html = "\n".join(
        f"""  <div class="qa">
    <p class="q">❓ {e(str(qa.get('q', '')))} </p>
    <p class="a">{e(str(qa.get('a', '')))}</p>
  </div>"""
        for qa in result.get("rufus_qa", [])
    )
    opt_title = result.get("optimized_title", "")
    bk = result.get("backend_keywords", "")
    opt_len = len(opt_title)
    bk_bytes = len(bk.encode())
    title_badge = ("✅ Good length" if opt_len <= 200
                   else f"⚠️ {opt_len} chars — aim for ≤ 200")
    bk_badge = ("✅ Within limit" if bk_bytes <= 249
                else f"⚠️ {bk_bytes} bytes — trim to fit 249-byte limit")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SKU Optimization Brief — {e(sku)}</title>
<style>
  body  {{ font-family: -apple-system, 'Segoe UI', sans-serif;
           max-width: 820px; margin: 40px auto; padding: 0 24px;
           color: #210235; line-height: 1.65; }}
  h1   {{ color: #210235; border-bottom: 3px solid #C231FF; padding-bottom: 10px; }}
  h2   {{ color: #210235; margin-top: 36px; }}
  .meta {{ color: #666; margin-bottom: 28px; }}
  .box  {{ background: #f5f1f9; border-radius: 10px; padding: 16px 20px; margin: 10px 0; }}
  .new  {{ background: #210235; color: #ddd; }}
  .new h3 {{ color: #C231FF; margin-top: 0; }}
  .new small {{ color: #888; font-size: .82em; }}
  .note {{ border-left: 4px solid #5AAFFE; padding: 12px 16px;
           background: #eef5ff; border-radius: 4px; }}
  code  {{ font-family: 'SFMono-Regular', Menlo, monospace;
           background: #ece4f5; padding: 2px 6px; border-radius: 4px; }}
  .bk   {{ display: block; background: #ece4f5; padding: 12px 16px;
           border-radius: 6px; word-break: break-word; font-family: monospace; }}
  ol li, ul li {{ margin: 8px 0; }}
  .qa   {{ border-left: 3px solid #5AAFFE; margin: 12px 0;
           padding: 10px 14px; background: #f0f8ff; border-radius: 0 6px 6px 0; }}
  .q    {{ font-weight: 700; margin: 0 0 4px; }}
  .a    {{ margin: 0; color: #444; }}
  .badge {{ display: inline-block; background: #C231FF; color: #fff;
            border-radius: 4px; padding: 1px 10px; font-size: .78em;
            font-weight: 700; margin-left: 8px; vertical-align: middle; }}
  footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #ddd;
            color: #999; font-size: .8em; }}
</style>
</head>
<body>

<h1>SKU Optimization Brief</h1>
<p class="meta">
  <b>ASIN:</b> {e(sku)} &nbsp;·&nbsp;
  <b>Brand:</b> {e(brand)} &nbsp;·&nbsp;
  <b>Category:</b> {e(category)}
</p>

<h2>📊 Analysis</h2>
<div class="note">{e(result.get('analysis', ''))}</div>

<h2>🏷️ Title</h2>
<div class="box">
  <b>Current</b><br>{e(current_title)}
</div>
<div class="box new">
  <h3>Optimized Title ✨ <span class="badge">{title_badge}</span></h3>
  {e(opt_title)}
  <small>Character count: {opt_len} / 200</small>
</div>

<h2>📝 Bullet Points</h2>
<ol>
{bullets_html}
</ol>

<h2>🔍 Backend Search Terms</h2>
<div class="box">
  <code class="bk">{e(bk)}</code>
  <p style="margin:8px 0 0; font-size:.84em; color:#666;">
    {bk_badge} &nbsp;·&nbsp; {bk_bytes} / 249 bytes
  </p>
</div>

<h2>🤖 Rufus Q&amp;A Preparation</h2>
<p style="color:#666; font-size:.9em; margin-bottom: 14px;">
  Prepare your listing content to answer these questions
  Amazon Rufus shoppers commonly ask.
</p>
{qa_html}

<footer>
  Generated by CommerceIQ SKU Optimizer &nbsp;·&nbsp;
  {e(brand)} &nbsp;·&nbsp; {e(category)} &nbsp;·&nbsp; ASIN {e(sku)}
</footer>
</body>
</html>"""
