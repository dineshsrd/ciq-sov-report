"""Assemble the shareable report: self-contained interactive HTML + PDF."""
from __future__ import annotations

import html as _html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from . import branding as B


# ── tiny markdown -> html (headings, bold, italic, bullets) ──────────────
def _md_to_html(md: str) -> str:
    out: list[str] = []
    in_list = False

    def inline(s: str) -> str:
        s = _html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        return s

    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif not line.strip():
            out.append("")
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _kpi_cards(cards: list[tuple[str, str, str]]) -> str:
    html = []
    for label, value, color in cards:
        html.append(
            f'<div class="kpi" style="border-top:4px solid {color}">'
            f'<div class="kpi-label">{_html.escape(label)}</div>'
            f'<div class="kpi-value">{_html.escape(str(value))}</div></div>'
        )
    return f'<div class="kpi-row">{"".join(html)}</div>'


def _table_html(df) -> str:
    if df is None or len(df) == 0:
        return ""
    d = df.copy()
    d.insert(0, "#", range(1, len(d) + 1))  # explicit row numbering
    return d.to_html(index=False, border=0, justify="left",
                     classes="data", escape=True)


def _render_table(title: str, df) -> str:
    return f'<h3 class="tbl-title">{_html.escape(title)}</h3>{_table_html(df)}'


def _scope_bits(scope: dict) -> str:
    return " &nbsp;·&nbsp; ".join(filter(None, [
        f"Brand <b>{_html.escape(str(scope.get('brand_label', '')))}</b>",
        f"{_html.escape(scope.get('level_label', ''))}: "
        f"<b>{_html.escape(str(scope.get('category_value', 'All categories')))}</b>",
        f"Lens: <b>{_html.escape(scope.get('metric_label', ''))}</b> "
        f"/ <b>{_html.escape(scope.get('cutoff_label', ''))}</b>",
        f"{_html.escape(str(scope.get('date_min', '')))} → "
        f"{_html.escape(str(scope.get('date_max', '')))}",
    ]))


_CTA = f"""<div class="cta">
    <div class="cta-title">Win more share in these categories.</div>
    <div class="cta-body">CommerceIQ helps brands grow Share of Search and sales
      across Amazon and the digital shelf — turning insights like these into
      automated action.</div>
    <a class="cta-btn" href="https://www.commerceiq.ai/demo">Talk to CommerceIQ →</a>
  </div>"""

_STYLE = f"""
  * {{ box-sizing: border-box; }}
  body {{ font-family: Inter, 'Helvetica Neue', Arial, sans-serif;
         color: {B.BLACK}; margin: 0; background: {B.WHITE}; }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 0 28px 56px; }}
  header {{ background: {B.DEEP_PURPLE}; color: {B.WHITE}; padding: 28px;
            border-bottom: 5px solid {B.ELECTRIC}; }}
  header h1 {{ margin: 0 0 6px; font-size: 24px; }}
  header .scope {{ color: #D9CFE8; font-size: 13px; }}
  h2.section {{ color: {B.DEEP_PURPLE}; margin-top: 40px; font-size: 19px; }}
  h2.section .num {{ color: {B.ELECTRIC}; font-weight: 800; }}
  .kpi-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 26px 0; }}
  .kpi {{ flex: 1; min-width: 150px; background: #FAFAFD; border: 1px solid #ECECF2;
          border-radius: 10px; padding: 16px; }}
  .kpi-label {{ font-size: 12px; color: #6A6A7A; text-transform: uppercase;
                letter-spacing: .04em; }}
  .kpi-value {{ font-size: 22px; font-weight: 700; color: {B.DEEP_PURPLE};
                margin-top: 6px; }}
  .verdict {{ background: #FBF7FF; border-left: 4px solid {B.ELECTRIC};
              border-radius: 8px; padding: 14px 22px; font-size: 15px;
              margin: 22px 0; }}
  .insight {{ color: #2B2440; font-size: 14.5px; margin: 4px 0 12px;
              border-left: 3px solid {B.SKY}; padding-left: 12px; }}
  .badge {{ display:inline-block; font-size: 11px; background: {B.ELECTRIC};
            color: {B.WHITE}; padding: 2px 8px; border-radius: 10px;
            vertical-align: middle; }}
  .chart {{ margin: 14px 0 30px; }}
  .tbl-title {{ color: {B.DEEP_PURPLE}; margin: 22px 0 8px; }}
  table.data {{ border-collapse: collapse; width: 100%; font-size: 13px;
                margin-bottom: 8px; }}
  table.data th {{ background: {B.DEEP_PURPLE}; color: {B.WHITE};
                   text-align: left; padding: 8px 10px; }}
  table.data td {{ border-bottom: 1px solid #ECECF2; padding: 7px 10px; }}
  table.data tr:nth-child(even) td {{ background: #FAFAFD; }}
  .cta {{ margin-top: 44px; background: {B.DEEP_PURPLE}; border-radius: 12px;
          padding: 26px 28px; color: {B.WHITE}; }}
  .cta-title {{ font-size: 20px; font-weight: 800; margin-bottom: 6px; }}
  .cta-body {{ color: #E2D8F0; font-size: 14px; max-width: 720px; }}
  .cta-btn {{ display: inline-block; margin-top: 16px; background: {B.ELECTRIC};
              color: {B.WHITE}; text-decoration: none; font-weight: 700;
              padding: 10px 18px; border-radius: 8px; }}
  footer {{ color: #9A9AAC; font-size: 12px; margin-top: 40px;
            border-top: 1px solid #ECECF2; padding-top: 14px; }}
  @media print {{ header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
"""


def _page(scope: dict, title: str, cards: list, body_html: str,
          src_badge: str, plotly_head: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)} — {_html.escape(str(scope.get('category_value', '')))}</title>
{plotly_head}
<style>{_STYLE}</style></head>
<body>
<header>
  <h1>{_html.escape(title)} <span style="font-size:15px;font-weight:400;color:#D9CFE8">·
    {_html.escape(str(scope.get('brand_label', '')))}</span></h1>
  <div class="scope">{_scope_bits(scope)}</div>
</header>
<div class="wrap">
  {_kpi_cards(cards)}
  {body_html}
  {_CTA}
  <footer>Generated by CommerceIQ · Source: Amazon SOV search-term cubes ·
    <span class="badge">{src_badge}</span></footer>
</div>
</body></html>"""


def build_html_report(scope: dict, cards: list[tuple[str, str, str]],
                      narrative_md: str,
                      figures: list[tuple[str, "go.Figure"]] | None = None,
                      narrative_source: str = "template",
                      tables: list[tuple[str, object]] | None = None) -> str:
    """Simple report (used by the all-categories overview): narrative + tables."""
    figures = figures or []
    fig_blocks = [f'<div class="chart">'
                  f'{fig.to_html(full_html=False, include_plotlyjs=False, default_width="100%")}'
                  f"</div>" for _t, fig in figures]
    plotly_head = f"<script>{get_plotlyjs()}</script>" if fig_blocks else ""
    src_badge = "AI-generated (OpenAI)" if narrative_source == "openai" else "Rule-based"
    body = (f'<div class="verdict">{_md_to_html(narrative_md)}</div>'
            + "".join(_render_table(t, d) for t, d in (tables or []))
            + ("".join(fig_blocks)))
    return _page(scope, "Category Positioning Report", cards, body, src_badge,
                 plotly_head)


def build_sectioned_report(scope: dict, cards: list[tuple[str, str, str]],
                           headline_md: str,
                           sections: list[dict],
                           how_you_win_md: str = "",
                           narrative_source: str = "template") -> str:
    """Full sectioned report. `sections` = list of
    {"title": str, "insight": str (md), "table": DataFrame|None}."""
    src_badge = "AI-generated (OpenAI)" if narrative_source == "openai" else "Rule-based"
    parts = [f'<div class="verdict">{_md_to_html(headline_md)}</div>']
    for i, sec in enumerate(sections, start=1):
        insight = sec.get("insight", "")
        table = sec.get("table")
        parts.append(
            f'<h2 class="section"><span class="num">{i:02d}</span> · '
            f'{_html.escape(sec["title"])}</h2>')
        if insight:
            parts.append(f'<div class="insight">{_md_to_html(insight)}</div>')
        parts.append(_table_html(table))
    if how_you_win_md:
        parts.append('<h2 class="section">How you win</h2>')
        parts.append(f'<div class="insight">{_md_to_html(how_you_win_md)}</div>')
    return _page(scope, "Share-of-Search Report", cards, "".join(parts), src_badge)


_PAL = [B.ELECTRIC, B.COBALT, B.SKY, "#7a3df0", "#e0457b", "#e08a00",
        B.DEEP_PURPLE, "#2f8fd6", "#2EC5B6", "#9AA0FF"]

_THEME_CSS = """
:root{--purple:#210235;--electric:#C231FF;--sky:#5AAFFE;--cobalt:#1F22B2;
 --ink:#120318;--paper:#fff;--bg:#f5f1f9;--bg2:#ece4f5;--line:#e4dbf0;
 --muted:#6b5f78;--muted2:#9a8ea8;--good:#15a34a;--max:1100px;
 --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,sans-serif;
 --mono:'IBM Plex Mono',ui-monospace,monospace;}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:var(--max);margin:0 auto;padding:0 26px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase}
.topbar{background:#120318;border-bottom:1px solid rgba(194,49,255,.22)}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;height:54px}
.brandlogo{display:flex;align-items:center;gap:9px;color:#fff;font-weight:800}
.brandlogo .dot{width:9px;height:9px;border-radius:50%;background:var(--electric);box-shadow:0 0 14px var(--electric)}
.confid{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.55)}
.hero{background:var(--purple);color:#fff;position:relative;overflow:hidden;padding:58px 0 66px}
.hero::before{content:"";position:absolute;inset:0;background:radial-gradient(60% 90% at 84% 6%,rgba(194,49,255,.42),transparent 60%),radial-gradient(50% 70% at 6% 94%,rgba(90,175,254,.3),transparent 60%)}
.hero .wrap{position:relative;z-index:2}
.hero .eyebrow{color:var(--sky)}
.hero h1{font-size:clamp(30px,5vw,50px);line-height:1.05;font-weight:900;letter-spacing:-.03em;margin:14px 0 0}
.hero h1 em{font-style:normal;background:linear-gradient(100deg,var(--electric),var(--sky));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero .sub{max-width:740px;color:rgba(255,255,255,.85);font-size:16px;margin-top:18px}
.heroband{margin-top:34px;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.14);border-radius:14px;overflow:hidden}
.heroband .cell{background:rgba(18,3,24,.55);padding:18px 20px}
.heroband .cell.focus{background:rgba(194,49,255,.16);box-shadow:inset 3px 0 0 var(--electric)}
.heroband .cell.focus .k{color:rgba(255,255,255,.85)}
.heroband .youtag{font-family:var(--mono);font-size:8px;letter-spacing:.06em;background:var(--electric);color:#fff;border-radius:4px;padding:1px 5px;margin-left:5px;vertical-align:middle}
.heroband .k{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.55)}
.heroband .v{font-size:29px;font-weight:800;margin-top:8px;letter-spacing:-.02em}
.heroband .v.accent{color:var(--electric)}
.heroband .v .u{font-size:13px;color:rgba(255,255,255,.6);font-weight:600}
section{padding:46px 0;border-bottom:1px solid var(--line)}
.sechead{display:flex;align-items:baseline;gap:15px}
.secnum{font-family:var(--mono);font-size:13px;font-weight:600;color:#fff;background:var(--purple);width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none}
.sechead h2{font-size:clamp(21px,3vw,29px);font-weight:800;letter-spacing:-.02em}
.sec-intro{color:var(--muted);font-size:15.5px;max-width:830px;margin:12px 0 24px;padding-left:51px}
.badge{position:relative;width:36px;height:36px;border-radius:9px;flex:none;overflow:hidden;background:#fff;border:1px solid var(--line)}
.badge .ini{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;color:#fff;background:var(--c,#8a7f99)}
.badge.sm{width:27px;height:27px;border-radius:7px}.badge.sm .ini{font-size:10px}
.badge .lg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#fff;z-index:2}
.lb{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.lbrow{display:grid;align-items:center;gap:16px;padding:13px 20px;border-top:1px solid var(--line)}
.lbrow.head{background:var(--bg)}.lbrow:first-child{border-top:none}
.lbrow.head span{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2)}
.lbrank{font-family:var(--mono);font-weight:600;font-size:15px;color:var(--muted2)}
.lbrow.lead-row{background:rgba(194,49,255,.055)}
.lbrow.lead-row .lbrank{color:var(--electric)}
.brandcell{display:flex;align-items:center;gap:11px;min-width:0}
.brandcell .nm{font-weight:700;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.youtag{font-family:var(--mono);font-size:9px;letter-spacing:.06em;background:var(--electric);color:#fff;border-radius:5px;padding:2px 6px;margin-left:7px}
.metric .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px}
.metric .lab{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2)}
.metric .num{font-family:var(--mono);font-weight:600;font-size:14px}
.mbar-track{height:9px;background:var(--bg2);border-radius:6px;overflow:hidden;display:flex}
.mbar-fill{height:100%;border-radius:6px}
.mfill-org{background:linear-gradient(90deg,var(--electric),#a01fe0)}
.mfill-paid{background:linear-gradient(90deg,var(--sky),var(--cobalt))}
.seg-org{height:100%;background:linear-gradient(90deg,var(--electric),#a01fe0)}
.seg-paid{height:100%;background:linear-gradient(90deg,var(--sky),var(--cobalt))}
.note{display:flex;gap:13px;background:#fff;border:1px solid var(--line);border-left:3px solid var(--sky);border-radius:12px;padding:15px 18px;margin-top:20px}
.note .ic{font-family:var(--mono);font-weight:600;color:var(--sky);font-size:12px;flex:none}
.note p{font-size:14px;color:var(--muted)}.note p strong{color:var(--ink)}
.subgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.subcard{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.subcard.wide{grid-column:1/-1}
.sc-head{padding:15px 18px;border-bottom:1px solid var(--line);position:relative}
.sc-head::after{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c,var(--electric))}
.sc-path{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2)}
.sc-path strong{color:var(--c,var(--electric))}
.sc-title{font-size:17px;font-weight:800;margin-top:4px}
.sc-leader{display:flex;align-items:center;gap:10px;margin-top:12px;background:var(--bg);border:1px solid var(--line);border-radius:11px;padding:8px 11px}
.sc-leader .ld-lab{font-family:var(--mono);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted2)}
.sc-leader .ld-nm{font-weight:700;font-size:13.5px}
.sc-leader .ld-sov{margin-left:auto;text-align:right;font-family:var(--mono)}
.sc-leader .ld-sov .v{font-weight:600;font-size:16px}
.sc-body{padding:6px 18px 12px}
.kwline{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line)}
.kwline:last-child{border-bottom:none}
.kwline .kw{font-weight:600;font-size:13.5px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kwline .rk{display:flex;align-items:center;gap:9px;flex:none}
.kwline .demand{width:120px;height:8px;background:var(--bg2);border-radius:4px;overflow:hidden;display:flex}
.kwline .demand i{display:block;height:100%;background:var(--c,var(--electric))}
.kwline .rnum{font-family:var(--mono);font-size:11.5px;color:var(--muted);min-width:96px;text-align:right}
.kwline .rnum b{color:var(--ink)}
.legend{font-family:var(--mono);font-size:10px;color:var(--muted2);margin:0 0 10px 51px;display:flex;gap:16px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-bottom:8px}
.stats .c{background:#fff;padding:15px 18px}
.stats .k{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2)}
.stats .v{font-size:22px;font-weight:800;margin-top:6px;letter-spacing:-.02em}
.bandbar{height:14px;border-radius:6px;overflow:hidden;display:flex;margin:14px 0 6px}
.bandbar i{height:100%}
.skuopt{display:grid;gap:15px}
.sku-card{display:grid;grid-template-columns:92px 1fr;gap:16px;background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:15px;overflow:hidden}
.sku-img{width:92px;height:92px;border-radius:10px;overflow:hidden;background:var(--bg2);display:flex;align-items:center;justify-content:center;font-size:1.9rem}
.sku-img img{width:100%;height:100%;object-fit:cover}
.sku-main{min-width:0}
.sku-meta{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted2);margin-bottom:9px}
.sku-meta b{color:var(--electric)}
.sku-meta .asin{color:var(--muted)}
.sku-before,.sku-after{margin-bottom:8px}
.sku-before .lab,.sku-after .lab,.sku-targets .lab{font-family:var(--mono);font-size:8.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2);display:block;margin-bottom:3px}
.sku-before p{font-size:13px;color:var(--muted);text-decoration:line-through;text-decoration-color:var(--muted2)}
.sku-after p{font-size:14.5px;font-weight:700;color:var(--ink)}
.sku-after .lab{color:var(--electric)}
.sku-targets{margin:10px 0 8px}
.chip{display:inline-block;font-size:11px;background:var(--bg2);color:var(--purple);border:1px solid var(--line);border-radius:100px;padding:3px 11px;margin:0 5px 5px 0;font-weight:600}
.sku-why{display:flex;gap:9px;align-items:flex-start;background:var(--bg);border-left:3px solid var(--electric);border-radius:0 8px 8px 0;padding:8px 12px;font-size:13px;color:var(--muted)}
.sku-why .ic{font-family:var(--mono);color:var(--electric);flex:none}
.sku-why b{color:var(--ink)}
.levers{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.lever{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px;position:relative;overflow:hidden}
.lever::before{content:"";position:absolute;left:0;top:0;right:0;height:4px}
.lever.org::before{background:linear-gradient(90deg,var(--electric),#a01fe0)}
.lever.paid::before{background:linear-gradient(90deg,var(--sky),var(--cobalt))}
.lever .tag{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:600}
.lever.org .tag{color:var(--electric)}.lever.paid .tag{color:var(--cobalt)}
.lever h3{font-size:18px;font-weight:800;margin:8px 0 6px}
.lever p{font-size:14px;color:var(--muted)}
.cta{background:var(--purple);color:#fff;position:relative;overflow:hidden;text-align:center;padding:58px 0}
.cta::before{content:"";position:absolute;inset:0;background:radial-gradient(50% 80% at 80% 20%,rgba(194,49,255,.4),transparent 60%),radial-gradient(50% 80% at 10% 90%,rgba(90,175,254,.28),transparent 60%)}
.cta .wrap{position:relative;z-index:2;max-width:720px}
.cta h2{font-size:clamp(24px,4vw,36px);font-weight:900;letter-spacing:-.02em}
.cta p{color:rgba(255,255,255,.82);font-size:15px;margin:15px auto 0;max-width:560px}
.btn{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(100deg,var(--electric),#a01fe0);color:#fff;font-weight:700;font-size:15px;padding:14px 26px;border-radius:100px;margin-top:22px}
footer{background:var(--ink);color:rgba(255,255,255,.6);padding:26px 0}
footer .wrap{display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;font-size:12px;font-family:var(--mono)}
footer b{color:#fff}
@media(max-width:820px){.subgrid,.levers,.inc-grid{grid-template-columns:1fr}}
@media print{.hero,.cta,.topbar{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.inc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px}
.inc-card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:18px;overflow:hidden}
.inc-card-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.inc-cat-name{font-weight:700;font-size:15px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.inc-tag{font-family:var(--mono);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:#fff;padding:3px 10px;border-radius:100px;font-weight:600;flex:none}
.inc-bar-wrap{margin:10px 0}
.inc-bar{height:12px;background:var(--bg2);border-radius:6px;overflow:hidden;display:flex}
.inc-stats{display:flex;gap:14px;font-family:var(--mono);font-size:11px;color:var(--muted2)}
.inc-stats b{color:var(--ink)}
.inc-meta{font-family:var(--mono);font-size:10px;color:var(--muted2);margin-top:8px}
.inc-summary{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-bottom:18px}
.inc-summary .c{background:#fff;padding:18px;text-align:center}
.inc-summary .ic{font-size:20px;margin-bottom:6px}
.inc-summary .n{font-size:26px;font-weight:800}
.inc-summary .l{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted2);margin-top:4px}
.inc-group{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-bottom:14px}
.inc-group-head{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid var(--line);background:var(--bg)}
.inc-group-icon{font-size:18px}
.inc-group-title{font-weight:700;font-size:14px}
.inc-group-desc{font-size:12px;color:var(--muted)}
.inc-group-count{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted2);white-space:nowrap}
.inc-group .kwline{padding:9px 18px}
"""


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", str(name)) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[1][:1]).upper()


def _sentence(s: str) -> str:
    """Sentence case: capitalise the first letter, keep the rest as-is
    (so existing capitalisation / acronyms are preserved)."""
    s = str(s or "").strip()
    return s[:1].upper() + s[1:] if s else s


def _logo_url(name: str) -> str:
    """Best-effort brand logo from Clearbit's free logo CDN (no API key).
    Guesses {slug}.com; if that 404s the <img> onerror reveals the initials."""
    slug = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return f"https://logo.clearbit.com/{slug}.com" if slug else ""


def _badge(name: str, color: str, sm: bool = True) -> str:
    cls = "badge sm" if sm else "badge"
    logo = _logo_url(name)
    # Initials sit underneath; the logo <img> layers on top and hides itself
    # (revealing the initials) if the brand has no Clearbit logo.
    img = (f'<img class="lg" src="{_html.escape(logo)}" alt="" loading="lazy" '
           f'onerror="this.style.display=\'none\'">' if logo else "")
    return (f'<div class="{cls}" style="--c:{color}">'
            f'<span class="ini">{_html.escape(_initials(name))}</span>{img}</div>')


def _inl(s) -> str:
    s = _html.escape(str(s or ""))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def _section(num: str, title: str, intro: str, body: str,
             note: str = "", legend: str = "") -> str:
    note_html = (f'<div class="note"><span class="ic">▌</span><p>{_inl(note)}</p></div>'
                 if note else "")
    intro_html = f'<p class="sec-intro">{_inl(intro)}</p>' if intro else ""
    legend_html = f'<div class="legend">{legend}</div>' if legend else ""
    return (f'<section><div class="sechead"><span class="secnum">{num}</span>'
            f'<h2>{_html.escape(title)}</h2></div>{intro_html}{legend_html}'
            f'{body}{note_html}</section>')


def _orgpaid_lb(rows: list[dict]) -> str:
    if not rows:
        return ""
    mo = max((r["organic"] for r in rows), default=0) or 1.0
    mp = max((r["paid"] for r in rows), default=0) or 1.0
    out = ['<div class="lb"><div class="lbrow head" '
           'style="grid-template-columns:40px 1fr 190px 190px">'
           '<span>#</span><span>Brand</span><span>Organic Share of Voice</span>'
           '<span>Paid Share of Voice</span></div>']
    for i, r in enumerate(rows):
        col = B.ELECTRIC if r["is_focus"] else _PAL[i % len(_PAL)]
        lead = " lead-row" if r["is_focus"] else ""
        you = '<span class="youtag">YOU</span>' if r["is_focus"] else ""
        wo, wp = min(100, r["organic"] / mo * 100), min(100, r["paid"] / mp * 100)
        out.append(
            f'<div class="lbrow{lead}" style="grid-template-columns:40px 1fr 190px 190px">'
            f'<div class="lbrank">{i + 1}</div>'
            f'<div class="brandcell">{_badge(r["brand"], col)}'
            f'<div class="nm">{_html.escape(str(r["brand"]))}{you}</div></div>'
            f'<div class="metric"><div class="top"><span class="lab">Organic</span>'
            f'<span class="num">{r["organic"]:.2f}%</span></div>'
            f'<div class="mbar-track"><div class="mbar-fill mfill-org" style="width:{wo:.1f}%"></div></div></div>'
            f'<div class="metric"><div class="top"><span class="lab">Paid</span>'
            f'<span class="num">{r["paid"]:.2f}%</span></div>'
            f'<div class="mbar-track"><div class="mbar-fill mfill-paid" style="width:{wp:.1f}%"></div></div></div></div>')
    out.append("</div>")
    return "".join(out)


def _combined_lb(rows: list[dict]) -> str:
    """ONE number per brand: Combined SOV, with a single bar split into the
    organic and paid points that add up to it."""
    if not rows:
        return ""
    mx = max((r["combined_sov"] for r in rows), default=0) or 1.0
    out = ['<div class="lb"><div class="lbrow head" '
           'style="grid-template-columns:40px 1fr 300px"><span>#</span>'
           '<span>Brand</span><span>Share of Voice (organic + paid)</span></div>']
    for i, r in enumerate(rows):
        col = B.ELECTRIC if r["is_focus"] else _PAL[i % len(_PAL)]
        lead = " lead-row" if r["is_focus"] else ""
        you = '<span class="youtag">YOU</span>' if r["is_focus"] else ""
        c = r["combined_sov"]
        wc = min(100, c / mx * 100)
        op, pp = r.get("organic_pts", 0), r.get("paid_pts", 0)
        tot = (op + pp) or 1.0
        wo, wp = op / tot * 100, pp / tot * 100
        out.append(
            f'<div class="lbrow{lead}" style="grid-template-columns:40px 1fr 300px">'
            f'<div class="lbrank">{i + 1}</div>'
            f'<div class="brandcell">{_badge(r["brand"], col)}'
            f'<div class="nm">{_html.escape(str(r["brand"]))}{you}</div></div>'
            f'<div class="metric"><div class="top"><span class="lab">Share of Voice</span>'
            f'<span class="num">{c:.2f}%</span></div>'
            f'<div class="mbar-track"><div class="mbar-fill" style="width:{wc:.1f}%;display:flex">'
            f'<i class="seg-org" style="width:{wo:.0f}%"></i>'
            f'<i class="seg-paid" style="width:{wp:.0f}%"></i></div></div>'
            f'<div style="font-family:var(--mono);font-size:10px;color:var(--muted2);'
            f'margin-top:4px">{op:.1f} pts organic · {pp:.1f} pts paid</div></div></div>')
    out.append("</div>")
    return "".join(out)


def _rank_lb(rows: list[dict], lab: str = "Share of voice") -> str:
    if not rows:
        return ""
    mx = max((r["sov"] for r in rows), default=0) or 1.0
    out = ['<div class="lb"><div class="lbrow head" '
           'style="grid-template-columns:40px 1fr 240px"><span>#</span>'
           f'<span>Brand</span><span>{_html.escape(lab)}</span></div>']
    for i, r in enumerate(rows):
        col = B.ELECTRIC if r["is_focus"] else _PAL[i % len(_PAL)]
        lead = " lead-row" if r["is_focus"] else ""
        you = '<span class="youtag">YOU</span>' if r["is_focus"] else ""
        w = min(100, r["sov"] / mx * 100)
        out.append(
            f'<div class="lbrow{lead}" style="grid-template-columns:40px 1fr 240px">'
            f'<div class="lbrank">{i + 1}</div>'
            f'<div class="brandcell">{_badge(r["brand"], col)}'
            f'<div class="nm">{_html.escape(str(r["brand"]))}{you}</div></div>'
            f'<div class="metric"><div class="top"><span class="lab">SOV</span>'
            f'<span class="num">{r["sov"]:.2f}%</span></div>'
            f'<div class="mbar-track"><div class="mbar-fill mfill-org" style="width:{w:.1f}%"></div></div></div></div>')
    out.append("</div>")
    return "".join(out)


def _subcards(cards: list[dict], cat: str) -> str:
    if not cards:
        return ""
    out = ['<div class="subgrid">']
    for i, c in enumerate(cards):
        col = _PAL[i % len(_PAL)]
        lead_sov = c.get("leader_sov", 0) or 0
        w = min(100, (c.get("focus_sov", 0) / lead_sov * 100) if lead_sov else 0)
        out.append(
            f'<div class="subcard"><div class="sc-head" style="--c:{col}">'
            f'<div class="sc-path">{_html.escape(cat)} <strong>&rarr;</strong> '
            f'{_html.escape(str(c["sub"]))}</div>'
            f'<div class="sc-title">{_html.escape(str(c["sub"]))}</div>'
            f'<div class="sc-leader">{_badge(c["leader"], col)}'
            f'<div><div class="ld-lab">Leader</div>'
            f'<div class="ld-nm">{_html.escape(str(c["leader"]))}</div></div>'
            f'<div class="ld-sov"><div class="v">{lead_sov:.1f}%</div></div></div></div>'
            f'<div class="sc-body"><div class="kwline"><span class="kw">You</span>'
            f'<span class="rk"><span class="demand" style="--c:{B.ELECTRIC}">'
            f'<i style="width:{w:.0f}%"></i></span>'
            f'<span class="rnum"><b>{c.get("focus_sov", 0):.1f}%</b> SOV</span></span></div></div></div>')
    out.append("</div>")
    return "".join(out)


def _kwlines(lines: list[dict], by: str, val_key: str, suffix: str) -> str:
    if not lines:
        return ""
    mx = max((abs(l.get(by, 0)) for l in lines), default=0) or 1.0
    rows = ['<div class="subcard wide"><div class="sc-body">']
    for l in lines:
        w = min(100, abs(l.get(by, 0)) / mx * 100)
        rows.append(
            f'<div class="kwline"><span class="kw">{_html.escape(str(l["kw"]))}</span>'
            f'<span class="rk"><span class="demand"><i style="width:{w:.0f}%"></i></span>'
            f'<span class="rnum"><b>{l.get(val_key, 0):.1f}%</b> {suffix}</span></span></div>')
    rows.append("</div></div>")
    return "".join(rows)


def _inc_lines(lines: list[dict]) -> str:
    if not lines:
        return ""
    mx = max((l["organic"] + l["paid"] for l in lines), default=0) or 1.0
    rows = ['<div class="subcard wide"><div class="sc-body">']
    for l in lines:
        wo, wp = l["organic"] / mx * 100, l["paid"] / mx * 100
        rows.append(
            f'<div class="kwline"><span class="kw">{_html.escape(str(l["kw"]))}</span>'
            f'<span class="rk"><span class="demand" style="width:150px">'
            f'<i style="width:{wo:.0f}%;background:var(--electric)"></i>'
            f'<i style="width:{wp:.0f}%;background:var(--sky)"></i></span>'
            f'<span class="rnum">org <b>{l["organic"]:.1f}</b> · paid <b>{l["paid"]:.1f}</b></span>'
            f'</span></div>')
    rows.append("</div></div>")
    return "".join(rows)


def _incr_body(incr: dict) -> str:
    s = incr.get("summary", {})
    stats = (
        '<div class="stats">'
        f'<div class="c"><div class="k">Paid SoV · ad data</div>'
        f'<div class="v" style="color:var(--electric)">{s.get("paid_sov", 0):.1f}%</div></div>'
        f'<div class="c"><div class="k">ROAS</div><div class="v">{s.get("roas", 0):.1f}x</div></div>'
        f'<div class="c"><div class="k">iROAS · incremental</div>'
        f'<div class="v" style="color:var(--cobalt)">{s.get("iroas", 0):.1f}x</div></div>'
        f'<div class="c"><div class="k">Sales that are incremental</div>'
        f'<div class="v">{s.get("inc_frac", 0) * 100:.0f}%</div></div></div>')
    bands = incr.get("bands", [])
    order = {"High": 0, "Mid": 1, "Low": 2}
    seg = {"High": B.ELECTRIC, "Mid": B.SKY, "Low": "#c9bcd6"}
    tot = sum(b.get("kws", 0) for b in bands) or 1.0
    band_html = "".join(
        f'<i style="width:{b.get("kws", 0) / tot * 100:.1f}%;background:{seg.get(b["band"], "#ccc")}"></i>'
        for b in sorted(bands, key=lambda x: order.get(x["band"], 3)))
    legend = ('<div class="legend" style="margin-left:0">'
              '<span><i style="background:#C231FF"></i>High incrementality</span>'
              '<span><i style="background:#5AAFFE"></i>Mid</span>'
              '<span><i style="background:#c9bcd6"></i>Low</span></div>')
    bandblock = (f'<div style="font-family:var(--mono);font-size:10px;letter-spacing:.1em;'
                 f'text-transform:uppercase;color:var(--muted2);margin-top:6px">'
                 f'Keywords by how incremental their ad-driven sales are</div>'
                 f'<div class="bandbar">{band_html}</div>{legend}') if bands else ""
    kws = incr.get("keywords", [])
    mx = max((k["paid_sov"] for k in kws), default=0) or 1.0
    rows = "".join(
        f'<div class="kwline"><span class="kw">{_html.escape(str(k["kw"]))}</span>'
        f'<span class="rk"><span class="demand"><i style="width:{min(100, k["paid_sov"] / mx * 100):.0f}%"></i></span>'
        f'<span class="rnum" style="min-width:210px">{k["paid_sov"]:.0f}% paid SoV · '
        f'ROAS <b>{k["roas"]:.1f}x</b> · iROAS <b>{k["iroas"]:.1f}x</b></span>'
        f'</span></div>' for k in kws)
    kwcard = f'<div class="subcard wide"><div class="sc-body">{rows}</div></div>' if rows else ""
    return stats + bandblock + kwcard


def _sku_opt_cards(items: list[dict]) -> str:
    """Cards for underperforming SKUs: thumbnail, current vs optimized title,
    target keywords, and the ranking rationale."""
    if not items:
        return ""
    out = ['<div class="skuopt">']
    for it in items:
        img = str(it.get("image_url", "") or "")
        img_html = (f'<img src="{_html.escape(img)}" alt="">' if img.startswith("http")
                    else "📦")
        chips = "".join(f'<span class="chip">{_html.escape(str(t))}</span>'
                        for t in (it.get("target_keywords") or []))
        chips_html = (f'<div class="sku-targets"><span class="lab">Target keywords '
                      f'(build the title to win these)</span>{chips}</div>'
                      if chips else "")
        avg = it.get("avg_rank", 0) or 0
        url = str(it.get("product_page_url", "") or "")
        asin_html = (f'<a href="{_html.escape(url)}" target="_blank" '
                     f'style="color:var(--sky);text-decoration:none">{_html.escape(str(it["sku"]))} &#8599;</a>'
                     if url.startswith("http") else _html.escape(str(it["sku"])))
        cur = str(it.get("current_title", "") or "(no current title on record)")
        opt = str(it.get("optimized_title", "") or "")
        why = it.get("rationale", "")
        out.append(
            f'<div class="sku-card">'
            f'<div class="sku-img">{img_html}</div>'
            f'<div class="sku-main">'
            f'<div class="sku-meta"><span class="asin">ASIN {asin_html}</span> &nbsp;·&nbsp; '
            f'avg rank <b>#{avg:.1f}</b> &nbsp;·&nbsp; {it.get("keywords", 0)} keywords &nbsp;·&nbsp; '
            f'{it.get("page1_kws", 0)} on page&nbsp;1</div>'
            f'<div class="sku-before"><span class="lab">Current title</span>'
            f'<p>{_html.escape(cur)}</p></div>'
            f'<div class="sku-after"><span class="lab">Optimized title ✨ '
            f'({len(opt)}/200 chars)</span><p>{_html.escape(opt)}</p></div>'
            f'{chips_html}'
            + (f'<div class="sku-why"><span class="ic">▌</span>'
               f'<span>{_inl(why)}</span></div>' if why else "")
            + '</div></div>')
    out.append("</div>")
    return "".join(out)


def build_themed_report(scope: dict, ins: dict, d: dict,
                        narrative_source: str = "template") -> str:
    cat = _sentence(scope.get("category_value", ""))
    brand = str(scope.get("brand_label", ""))
    h = d.get("hero", {})
    rank_txt = f" · #{h['rank']}" if h.get("rank") else ""
    src = "AI · OpenAI" if narrative_source == "openai" else "rule-based"

    hero = (
        f'<header class="hero"><div class="wrap">'
        f'<div class="eyebrow">Share of Search Report · {_html.escape(cat)} · Amazon · '
        f'{_html.escape(str(scope.get("metric_label", "")))}</div>'
        f'<h1>Win Your <em>Share of Search</em><br>in {_html.escape(cat)}</h1>'
        f'<p class="sub">{_inl(ins.get("verdict", ""))}</p>'
        f'<div class="heroband">'
        f'<div class="cell focus"><div class="k">{_html.escape(brand)} · your position '
        f'<span class="youtag">YOU</span></div>'
        f'<div class="v accent">{h.get("your_sov", 0):.2f}<span class="u">% SOV{rank_txt}</span></div></div>'
        f'<div class="cell"><div class="k">Organic SOV</div>'
        f'<div class="v">{h.get("organic", 0):.2f}<span class="u">%</span></div></div>'
        f'<div class="cell"><div class="k">Paid SOV</div>'
        f'<div class="v">{h.get("paid", 0):.2f}<span class="u">%</span></div></div>'
        f'</div></div></header>')

    secs = []
    n = 1
    if d.get("leaderboard"):
        legend = ('<span><i style="background:linear-gradient(90deg,#C231FF,#a01fe0)"></i>Organic</span>'
                  '<span><i style="background:linear-gradient(90deg,#5AAFFE,#1F22B2)"></i>Paid</span>')
        secs.append(_section(f"{n:02d}", "Share-of-Search Leaderboard",
                             ins.get("organic_paid", ""), _combined_lb(d["leaderboard"]),
                             note=ins.get("leaderboard", ""), legend=legend))
        n += 1
    if d.get("subcats"):
        secs.append(_section(f"{n:02d}", "Sub-Category Leaders",
                             ins.get("subcategories", ""), _subcards(d["subcats"], cat),
                             note=ins.get("readiness", "")))
        n += 1
    if d.get("whitespace"):
        secs.append(_section(f"{n:02d}", "Keyword Opportunities — Whitespace",
                             ins.get("keywords", ""),
                             _kwlines(d["whitespace"], "crawls", "your_sov", "your SOV")))
        n += 1
    if d.get("sku_opt") and d["sku_opt"].get("items"):
        so = d["sku_opt"]
        secs.append(_section(
            f"{n:02d}", "SKU Optimization — Biggest Ranking Wins",
            so.get("intro", ""), _sku_opt_cards(so["items"]),
            note=ins.get("sku_opt", "")))
        n += 1
    if d.get("incr"):
        secs.append(_section(f"{n:02d}", "Ad Incrementality & Efficiency",
                             d["incr"].get("intro", ""), _incr_body(d["incr"]),
                             note=ins.get("incrementality", "")))
        n += 1
    elif d.get("incrementality"):
        legend = ('<span><i style="background:#C231FF"></i>Organic</span>'
                  '<span><i style="background:#5AAFFE"></i>Paid (incremental)</span>')
        secs.append(_section(f"{n:02d}", "Organic vs Paid — by Keyword",
                             ins.get("incrementality", ""), _inc_lines(d["incrementality"]),
                             legend=legend))
        n += 1
    # How you win (generic levers)
    levers = (
        '<div class="levers">'
        '<div class="lever org"><div class="tag">Lever 01 · Organic</div>'
        '<h3>Win organic share with content</h3>'
        '<p>Rank on the searches shoppers run by making every listing the best-'
        'answered result — titles, bullets, A+ content, images and backend keywords '
        'tuned to each target term.</p></div>'
        '<div class="lever paid"><div class="tag">Lever 02 · Paid</div>'
        '<h3>Win paid share with ads</h3>'
        '<p>Buy the placements you can\'t yet earn. Target high-intent terms with '
        'sponsored ads to capture paid real estate the moment a shopper searches — '
        'and measure incremental return.</p></div></div>')
    secs.append(_section(f"{n:02d}", "How You Win Share of Search",
                         ins.get("how_you_win", ""), levers))

    cta = (
        '<section class="cta"><div class="wrap">'
        '<div class="eyebrow" style="color:var(--sky)">CommerceIQ Share-of-Search Enablement</div>'
        f'<h2>Climb the {_html.escape(cat)} leaderboard.</h2>'
        '<p>We\'ll map your organic and paid share on every target term, pinpoint the '
        'keywords you can win fastest, and put CommerceIQ to work capturing them.</p>'
        '<a class="btn" href="https://www.commerceiq.ai/demo">Talk to CommerceIQ &rarr;</a>'
        '</div></section>')

    footer = (
        '<footer><div class="wrap">'
        f'<span>© CommerceIQ · Share of Search Report</span>'
        f'<span>Category: {_html.escape(cat)} · {_html.escape(str(scope.get("date_min","")))} '
        f'→ {_html.escape(str(scope.get("date_max","")))}</span>'
        f'<span>Insights: {src}</span></div></footer>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(str(scope.get("name") or f"Share of Search — {cat} · {brand}"))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{_THEME_CSS}</style></head><body>
<div class="topbar"><div class="wrap"><div class="brandlogo"><span class="dot"></span>CommerceIQ</div>
<div class="confid">Generated report</div></div></div>
{hero}
<main class="wrap">{''.join(secs)}</main>
{cta}{footer}
</body></html>"""


def _cat_subcards(cards: list[dict], cat: str) -> str:
    """Sub-category cards for category report — shows category leader only,
    no 'YOU' bar (there is no focus brand in category mode)."""
    if not cards:
        return ""
    out = ['<div class="subgrid">']
    for i, c in enumerate(cards):
        col = _PAL[i % len(_PAL)]
        lead_sov = c.get("leader_sov", 0) or 0
        out.append(
            f'<div class="subcard"><div class="sc-head" style="--c:{col}">'
            f'<div class="sc-path">{_html.escape(cat)} <strong>&rarr;</strong> '
            f'{_html.escape(str(c["sub"]))}</div>'
            f'<div class="sc-title">{_html.escape(str(c["sub"]))}</div>'
            f'<div class="sc-leader">{_badge(c["leader"], col)}'
            f'<div><div class="ld-lab">Category Leader</div>'
            f'<div class="ld-nm">{_html.escape(str(c["leader"]))}</div></div>'
            f'<div class="ld-sov"><div class="v">{lead_sov:.1f}%</div>'
            f'<div style="font-family:var(--mono);font-size:9px;color:var(--muted2)">'
            f'SOV</div></div></div></div></div>')
    out.append("</div>")
    return "".join(out)


def _demand_kwlines(kws: list[dict]) -> str:
    """Keyword rows with a demand (crawl volume) bar — no SOV column
    since there is no focus brand in category mode."""
    if not kws:
        return ""
    mx = max((k.get("crawls", 0) for k in kws), default=0) or 1.0
    rows = ['<div class="subcard wide"><div class="sc-body">']
    for k in kws:
        w = min(100, k.get("crawls", 0) / mx * 100)
        rows.append(
            f'<div class="kwline"><span class="kw">{_html.escape(str(k["kw"]))}</span>'
            f'<span class="rk"><span class="demand">'
            f'<i style="width:{w:.0f}%"></i></span>'
            f'<span class="rnum"><b>{k["crawls"]:,.0f}</b> crawls</span>'
            f'</span></div>')
    rows.append("</div></div>")
    return "".join(rows)


def build_category_report(scope: dict, ins: dict, d: dict,
                           narrative_source: str = "template") -> str:
    """Category-landscape report — no focus brand.
    Shows who owns the category, sub-category breakdown, and top keywords.
    CTA nudges the reader to find out where THEIR brand stands."""
    cat = _sentence(scope.get("category_value", ""))
    src = "AI · OpenAI" if narrative_source == "openai" else "rule-based"
    h = d.get("hero", {})  # {top_brand, top_sov, brands, keywords}

    hero = (
        f'<header class="hero"><div class="wrap">'
        f'<div class="eyebrow">Category Share of Search · {_html.escape(cat)} · Amazon</div>'
        f'<h1>Who Owns <em>{_html.escape(cat)}</em>?</h1>'
        f'<p class="sub">{_inl(ins.get("verdict", ""))}</p>'
        f'<div class="heroband">'
        f'<div class="cell"><div class="k">Category Leader</div>'
        f'<div class="v accent">{_html.escape(str(h.get("top_brand", "—")))}'
        f'<span class="u"> · {h.get("top_sov", 0):.1f}% SOV</span></div></div>'
        f'<div class="cell"><div class="k">Brands Competing</div>'
        f'<div class="v">{h.get("brands", 0):,}</div></div>'
        f'<div class="cell"><div class="k">Keywords Tracked</div>'
        f'<div class="v">{h.get("keywords", 0):,}</div></div>'
        f'</div></div></header>')

    secs = []
    n = 1
    if d.get("leaderboard"):
        legend = (
            '<span><i style="background:linear-gradient(90deg,#C231FF,#a01fe0)"></i>Organic</span>'
            '<span><i style="background:linear-gradient(90deg,#5AAFFE,#1F22B2)"></i>Paid</span>')
        secs.append(_section(
            f"{n:02d}", f"Category Leaderboard — {cat}",
            ins.get("leaderboard", ""), _combined_lb(d["leaderboard"]),
            note=ins.get("organic_paid", ""), legend=legend))
        n += 1

    if d.get("subcats"):
        secs.append(_section(
            f"{n:02d}", "Sub-Category Breakdown",
            ins.get("subcategories", ""), _cat_subcards(d["subcats"], cat),
            note="No single brand dominates every sub-category — "
                 "this is where challenger brands find their opening."))
        n += 1

    if d.get("keywords"):
        secs.append(_section(
            f"{n:02d}", "Highest-Demand Keywords",
            ins.get("keywords", ""), _demand_kwlines(d["keywords"])))
        n += 1

    levers = (
        '<div class="levers">'
        '<div class="lever org"><div class="tag">Lever 01 · Organic</div>'
        '<h3>Content wins share durably</h3>'
        '<p>The top-ranked brands optimise every listing for the searches shoppers run — '
        'titles, bullets, A+ content and backend keywords tuned to each target term. '
        'Organic share compounds: it earns placement without ongoing spend.</p></div>'
        '<div class="lever paid"><div class="tag">Lever 02 · Paid</div>'
        '<h3>Ads win share immediately</h3>'
        '<p>Sponsored placements buy real estate on the highest-intent searches today. '
        'Find the keywords with low organic coverage and high crawl volume — '
        'that\'s where incremental paid share is most available and cheapest to capture.</p></div></div>')
    secs.append(_section(
        f"{n:02d}", f"How to Win Share in {cat}",
        ins.get("how_you_win", ""), levers))

    cta = (
        '<section class="cta"><div class="wrap">'
        '<div class="eyebrow" style="color:var(--sky)">'
        'CommerceIQ Share-of-Search Intelligence</div>'
        f'<h2>Is your brand in the <em>{_html.escape(cat)}</em> race?</h2>'
        '<p>CommerceIQ maps your organic and paid share on every target term, shows '
        'exactly who is winning and why, and puts automation to work capturing the '
        'share that is available.</p>'
        '<a class="btn" href="https://www.commerceiq.ai/demo">'
        'See where you stand &rarr;</a>'
        '</div></section>')

    footer = (
        '<footer><div class="wrap">'
        f'<span>&#169; CommerceIQ &middot; Category Share of Search Report</span>'
        f'<span>Category: {_html.escape(cat)} &middot; '
        f'{_html.escape(str(scope.get("date_min", "")))} &rarr; '
        f'{_html.escape(str(scope.get("date_max", "")))}</span>'
        f'<span>Insights: {src}</span></div></footer>')

    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_html.escape(str(scope.get("name") or f"Category SoS — {cat}"))}</title>'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:'
        f'wght@400;500;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600'
        f'&display=swap" rel="stylesheet">'
        f'<style>{_THEME_CSS}</style></head><body>'
        f'<div class="topbar"><div class="wrap">'
        f'<div class="brandlogo"><span class="dot"></span>CommerceIQ</div>'
        f'<div class="confid">Category Intelligence Report</div>'
        f'</div></div>'
        f'{hero}'
        f'<main class="wrap">{"".join(secs)}</main>'
        f'{cta}{footer}'
        f'</body></html>'
    )


# ── Incrementality report builder ──────────────────────────────────────────
_INC_TAG_COLORS = {
    "Organic-led": "var(--electric)",
    "Paid-dependent": "var(--cobalt)",
    "Balanced": "var(--sky)",
    "Cannibalizing": "#e05a00",
    "Dark Spot": "var(--muted2)",
}
_INC_TAG_ICONS = {
    "Cannibalizing": "🔴",
    "Paid-dependent": "🟡",
    "Organic-led": "🟢",
    "Balanced": "🔵",
    "Dark Spot": "⚫",
}
_INC_TAG_DESCS = {
    "Cannibalizing": "Strong organic rank + active ads — potential wasted overlap",
    "Paid-dependent": "Low organic presence, ads are your lifeline here",
    "Organic-led": "Strong organic presence, minimal paid needed",
    "Balanced": "Organic and paid working together",
    "Dark Spot": "No meaningful brand presence — untapped opportunity",
}


def _incr_cat_grid(cats: list[dict]) -> str:
    """Legacy card grid — kept as fallback."""
    if not cats:
        return ""
    out = ['<div class="inc-grid">']
    for c in cats:
        org = c.get("organic_sov", 0)
        paid = c.get("paid_sov", 0)
        total = org + paid or 1
        wo = org / total * 100
        wp = paid / total * 100
        cls = c.get("classification", "Balanced")
        color = _INC_TAG_COLORS.get(cls, "var(--muted2)")
        out.append(
            f'<div class="inc-card">'
            f'<div class="inc-card-head">'
            f'<div class="inc-cat-name">{_html.escape(_sentence(str(c["category"])))}</div>'
            f'<span class="inc-tag" style="background:{color}">{_html.escape(cls)}</span></div>'
            f'<div class="inc-bar-wrap"><div class="inc-bar">'
            f'<i class="seg-org" style="width:{wo:.0f}%"></i>'
            f'<i class="seg-paid" style="width:{wp:.0f}%"></i></div></div>'
            f'<div class="inc-stats">'
            f'<span>Organic <b>{org:.1f}%</b></span>'
            f'<span>Paid <b>{paid:.1f}%</b></span>'
            f'<span>Combined <b>{c.get("combined_sov", 0):.1f}%</b></span></div>'
            f'</div>')
    out.append("</div>")
    return "".join(out)


_LVL_COLORS = {
    "L1": "var(--purple)", "L2": "#5c2a8a", "L3": "var(--cobalt)",
    "L4": "var(--sky)", "L5": "#8a7f99", "L6": "#8a7f99",
    "L7": "#8a7f99", "L8": "#8a7f99", "L9": "#8a7f99", "L10": "#8a7f99",
}


def _incr_classification_legend() -> str:
    """Inline legend table explaining each classification label and its threshold."""
    rows = [
        ("Dark Spot",        "⚫", "var(--muted2)", "Combined SOV &lt; 0.5%",
         "No meaningful presence — untapped opportunity"),
        ("Paid-dependent",   "🟡", "var(--cobalt)",  "Paid fraction &ge; 65%",
         "Ads are the lifeline — low organic presence"),
        ("Organic-led",      "🟢", "var(--electric)", "Paid fraction &le; 15%",
         "Free traffic — protect this organic position"),
        ("Cannibalizing",    "🔴", "#e05a00",        "Organic &ge; 2.5% AND Paid &ge; 1.5%",
         "Paying for what you already own"),
        ("Balanced",         "🔵", "var(--sky)",      "Everything else",
         "Healthy organic + paid working together"),
    ]
    cells = "".join(
        f'<tr>'
        f'<td style="padding:8px 12px;white-space:nowrap">'
        f'<span class="inc-tag" style="background:{color};font-size:10px">{ic} {label}</span></td>'
        f'<td style="padding:8px 12px;font-family:var(--mono);font-size:12px;'
        f'color:var(--muted)">{rule}</td>'
        f'<td style="padding:8px 12px;font-size:13px;color:var(--ink)">{desc}</td>'
        f'</tr>' for label, ic, color, rule, desc in rows)
    return (
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:14px;overflow:hidden;margin-bottom:22px">'
        '<div style="padding:12px 18px;border-bottom:1px solid var(--line);'
        'background:var(--bg);font-family:var(--mono);font-size:10px;'
        'letter-spacing:.1em;text-transform:uppercase;color:var(--muted2);'
        'font-weight:600">Classification Guide</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px">'
        '<tr style="background:var(--bg)">'
        '<th style="padding:8px 12px;text-align:left;font-family:var(--mono);'
        'font-size:9px;letter-spacing:.1em;text-transform:uppercase;'
        'color:var(--muted2)">Pattern</th>'
        '<th style="padding:8px 12px;text-align:left;font-family:var(--mono);'
        'font-size:9px;letter-spacing:.1em;text-transform:uppercase;'
        'color:var(--muted2)">Rule</th>'
        '<th style="padding:8px 12px;text-align:left;font-family:var(--mono);'
        'font-size:9px;letter-spacing:.1em;text-transform:uppercase;'
        'color:var(--muted2)">What it means</th></tr>'
        f'{cells}</table></div>')


def _path_html(cat: dict) -> str:
    """Render 'L1 > L2 > **Leaf**' breadcrumb from the path string.
    The leaf (last segment) is bold; parents are muted."""
    path = str(cat.get("path", "") or cat.get("category", ""))
    parts = [p.strip() for p in path.split(">") if p.strip()]
    if not parts:
        return _html.escape(_sentence(str(cat.get("category", ""))))
    if len(parts) == 1:
        return f'<strong>{_html.escape(_sentence(parts[0]))}</strong>'
    parents = " &rsaquo; ".join(
        f'<span style="color:var(--muted2)">{_html.escape(_sentence(p))}</span>'
        for p in parts[:-1])
    leaf = f'<strong>{_html.escape(_sentence(parts[-1]))}</strong>'
    return f'{parents} &rsaquo; {leaf}'


def _incr_cat_table(cats: list[dict]) -> str:
    """Multi-level table view: Level | Category path | SOV bar | Classification | KWs | Crawls.
    Sorted by path so children sit under their parents."""
    if not cats:
        return ""
    mx = max((c.get("combined_sov", 0) for c in cats), default=0) or 1.0
    gcols = "grid-template-columns:54px 1fr 220px 140px"
    out = [
        f'<div class="lb">'
        f'<div class="lbrow head" style="{gcols}">'
        f'<span>Level</span><span>Category</span>'
        f'<span>SOV (organic + paid)</span><span>Classification</span></div>'
    ]
    for c in cats:
        org = c.get("organic_sov", 0)
        paid = c.get("paid_sov", 0)
        comb = c.get("combined_sov", 0)
        total = org + paid or 1
        wo = org / total * 100
        wp = paid / total * 100
        wc = min(100, comb / mx * 100)
        cls = c.get("classification", "Balanced")
        lvl = str(c.get("level", "L1"))
        tag_color = _INC_TAG_COLORS.get(cls, "var(--muted2)")
        lvl_color = _LVL_COLORS.get(lvl, "var(--muted2)")
        # L1 rows get a subtle highlight
        row_bg = ' style="background:rgba(33,2,53,.03)"' if lvl == "L1" else ""
        # Indent child rows slightly
        depth = int(lvl[1:]) if lvl[1:].isdigit() else 1
        indent = (depth - 1) * 16
        out.append(
            f'<div class="lbrow" style="{gcols}"{row_bg}>'
            # Level badge
            f'<div><span style="display:inline-block;font-family:var(--mono);font-size:11px;'
            f'font-weight:700;color:#fff;background:{lvl_color};padding:3px 10px;'
            f'border-radius:6px">{_html.escape(lvl)}</span></div>'
            # Category path (breadcrumb)
            f'<div style="font-size:14px;min-width:0;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;padding-left:{indent}px">'
            f'{_path_html(c)}</div>'
            # SOV stacked bar
            f'<div class="metric"><div class="top"><span class="lab">SOV</span>'
            f'<span class="num">{comb:.1f}%</span></div>'
            f'<div class="mbar-track"><div class="mbar-fill" style="width:{wc:.1f}%;display:flex">'
            f'<i class="seg-org" style="width:{wo:.0f}%"></i>'
            f'<i class="seg-paid" style="width:{wp:.0f}%"></i></div></div>'
            f'<div style="font-family:var(--mono);font-size:9px;color:var(--muted2);'
            f'margin-top:2px">{org:.1f} org · {paid:.1f} paid</div></div>'
            # Classification badge
            f'<div><span class="inc-tag" style="background:{tag_color}">'
            f'{_html.escape(cls)}</span></div>'
            f'</div>')
    out.append("</div>")
    return "".join(out)


def _incr_kw_summary(ks: dict) -> str:
    items = [
        ("🔴", ks.get("cannibalizing", 0), "Cannibalizing"),
        ("🟡", ks.get("paid_dependent", 0), "Paid-dependent"),
        ("🟢", ks.get("organic_led", 0), "Organic-led"),
        ("🔵", ks.get("balanced", 0), "Balanced"),
        ("⚫", ks.get("dark_spot", 0), "Dark Spot"),
    ]
    cells = "".join(
        f'<div class="c"><div class="ic">{ic}</div>'
        f'<div class="n">{n}</div><div class="l">{_html.escape(lab)}</div></div>'
        for ic, n, lab in items)
    return f'<div class="inc-summary">{cells}</div>'


def _incr_kw_grouped(keywords: list[dict]) -> str:
    if not keywords:
        return ""
    groups: dict[str, list[dict]] = {}
    for kw in keywords:
        groups.setdefault(kw.get("classification", "Balanced"), []).append(kw)
    order = ["Cannibalizing", "Paid-dependent", "Organic-led", "Balanced", "Dark Spot"]
    out: list[str] = []
    for cls in order:
        kws = groups.get(cls, [])
        if not kws:
            continue
        mx = max((k.get("combined_sov", 0) for k in kws), default=0) or 1.0
        icon = _INC_TAG_ICONS.get(cls, "")
        desc = _INC_TAG_DESCS.get(cls, "")
        out.append(
            f'<div class="inc-group"><div class="inc-group-head">'
            f'<span class="inc-group-icon">{icon}</span>'
            f'<div><div class="inc-group-title">{_html.escape(cls)}</div>'
            f'<div class="inc-group-desc">{_html.escape(desc)}</div></div>'
            f'<span class="inc-group-count">{len(kws)} keywords</span></div>')
        for kw in kws[:8]:
            org = kw.get("organic_sov", 0)
            paid = kw.get("paid_sov", 0)
            comb = kw.get("combined_sov", 0)
            total = org + paid or 1
            wo = org / total * 100
            wp = paid / total * 100
            w = min(100, comb / mx * 100)
            out.append(
                f'<div class="kwline"><span class="kw">'
                f'{_html.escape(str(kw["search_term"]))}</span>'
                f'<span class="rk"><span class="demand" style="width:150px">'
                f'<i style="width:{wo * w / 100:.0f}%;background:var(--electric)"></i>'
                f'<i style="width:{wp * w / 100:.0f}%;background:var(--sky)"></i></span>'
                f'<span class="rnum">org <b>{org:.1f}%</b> · paid <b>{paid:.1f}%</b>'
                f'</span></span></div>')
        out.append("</div>")
    return "".join(out)


def build_incrementality_report(scope: dict, ins: dict, d: dict,
                                narrative_source: str = "template") -> str:
    """Incrementality report — where a brand earns vs buys shelf space."""
    brand = _html.escape(str(scope.get("brand_label", "")))
    src = "AI · OpenAI" if narrative_source == "openai" else "rule-based"
    h = d.get("hero", {})
    ks = d.get("keyword_summary", {})

    hero = (
        f'<header class="hero"><div class="wrap">'
        f'<div class="eyebrow">Incrementality Analysis · {brand} · Amazon</div>'
        f'<h1>Where {brand} <em>Earns vs Buys</em> Shelf Space</h1>'
        f'<p class="sub">{_inl(ins.get("verdict", ""))}</p>'
        f'<div class="heroband">'
        f'<div class="cell focus"><div class="k">{brand} <span class="youtag">YOU</span></div>'
        f'<div class="v accent">{h.get("categories", 0)}<span class="u"> categories</span></div></div>'
        f'<div class="cell"><div class="k">Organic SOV (avg)</div>'
        f'<div class="v">{h.get("avg_organic", 0):.1f}<span class="u">%</span></div></div>'
        f'<div class="cell"><div class="k">Paid SOV (avg)</div>'
        f'<div class="v">{h.get("avg_paid", 0):.1f}<span class="u">%</span></div></div>'
        f'</div></div></header>')

    secs = []
    n = 1

    # Section: Category map — table view showing all taxonomy levels
    if d.get("categories"):
        legend = ('<span><i style="background:linear-gradient(90deg,#C231FF,#a01fe0)"></i>Organic</span>'
                  '<span><i style="background:linear-gradient(90deg,#5AAFFE,#1F22B2)"></i>Paid</span>')
        cat_body = _incr_classification_legend() + _incr_cat_table(d["categories"])
        secs.append(_section(
            f"{n:02d}", "Category Incrementality Map",
            ins.get("overview", ""), cat_body,
            legend=legend))
        n += 1

    # Section: Keyword summary + grouped detail
    if d.get("keywords"):
        body = _incr_kw_summary(ks) + _incr_kw_grouped(d["keywords"])
        top_cat = d.get("detail_category", "")
        title = (f"Keyword Incrementality — {_sentence(top_cat)}"
                 if top_cat else "Keyword Incrementality Breakdown")
        secs.append(_section(f"{n:02d}", title,
                             ins.get("cannibalizing", ""), body,
                             note=ins.get("incremental", "")))
        n += 1

    # Section: Reallocation signals
    n_can = ks.get("cannibalizing", 0)
    n_dark = ks.get("dark_spot", 0)
    realloc = (
        '<div class="levers">'
        f'<div class="lever org"><div class="tag">Signal 01 · Reduce overlap</div>'
        f'<h3>{n_can} Cannibalizing Keywords</h3>'
        '<p>These keywords already rank well organically — the brand appears on '
        'page 1 without ads. Reducing paid focus here frees resources for '
        'higher-impact terms without losing shelf presence.</p></div>'
        f'<div class="lever paid"><div class="tag">Signal 02 · Fill gaps</div>'
        f'<h3>{n_dark} Dark-Spot Opportunities</h3>'
        '<p>High-demand keywords where the brand has no presence — organic or paid. '
        'These are the highest-upside targets: each one is a shelf position '
        'competitors hold that this brand doesn\'t contest.</p></div></div>')
    secs.append(_section(f"{n:02d}", "Budget Reallocation Signals",
                         ins.get("opportunities", ""), realloc))
    n += 1

    # How you win
    levers = (
        '<div class="levers">'
        '<div class="lever org"><div class="tag">Lever 01 · Organic</div>'
        '<h3>Earn share with content</h3>'
        '<p>Optimize listing titles, bullets, and backend keywords for the terms '
        'where the brand has paid presence but weak organic — convert paid '
        'dependency into durable organic share that compounds over time.</p></div>'
        '<div class="lever paid"><div class="tag">Lever 02 · Paid</div>'
        '<h3>Buy share where it\'s incremental</h3>'
        '<p>Focus ad spend on keywords where organic rank is low but demand is '
        'high — the truly incremental placements. Every dollar here captures '
        'a shopper who would otherwise go to a competitor.</p></div></div>')
    secs.append(_section(f"{n:02d}", "How You Win — Organic + Paid Strategy",
                         ins.get("how_you_win", ""), levers))

    cta = (
        '<section class="cta"><div class="wrap">'
        '<div class="eyebrow" style="color:var(--sky)">'
        'CommerceIQ Incrementality Intelligence</div>'
        f'<h2>Stop paying for what you already own.</h2>'
        '<p>CommerceIQ identifies every cannibalizing keyword, every paid-dependent '
        'term, and every dark-spot opportunity — then automates the reallocation '
        'across your entire catalog.</p>'
        '<a class="btn" href="https://www.commerceiq.ai/demo">Talk to CommerceIQ &rarr;</a>'
        '</div></section>')

    footer = (
        '<footer><div class="wrap">'
        f'<span>&#169; CommerceIQ &middot; Incrementality Analysis</span>'
        f'<span>Brand: {brand} &middot; '
        f'{_html.escape(str(scope.get("date_min", "")))} &rarr; '
        f'{_html.escape(str(scope.get("date_max", "")))}</span>'
        f'<span>Insights: {src}</span></div></footer>')

    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_html.escape(str(scope.get("name") or f"Incrementality — {brand}"))}</title>'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:'
        f'wght@400;500;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600'
        f'&display=swap" rel="stylesheet">'
        f'<style>{_THEME_CSS}</style></head><body>'
        f'<div class="topbar"><div class="wrap">'
        f'<div class="brandlogo"><span class="dot"></span>CommerceIQ</div>'
        f'<div class="confid">Incrementality Analysis Report</div>'
        f'</div></div>'
        f'{hero}'
        f'<main class="wrap">{"".join(secs)}</main>'
        f'{cta}{footer}'
        f'</body></html>'
    )


def html_to_pdf(html_str: str, out_path: str | Path) -> Path | None:
    """Render the HTML report to PDF via headless Chromium (Playwright).

    Runs in a subprocess to avoid Playwright's sync-API-inside-asyncio error
    under Streamlit. Returns the PDF path, or None if Playwright is unavailable.
    """
    out_path = Path(out_path)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as tf:
        tf.write(html_str)
        html_path = tf.name
    try:
        subprocess.run(
            [sys.executable, "-m", "sov.pdf_render", html_path, str(out_path)],
            check=True, capture_output=True, text=True, timeout=180,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        return out_path if out_path.exists() else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        detail = getattr(e, "stderr", "") or str(e)
        raise RuntimeError(f"PDF rendering failed: {detail.strip()[-500:]}") from e
    finally:
        try:
            Path(html_path).unlink(missing_ok=True)
        except Exception:
            pass
