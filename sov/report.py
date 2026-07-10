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
  body {{ font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
         color: #0A0A0A; margin: 0; background: {B.WHITE}; }}
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
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
 --ink:#0A0A0A;--paper:#fff;--bg:#f5f1f9;--bg2:#ece4f5;--line:#e4dbf0;
 --muted:#6b5f78;--muted2:#9a8ea8;--good:#047857;--max:1100px;
 --sans:'DM Sans',-apple-system,BlinkMacSystemFont,sans-serif;
 --mono:'DM Mono',ui-monospace,SFMono-Regular,monospace;
 --status-red-bg:#DC2626;--status-red-fg:#991B1B;
 --status-amber-bg:#D97706;--status-amber-fg:#92400E;
 --status-green-bg:#047857;--status-green-fg:#065F46;
 --status-blue-bg:#1F22B2;--status-blue-fg:#1E40AF;}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:var(--max);margin:0 auto;padding:0 26px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase}
.topbar{background:#120318;border-bottom:1px solid rgba(194,49,255,.22)}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;height:54px}
.brandlogo{display:flex;align-items:center;gap:9px;color:#fff;font-weight:800}
.brandlogo .dot{width:9px;height:9px;border-radius:50%;background:var(--electric);box-shadow:0 0 14px var(--electric)}
.confid{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.55)}
.cover{height:100vh;max-height:1080px;background:var(--purple);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 48px;position:relative;overflow:hidden}
.cover::before{content:"";position:absolute;top:-200px;right:-200px;width:600px;height:600px;background:radial-gradient(circle,rgba(194,49,255,.2) 0%,transparent 70%);pointer-events:none}
.cover::after{content:"";position:absolute;bottom:-150px;left:-150px;width:500px;height:500px;background:radial-gradient(circle,rgba(90,175,254,.12) 0%,transparent 70%);pointer-events:none}
.cover-accent-bar{width:60px;height:3px;background:var(--electric);border-radius:2px;margin-bottom:20px}
.cover-brand{font-size:12px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;color:var(--electric);margin-bottom:12px}
.cover-title{font-size:clamp(24px,3.5vw,40px);font-weight:700;color:#fff;text-align:center;line-height:1.2;margin-bottom:10px;max-width:650px}
.cover-subtitle{font-size:17px;font-weight:300;color:rgba(255,255,255,.5);margin-bottom:36px;letter-spacing:.05em}
.cover-divider{width:100%;max-width:480px;height:1px;background:linear-gradient(90deg,transparent,rgba(90,175,254,.5),transparent);margin-bottom:32px}
.cover-meta{display:grid;grid-template-columns:auto 1fr;gap:8px 20px;max-width:480px;width:100%}
.meta-label{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--sky);padding:3px 0;white-space:nowrap}
.meta-value{font-size:12px;color:rgba(255,255,255,.65);padding:3px 0;border-bottom:1px solid rgba(255,255,255,.08)}
@media print{.cover{page-break-after:always;height:auto;max-height:none}}
html{scroll-behavior:smooth;scroll-padding-top:48px}
section{padding:56px 64px;border-bottom:1px solid var(--line);background:var(--paper)}
.section-header{background:var(--purple);color:white;padding:18px 28px;display:flex;align-items:center;gap:16px;margin:-56px -64px 40px -64px}
.section-num{font-family:var(--mono);font-size:12px;color:var(--electric);font-weight:500;letter-spacing:.1em;background:rgba(194,49,255,.15);padding:4px 10px;border-radius:4px;white-space:nowrap}
.section-title{font-size:18px;font-weight:600;color:white}
.sechead{display:flex;align-items:baseline;gap:15px}
.secnum{font-family:var(--mono);font-size:13px;font-weight:600;color:#fff;background:var(--electric);width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none}
.sechead h2{font-size:clamp(21px,3vw,29px);font-weight:800;letter-spacing:-.02em}
.sticky-nav{position:sticky;top:0;z-index:100;background:rgba(33,2,53,.95);backdrop-filter:blur(10px);border-bottom:1px solid rgba(194,49,255,.3);padding:0 64px;display:flex;align-items:center;gap:4px;overflow-x:auto}
.nav-item{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:rgba(255,255,255,.45);padding:14px 12px;white-space:nowrap;border-bottom:2px solid transparent;transition:all .2s;text-decoration:none}
.nav-item:hover{color:var(--electric);border-bottom-color:var(--electric)}
.exec-kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:24px 0}
.exec-kpi{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px;position:relative;overflow:hidden}
.exec-kpi::before{content:"";position:absolute;left:0;top:0;right:0;height:4px;background:var(--c,var(--electric))}
.exec-kpi-val{font-size:28px;font-weight:800;letter-spacing:-.02em;margin-top:6px}
.exec-kpi-lbl{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted2);margin-top:4px}
.prose{font-size:15px;color:var(--muted);line-height:1.7;max-width:800px}
.prose strong{color:var(--ink)}
.deliverables{list-style:none;padding:0;margin:18px 0 0}
.deliverables li{display:flex;gap:10px;font-size:14px;color:var(--muted);padding:6px 0;border-bottom:1px dashed var(--line)}
.deliverables li:last-child{border-bottom:none}
.deliverables .dl-ic{flex:none;font-size:14px}
.sec-intro{color:var(--muted);font-size:15.5px;max-width:830px;margin:12px 0 24px;padding-left:51px}
.badge{position:relative;width:36px;height:36px;border-radius:9px;flex:none;overflow:hidden;background:#fff;border:1px solid var(--line)}
.badge .ini{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;color:#fff;background:var(--c,#8a7f99)}
.badge.sm{width:27px;height:27px;border-radius:7px}.badge.sm .ini{font-size:10px}
.badge .lg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#fff;z-index:2}
.lb{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.lbrow{display:grid;align-items:center;gap:16px;padding:13px 20px;border-top:1px solid var(--line)}
.lbrow:nth-child(even){background:#FAFAFD}
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
.pdp-opt{background:var(--paper);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.pdp-header{padding:22px 24px 18px;border-bottom:1px solid var(--line)}
.pdp-header-label{font-family:var(--mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted2);margin-bottom:12px}
.pdp-header-body{display:flex;gap:20px;align-items:flex-start}
.pdp-header-img{width:80px;height:80px;object-fit:contain;border:1px solid var(--line);border-radius:8px;flex:none;background:#fff}
.pdp-header-info{min-width:0;flex:1}
.pdp-header-title{font-size:17px;font-weight:700;color:var(--ink);line-height:1.4;margin-bottom:10px}
.pdp-header-stats{display:flex;gap:16px;margin-top:12px}
.pdp-stat{display:flex;flex-direction:column;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 14px;min-width:80px}
.pdp-stat-val{font-size:18px;font-weight:800;color:var(--ink);letter-spacing:-.02em}
.pdp-stat-lbl{font-family:var(--mono);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted2);margin-top:2px}
.pdp-asin-badge{display:inline-flex;align-items:center;gap:4px;font-family:var(--mono);font-size:10.5px;letter-spacing:.04em;color:var(--sky);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:3px 10px;text-decoration:none}
.pdp-asin-badge:hover{background:var(--bg2)}
.pdp-section{padding:20px 24px;border-bottom:1px solid var(--line)}
.pdp-section:last-child{border-bottom:none}
.pdp-compare{display:grid;grid-template-columns:1fr 1fr;gap:0}
.pdp-compare.full{grid-template-columns:1fr}
@media(max-width:800px){.pdp-compare{grid-template-columns:1fr}}
.pdp-before,.pdp-after{min-width:0;padding:16px 0}
.pdp-compare .pdp-after{border-left:1px solid var(--line);padding-left:20px}
.pdp-compare.full .pdp-after{border-left:none;padding-left:0}
.pdp-sec-bar{display:flex;align-items:center;gap:10px;background:var(--purple);color:#fff;padding:10px 16px;border-radius:8px;margin-bottom:14px;font-size:13px;font-weight:600}
.pdp-sec-pill{font-family:var(--mono);font-size:10px;letter-spacing:.06em;padding:3px 10px;border-radius:4px}
.pdp-sec-bar.cur .pdp-sec-pill{background:rgba(255,255,255,.15);color:rgba(255,255,255,.8)}
.pdp-sec-bar.rec .pdp-sec-pill{background:rgba(194,49,255,.2);color:var(--accent)}
.pdp-before p{font-size:13.5px;color:var(--muted);line-height:1.6}
.pdp-after p{font-size:13.5px;font-weight:600;color:var(--ink);line-height:1.6}
.pdp-before ul,.pdp-after ul{margin:0;padding:0;list-style:none;font-size:13px;line-height:1.7}
.pdp-before ul{color:var(--muted)}
.pdp-after ul{color:var(--ink)}
.pdp-before li,.pdp-after li{display:flex;gap:10px;margin-bottom:8px}
.pdp-before li:last-child,.pdp-after li:last-child{margin-bottom:0}
.pdp-bullet-num{flex:none;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:10px;font-weight:700;margin-top:2px}
.pdp-before .pdp-bullet-num{background:var(--bg2);color:var(--muted2)}
.pdp-after .pdp-bullet-num{background:var(--electric);color:#fff}
.pdp-bullet-text{min-width:0}
.pdp-desc-text{font-size:13px;line-height:1.65}
.ih-text{font-size:14px;font-weight:500;color:var(--ink);line-height:1.55;margin-top:4px}
.pdp-reasons{display:grid;grid-template-columns:repeat(2,1fr);gap:6px 20px;margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}
@media(max-width:800px){.pdp-reasons{grid-template-columns:1fr}}
.pdp-reason{display:flex;gap:7px;align-items:flex-start;font-size:12px;line-height:1.5;padding:2px 0}
.pdp-reason div{min-width:0}
.reason-icon{flex:none;font-size:12px;font-weight:700;margin-top:1px}
.reason-keep .reason-icon{color:var(--status-green-fg)}
.reason-add .reason-icon{color:var(--status-blue-fg)}
.reason-remove .reason-icon{color:var(--status-red-fg)}
.reason-label{font-weight:700;color:var(--ink);word-break:break-word}
.reason-detail{color:var(--muted);word-break:break-word}
.pdp-reason-legend{display:flex;gap:18px;font-family:var(--mono);font-size:10px;letter-spacing:.06em;margin-top:14px;padding:8px 0}
.pdp-reason-legend span{display:inline-flex;align-items:center;gap:5px}
.pdp-sec-title{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:var(--purple);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.pdp-analysis{background:var(--bg);border-bottom:none}
.analysis-group{margin-bottom:16px}
.analysis-group:last-child{margin-bottom:0}
.analysis-label{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--purple);font-weight:700;margin-bottom:8px}
.tier-group{border-radius:8px;padding:10px 14px;margin-bottom:8px}
.tier-group:last-child{margin-bottom:0}
.tier-a{background:rgba(4,120,87,.08);border-left:3px solid var(--status-green-bg)}
.tier-b{background:rgba(217,119,6,.08);border-left:3px solid var(--status-amber-bg)}
.tier-c{background:rgba(220,38,38,.08);border-left:3px solid var(--status-red-bg)}
.tier-label{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;font-weight:700;display:block;margin-bottom:4px}
.tier-a .tier-label{color:var(--status-green-fg)}
.tier-b .tier-label{color:var(--status-amber-fg)}
.tier-c .tier-label{color:var(--status-red-fg)}
.tier-group ul{margin:0;padding-left:16px;font-size:12px;color:var(--ink);line-height:1.6}
.sim-list{margin-bottom:8px}
.sim-key{font-size:11px;font-weight:600;color:var(--ink);display:block;margin-bottom:4px}
.sim-list ol{margin:0;padding-left:18px;font-size:12px;color:var(--muted);line-height:1.6}
.seo-notes{font-size:12.5px;color:var(--muted);line-height:1.65;background:var(--paper);border-radius:8px;padding:12px 14px}
.chip{display:inline-block;font-size:11px;background:var(--bg2);color:var(--purple);border:1px solid var(--line);border-radius:100px;padding:3px 11px;margin:0 5px 5px 0;font-weight:600}
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
             note: str = "", legend: str = "", section_id: str = "") -> str:
    id_attr = f' id="{_html.escape(section_id)}"' if section_id else ""
    note_html = (f'<div class="note"><span class="ic">▌</span><p>{_inl(note)}</p></div>'
                 if note else "")
    intro_html = f'<p class="sec-intro">{_inl(intro)}</p>' if intro else ""
    legend_html = f'<div class="legend">{legend}</div>' if legend else ""
    return (f'<section{id_attr}>'
            f'<div class="section-header">'
            f'<span class="section-num">SECTION {num}</span>'
            f'<span class="section-title">{_html.escape(title)}</span></div>'
            f'{intro_html}{legend_html}'
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


def _kwlines(lines: list[dict], by: str, val_key: str, suffix: str,
            fmt: str = "pct") -> str:
    if not lines:
        return ""
    mx = max((abs(l.get(by, 0)) for l in lines), default=0) or 1.0
    rows = ['<div class="subcard wide"><div class="sc-body">']
    for l in lines:
        w = min(100, abs(l.get(by, 0)) / mx * 100)
        val = l.get(val_key, 0)
        val_txt = f"{val:,.0f}" if fmt == "count" else f"{val:.1f}%"
        rows.append(
            f'<div class="kwline"><span class="kw">{_html.escape(str(l["kw"]))}</span>'
            f'<span class="rk"><span class="demand"><i style="width:{w:.0f}%"></i></span>'
            f'<span class="rnum"><b>{val_txt}</b> {suffix}</span></span></div>')
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


def _sku_pdp_card(card: dict) -> str:
    """Full PDP optimization card: title, bullets, description, analysis."""
    if not card:
        return ""
    e = _html.escape

    url = str(card.get("product_page_url", card.get("amazonUrl", "")) or "")
    asin = str(card.get("asin", ""))
    cur_title = str(card.get("currentTitle", "") or "(no current title)")
    opt_title = str(card.get("recommendedTitle", "") or "")

    asin_link = (f'<a class="pdp-asin-badge" href="{e(url)}" target="_blank">'
                 f'{e(asin)} &#8599;</a>'
                 if url.startswith("http")
                 else f'<span class="pdp-asin-badge">{e(asin)}</span>')


    img_url = str(card.get("image_url", "") or "")
    avg_rank = card.get("avg_rank", 0)
    kw_count = card.get("keywords", 0)
    p1_count = card.get("page1_kws", 0)

    img_html = (f'<img class="pdp-header-img" src="{e(img_url)}" alt="product">'
                if img_url.startswith("http") else "")

    stats_html = (
        '<div class="pdp-header-stats">'
        f'<div class="pdp-stat"><span class="pdp-stat-val">{avg_rank}</span>'
        f'<span class="pdp-stat-lbl">Avg Rank</span></div>'
        f'<div class="pdp-stat"><span class="pdp-stat-val">{kw_count}</span>'
        f'<span class="pdp-stat-lbl">Keywords</span></div>'
        '</div>'
    )

    out = [
        '<div class="pdp-opt">',
        f'<div class="pdp-header">'
        f'<div class="pdp-header-label">Product being optimized</div>'
        f'<div class="pdp-header-body">'
        f'{img_html}'
        f'<div class="pdp-header-info">'
        f'<div class="pdp-header-title">{e(cur_title)}</div>'
        f'{asin_link}'
        f'{stats_html}'
        f'</div></div></div>',
    ]

    sec_cur = ('<div class="pdp-sec-bar cur">'
               '<span class="pdp-sec-pill">Current</span>')
    sec_rec = ('<div class="pdp-sec-bar rec">'
               '<span class="pdp-sec-pill">Optimized</span>')

    # ── Title comparison
    out.append(
        f'<div class="pdp-section">'
        f'<div class="pdp-compare">'
        f'<div class="pdp-before">{sec_cur} Title</div>'
        f'<p>{e(cur_title)}</p></div>'
        f'<div class="pdp-after">{sec_rec} Title</div>'
        f'<p>{e(opt_title)}</p></div>'
        f'</div>')
    out.append(_reason_chips(card.get("titleReasons", [])))
    out.append('</div>')

    # ── Item Highlights
    highlights = str(card.get("itemHighlights", "") or "")
    if highlights:
        out.append(
            f'<div class="pdp-section">'
            f'{sec_rec} Item Highlights</div>'
            f'<p class="ih-text">{e(highlights)}</p></div>')

    # ── Bullets comparison (always side-by-side)
    cur_bullets = card.get("currentBullets") or []
    rec_bullets = card.get("recommendedBullets") or []
    if rec_bullets:
        out.append(f'<div class="pdp-section"><div class="pdp-compare">')
        out.append(f'<div class="pdp-before">{sec_cur} Bullets</div><ul>')
        if cur_bullets:
            for i, b in enumerate(cur_bullets, 1):
                out.append(
                    f'<li><span class="pdp-bullet-num">{i}</span>'
                    f'<span class="pdp-bullet-text">{e(str(b))}</span></li>')
        else:
            out.append('<li><span class="pdp-bullet-text" style="color:var(--muted2);'
                       'font-style:italic">No current bullets available</span></li>')
        out.append('</ul></div>')
        out.append(f'<div class="pdp-after">{sec_rec} Bullets</div><ul>')
        for i, b in enumerate(rec_bullets, 1):
            text = b.get("text", b) if isinstance(b, dict) else str(b)
            out.append(
                f'<li><span class="pdp-bullet-num">{i}</span>'
                f'<span class="pdp-bullet-text">{e(str(text))}</span></li>')
        out.append('</ul></div></div>')
        out.append(_reason_chips(card.get("bulletReasons", [])))
        out.append('</div>')

    # ── Description comparison (always side-by-side)
    cur_desc = str(card.get("currentDescription", "") or "")
    rec_desc = str(card.get("recommendedDescription", "") or "")
    if rec_desc:
        out.append(f'<div class="pdp-section"><div class="pdp-compare">')
        out.append(
            f'<div class="pdp-before">{sec_cur} Description</div>'
            f'<p class="pdp-desc-text">{e(cur_desc) if cur_desc else "<em style=&quot;color:var(--muted2)&quot;>No current description available</em>"}</p></div>')
        out.append(
            f'<div class="pdp-after">{sec_rec} Description</div>'
            f'<p class="pdp-desc-text">{e(rec_desc)}</p></div>'
            f'</div>')
        out.append(_reason_chips(card.get("descriptionReasons", [])))
        out.append('</div>')

    # ── Self-directed analysis (credibility + intent + SEO/AEO)
    sda = card.get("selfDirectedAnalysis") or {}
    if sda:
        out.append(_self_directed_block(sda))

    out.append('</div>')
    return "".join(out)


_REASON_LEGEND = (
    '<div class="pdp-reason-legend">'
    '<span class="reason-keep"><span class="reason-icon">✓</span> Retained</span>'
    '<span class="reason-add"><span class="reason-icon">+</span> Added</span>'
    '<span class="reason-remove"><span class="reason-icon">✕</span> Removed</span>'
    '</div>'
)


def _reason_chips(reasons: list[dict]) -> str:
    """Render change reasons as compact grid items with inline icon + label — detail."""
    if not reasons:
        return ""
    out = [_REASON_LEGEND, '<div class="pdp-reasons">']
    for r in reasons:
        rtype = r.get("type", "add")
        icon = {"keep": "✓", "add": "+", "remove": "✕"}.get(rtype, "·")
        cls = f"reason-{rtype}"
        label = str(r.get("label", ""))[:120]
        detail = str(r.get("detail", ""))
        detail_html = (f' <span class="reason-detail">&mdash; {_html.escape(detail)}</span>'
                       if detail else "")
        out.append(
            f'<div class="pdp-reason {cls}">'
            f'<span class="reason-icon">{icon}</span>'
            f'<div><span class="reason-label">{_html.escape(label)}</span>'
            f'{detail_html}</div></div>')
    out.append('</div>')
    return "".join(out)


def _self_directed_block(sda: dict) -> str:
    """Render credibility profile, intent model, and SEO/AEO notes."""
    e = _html.escape
    out = [
        '<div class="pdp-section pdp-analysis">'
        '<div class="pdp-sec-title">Optimization Analysis</div>'
    ]

    ccp = sda.get("content_credibility_profile") or {}
    if ccp:
        out.append('<div class="analysis-group">'
                   '<div class="analysis-label">Content Credibility Profile</div>')
        for tier, label, cls in [
            ("carry_forward", "Carry Forward (Tier A)", "tier-a"),
            ("softened", "Softened (Tier B)", "tier-b"),
            ("removed", "Removed (Tier C)", "tier-c"),
        ]:
            items = ccp.get(tier) or []
            if items:
                out.append(f'<div class="tier-group {cls}">'
                           f'<span class="tier-label">{label}</span><ul>')
                for item in items:
                    out.append(f'<li>{e(str(item))}</li>')
                out.append('</ul></div>')
        out.append('</div>')

    out.append('</div>')
    return "".join(out)


def _exec_summary(hero: dict, ins: dict, brand: str, cat: str) -> str:
    """Executive Summary section: KPI cards + verdict + deliverables list."""
    sov = hero.get("your_sov", 0)
    rank = hero.get("rank", 0)
    org = hero.get("organic", 0)
    paid = hero.get("paid", 0)
    verdict = ins.get("verdict", "")

    kpis = (
        '<div class="exec-kpi-row">'
        f'<div class="exec-kpi" style="--c:var(--electric)">'
        f'<div class="exec-kpi-val" style="color:var(--electric)">{sov:.1f}%</div>'
        f'<div class="exec-kpi-lbl">Combined SOV</div></div>'
        f'<div class="exec-kpi" style="--c:var(--good)">'
        f'<div class="exec-kpi-val" style="color:var(--good)">#{rank}</div>'
        f'<div class="exec-kpi-lbl">Category Rank</div></div>'
        f'<div class="exec-kpi" style="--c:var(--electric)">'
        f'<div class="exec-kpi-val">{org:.1f}</div>'
        f'<div class="exec-kpi-lbl">Organic Pts</div></div>'
        f'<div class="exec-kpi" style="--c:var(--status-amber-bg)">'
        f'<div class="exec-kpi-val">{paid:.1f}</div>'
        f'<div class="exec-kpi-lbl">Paid Pts</div></div>'
        '</div>'
    )

    verdict_html = (
        f'<div class="verdict" style="background:#FBF7FF;border-left:4px solid var(--electric);'
        f'border-radius:8px;padding:14px 22px;font-size:15px;margin:22px 0">'
        f'<p class="prose"><strong>{_html.escape(verdict)}</strong></p></div>'
        if verdict else "")

    deliverables = (
        '<ul class="deliverables">'
        f'<li><span class="dl-ic">📊</span> Share-of-Search leaderboard — where {_html.escape(brand)} '
        f'ranks in {_html.escape(cat)}</li>'
        '<li><span class="dl-ic">🔍</span> Sub-category breakdown — who owns each niche</li>'
        '<li><span class="dl-ic">🎯</span> Keyword opportunities — whitespace and zero-SOV gaps</li>'
        '<li><span class="dl-ic">🛠</span> SKU optimization — deep PDP content audit with AI</li>'
        '<li><span class="dl-ic">🏆</span> How you win — organic and paid levers to grow share</li>'
        '</ul>')

    body = kpis + verdict_html + deliverables
    return _section("01", "Executive Summary",
                    f"A snapshot of {_html.escape(brand)}'s competitive position "
                    f"in {_html.escape(cat)} and what this report covers.",
                    body, section_id="exec")


def _cat_exec_summary(hero: dict, ins: dict, cat: str) -> str:
    """Executive Summary for Category report: KPI cards + verdict + deliverables."""
    top_brand = _html.escape(str(hero.get("top_brand", "—")))
    top_sov = hero.get("top_sov", 0)
    nbrands = hero.get("brands", 0)
    nkws = hero.get("keywords", 0)
    verdict = ins.get("verdict", "")

    kpis = (
        '<div class="exec-kpi-row">'
        f'<div class="exec-kpi" style="--c:var(--electric)">'
        f'<div class="exec-kpi-val" style="color:var(--electric)">{top_brand}</div>'
        f'<div class="exec-kpi-lbl">Top Brand · {top_sov:.1f}% SOV</div></div>'
        f'<div class="exec-kpi" style="--c:var(--cobalt)">'
        f'<div class="exec-kpi-val" style="color:var(--cobalt)">{nbrands:,}</div>'
        f'<div class="exec-kpi-lbl">Brands Competing</div></div>'
        f'<div class="exec-kpi" style="--c:var(--sky)">'
        f'<div class="exec-kpi-val" style="color:var(--sky)">{nkws:,}</div>'
        f'<div class="exec-kpi-lbl">Keywords Tracked</div></div>'
        f'<div class="exec-kpi" style="--c:var(--good)">'
        f'<div class="exec-kpi-val" style="color:var(--good)">{top_sov:.1f}%</div>'
        f'<div class="exec-kpi-lbl">Leader SOV</div></div>'
        '</div>')

    verdict_html = (
        f'<div class="verdict" style="background:#FBF7FF;border-left:4px solid var(--electric);'
        f'border-radius:8px;padding:14px 22px;font-size:15px;margin:22px 0">'
        f'<p class="prose"><strong>{_html.escape(verdict)}</strong></p></div>'
        if verdict else "")

    deliverables = (
        '<ul class="deliverables">'
        f'<li><span class="dl-ic">📊</span> Category leaderboard — who dominates '
        f'{_html.escape(cat)}</li>'
        '<li><span class="dl-ic">🔍</span> Sub-category breakdown — niche leaders</li>'
        '<li><span class="dl-ic">🎯</span> Highest-demand keywords — where shoppers search</li>'
        '<li><span class="dl-ic">🏆</span> How to win — organic and paid levers</li>'
        '</ul>')

    body = kpis + verdict_html + deliverables
    return _section("01", "Executive Summary",
                    f"A snapshot of the competitive landscape in "
                    f"{_html.escape(cat)} and what this report covers.",
                    body, section_id="exec")


def _sticky_nav(sections: list[tuple[str, str]]) -> str:
    """Build a sticky nav bar from a list of (anchor_id, label) tuples."""
    links = "".join(
        f'<a class="nav-item" href="#{_html.escape(sid)}">{_html.escape(lab)}</a>'
        for sid, lab in sections)
    return f'<nav class="sticky-nav">{links}</nav>'


def build_themed_report(scope: dict, ins: dict, d: dict,
                        narrative_source: str = "template") -> str:
    cat = _sentence(scope.get("category_value", ""))
    brand = str(scope.get("brand_label", ""))
    h = d.get("hero", {})
    rank_txt = f" · #{h['rank']}" if h.get("rank") else ""
    src = "AI · OpenAI" if narrative_source == "openai" else "rule-based"

    kw_count = scope.get("extras", {}).get("total_keywords", "")
    kw_line = f'{kw_count} search terms analysed' if kw_count else ""

    hero_block = (
        f'<div class="cover">'
        f'<div class="cover-accent-bar"></div>'
        f'<div class="cover-brand">CommerceIQ Intelligence</div>'
        f'<h1 class="cover-title">Share of Search &amp; Competitive Intelligence Report</h1>'
        f'<div class="cover-subtitle">{_html.escape(brand)}</div>'
        f'<div class="cover-divider"></div>'
        f'<div class="cover-meta">'
        f'<span class="meta-label">Prepared by</span>'
        f'<span class="meta-value">CommerceIQ Strategic Intelligence Team</span>'
        f'<span class="meta-label">Prepared for</span>'
        f'<span class="meta-value">{_html.escape(brand)} Retail Media Leadership</span>'
        f'<span class="meta-label">Category</span>'
        f'<span class="meta-value">{_html.escape(cat)} — Amazon US</span>'
        + (f'<span class="meta-label">Keywords</span>'
           f'<span class="meta-value">{_html.escape(str(kw_line))}</span>'
           if kw_line else "")
        + f'<span class="meta-label">Status</span>'
        f'<span class="meta-value">Confidential — For Internal Use Only</span>'
        f'</div></div>')

    # Build sections list with (anchor_id, nav_label, html) for nav generation
    nav_entries: list[tuple[str, str]] = []
    secs = []

    # 01 — Executive Summary (always present)
    nav_entries.append(("exec", "Executive Summary"))
    secs.append(_exec_summary(h, ins, brand, cat))
    n = 2

    if d.get("leaderboard"):
        legend = ('<span><i style="background:linear-gradient(90deg,#C231FF,#a01fe0)"></i>Organic</span>'
                  '<span><i style="background:linear-gradient(90deg,#5AAFFE,#1F22B2)"></i>Paid</span>')
        sid = "lb"
        nav_entries.append((sid, "Leaderboard"))
        secs.append(_section(f"{n:02d}", "Share-of-Search Leaderboard",
                             ins.get("organic_paid", ""), _combined_lb(d["leaderboard"]),
                             note=ins.get("leaderboard", ""), legend=legend,
                             section_id=sid))
        n += 1
    if d.get("subcats"):
        sid = "subcats"
        nav_entries.append((sid, "Sub-Categories"))
        secs.append(_section(f"{n:02d}", "Sub-Category Leaders",
                             ins.get("subcategories", ""), _subcards(d["subcats"], cat),
                             note=ins.get("readiness", ""), section_id=sid))
        n += 1
    if d.get("whitespace"):
        sid = "kws"
        nav_entries.append((sid, "Opportunities"))
        secs.append(_section(f"{n:02d}", "Keyword Opportunities — Whitespace",
                             ins.get("keywords", ""),
                             _kwlines(d["whitespace"], "crawls", "your_sov", "your SOV"),
                             section_id=sid))
        n += 1
    if d.get("zero_sov"):
        sid = "zero"
        nav_entries.append((sid, "Missed Opportunities"))
        secs.append(_section(
            f"{n:02d}", "Top Missed Opportunities — Zero SOV",
            ins.get("zero_sov", "Highest-volume searches where you currently have "
                                 "no organic or paid presence at all."),
            _kwlines(d["zero_sov"], "crawls", "crawls", "searches", fmt="count"),
            section_id=sid))
        n += 1
    if d.get("sku_opt") and d["sku_opt"].get("card"):
        so = d["sku_opt"]
        sid = "sku"
        nav_entries.append((sid, "SKU Optimization"))
        secs.append(_section(
            f"{n:02d}", "SKU Optimization",
            so.get("intro", ""), _sku_pdp_card(so["card"]),
            note=ins.get("sku_opt", ""), section_id=sid))
        n += 1
    # How you win (always present)
    sid = "win"
    nav_entries.append((sid, "How You Win"))
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
                         ins.get("how_you_win", ""), levers, section_id=sid))

    nav_bar = _sticky_nav(nav_entries)

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
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{_THEME_CSS}</style></head><body>
<div class="topbar"><div class="wrap"><div class="brandlogo"><span class="dot"></span>CommerceIQ</div>
<div class="confid">Generated report</div></div></div>
{hero_block}
{nav_bar}
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
        f'<div class="cover">'
        f'<div class="cover-accent-bar"></div>'
        f'<div class="cover-brand">CommerceIQ Intelligence</div>'
        f'<h1 class="cover-title">Category Share of Search Intelligence Report</h1>'
        f'<div class="cover-subtitle">{_html.escape(cat)}</div>'
        f'<div class="cover-divider"></div>'
        f'<div class="cover-meta">'
        f'<span class="meta-label">Prepared by</span>'
        f'<span class="meta-value">CommerceIQ Strategic Intelligence Team</span>'
        f'<span class="meta-label">Category</span>'
        f'<span class="meta-value">{_html.escape(cat)} — Amazon US</span>'
        f'<span class="meta-label">Brands</span>'
        f'<span class="meta-value">{h.get("brands", 0):,} brands competing</span>'
        f'<span class="meta-label">Keywords</span>'
        f'<span class="meta-value">{h.get("keywords", 0):,} search terms tracked</span>'
        f'<span class="meta-label">Status</span>'
        f'<span class="meta-value">Confidential — For Internal Use Only</span>'
        f'</div></div>')

    secs = []
    nav_entries: list[tuple[str, str]] = []
    n = 1

    exec_sec = _cat_exec_summary(h, ins, cat)
    secs.append(exec_sec)
    nav_entries.append(("exec", "Executive Summary"))
    n += 1

    if d.get("leaderboard"):
        sid = "lb"
        legend = (
            '<span><i style="background:linear-gradient(90deg,#C231FF,#a01fe0)"></i>Organic</span>'
            '<span><i style="background:linear-gradient(90deg,#5AAFFE,#1F22B2)"></i>Paid</span>')
        secs.append(_section(
            f"{n:02d}", f"Category Leaderboard — {cat}",
            ins.get("leaderboard", ""), _combined_lb(d["leaderboard"]),
            note=ins.get("organic_paid", ""), legend=legend, section_id=sid))
        nav_entries.append((sid, "Leaderboard"))
        n += 1

    if d.get("subcats"):
        sid = "subcats"
        secs.append(_section(
            f"{n:02d}", "Sub-Category Breakdown",
            ins.get("subcategories", ""), _cat_subcards(d["subcats"], cat),
            note="No single brand dominates every sub-category — "
                 "this is where challenger brands find their opening.",
            section_id=sid))
        nav_entries.append((sid, "Sub-Categories"))
        n += 1

    if d.get("keywords"):
        sid = "kws"
        secs.append(_section(
            f"{n:02d}", "Highest-Demand Keywords",
            ins.get("keywords", ""), _demand_kwlines(d["keywords"]),
            section_id=sid))
        nav_entries.append((sid, "Keywords"))
        n += 1

    sid = "win"
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
        ins.get("how_you_win", ""), levers, section_id=sid))
    nav_entries.append((sid, "How to Win"))

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

    nav_bar = _sticky_nav(nav_entries)

    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_html.escape(str(scope.get("name") or f"Category SoS — {cat}"))}</title>'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link href="https://fonts.googleapis.com/css2?family=DM+Sans:'
        f'wght@400;500;600;700;800;900&family=DM+Mono:wght@400;500'
        f'&display=swap" rel="stylesheet">'
        f'<style>{_THEME_CSS}</style></head><body>'
        f'<div class="topbar"><div class="wrap">'
        f'<div class="brandlogo"><span class="dot"></span>CommerceIQ</div>'
        f'<div class="confid">Category Intelligence Report</div>'
        f'</div></div>'
        f'{hero}'
        f'{nav_bar}'
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


def _incr_hero_cards(h: dict) -> str:
    """Six hero metric cards for the incrementality report header.
    Uses the .heroband class so .cell/.k/.v inherit the dark hero styling."""
    cards = [
        ("Keywords Analysed", str(h.get("total_keywords", 0)), "#fff"),
        ("Avg Organic SOV", f"{h.get('avg_organic', 0):.1f}%", "var(--electric)"),
        ("Avg Sponsored SOV", f"{h.get('avg_paid', 0):.1f}%", "var(--sky)"),
        ("Cannibalization Terms", str(h.get("cannibalizing", 0)), "#e05a00"),
        ("Growth Opportunity Terms", str(h.get("growth_terms", 0)), "var(--cobalt)"),
        ("Moderate Risk Terms", str(h.get("balanced", 0)), "var(--sky)"),
    ]
    cells = "".join(
        f'<div class="cell"><div class="k">{_html.escape(label)}</div>'
        f'<div class="v" style="color:{color}">{_html.escape(val)}</div></div>'
        for label, val, color in cards)
    return f'<div class="heroband">{cells}</div>'


def _incr_thesis(d: dict) -> str:
    """Central thesis section: three color-coded problem statements."""
    kws = d.get("keywords", [])
    ks = d.get("keyword_summary", {})
    n_can = ks.get("cannibalizing", 0)
    n_paid = ks.get("paid_dependent", 0)
    n_dark = ks.get("dark_spot", 0)
    n_org = ks.get("organic_led", 0)
    n_growth = n_paid + n_dark

    # Pick example keywords for each bucket
    can_examples = [k["search_term"] for k in kws
                    if k.get("classification") == "Cannibalizing"][:3]
    growth_examples = [k["search_term"] for k in kws
                       if k.get("classification") in ("Paid-dependent", "Dark Spot")][:3]
    org_examples = [k["search_term"] for k in kws
                    if k.get("classification") == "Organic-led"][:3]

    def _ex(items):
        if not items:
            return ""
        return ('<div style="font-family:var(--mono);font-size:11px;color:var(--muted);'
                'margin-top:8px">e.g. ' +
                ", ".join(f'"{_html.escape(k)}"' for k in items) + "</div>")

    return (
        '<div style="display:grid;gap:16px;margin-top:8px">'
        # Red — Cannibalization
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-left:5px solid #e05a00;border-radius:14px;padding:20px 24px">'
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        '<span style="font-size:18px">&#128308;</span>'
        '<strong style="font-size:16px">Sponsored Cannibalization</strong>'
        f'<span class="inc-tag" style="background:#e05a00">{n_can} terms</span></div>'
        f'<p style="color:var(--muted);font-size:14px">'
        f'Keywords where the brand has Organic SOV &ge; 2.5% AND Paid SOV &ge; 1.5%. '
        f'The brand is paying for shelf positions it already owns organically.</p>'
        f'{_ex(can_examples)}</div>'
        # Yellow — Under-investment
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-left:5px solid var(--cobalt);border-radius:14px;padding:20px 24px">'
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        '<span style="font-size:18px">&#128993;</span>'
        '<strong style="font-size:16px">Under-Investment in Growth</strong>'
        f'<span class="inc-tag" style="background:var(--cobalt)">{n_growth} terms</span></div>'
        f'<p style="color:var(--muted);font-size:14px">'
        f'{n_dark} keywords with combined SOV &lt; 0.5% (Dark Spots) and '
        f'{n_paid} where paid fraction &ge; 65% (Paid-dependent). '
        f'Either invisible or entirely reliant on ads.</p>'
        f'{_ex(growth_examples)}</div>'
        # Green — Organic strongholds
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-left:5px solid var(--electric);border-radius:14px;padding:20px 24px">'
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        '<span style="font-size:18px">&#128994;</span>'
        '<strong style="font-size:16px">Organic Strongholds</strong>'
        f'<span class="inc-tag" style="background:var(--electric)">{n_org} terms</span></div>'
        f'<p style="color:var(--muted);font-size:14px">'
        f'Keywords where paid fraction &le; 15%. Free traffic to protect — '
        f'these earn share without spend and compound over time.</p>'
        f'{_ex(org_examples)}</div>'
        '</div>')


def _incr_kw_table_v2(keywords: list[dict], max_rows: int = 20,
                      note: str = "") -> str:
    """Reusable keyword table for incrementality sections.
    Columns: Search Term, Category, Rank, Organic SOV%, Sponsored SOV%,
    Paid Fraction%, Classification badge.
    Rows color-coded by classification."""
    if not keywords:
        return ""
    shown = keywords[:max_rows]
    total = len(keywords)

    _ROW_BG = {
        "Cannibalizing": "rgba(224,90,0,.06)",
        "Paid-dependent": "rgba(90,175,254,.06)",
        "Organic-led": "rgba(194,49,255,.06)",
        "Dark Spot": "rgba(154,142,168,.06)",
        "Balanced": "transparent",
    }

    gcols = "grid-template-columns:40px 1fr 120px 60px 100px 100px 100px 130px"
    out = [
        f'<div class="lb">'
        f'<div class="lbrow head" style="{gcols}">'
        f'<span>#</span><span>Search Term</span><span>Category</span>'
        f'<span>Rank</span><span>Organic SOV</span><span>Sponsored SOV</span>'
        f'<span>Paid Frac.</span><span>Classification</span></div>']
    for i, kw in enumerate(shown):
        cls = kw.get("classification", "Balanced")
        tag_color = _INC_TAG_COLORS.get(cls, "var(--muted2)")
        bg = _ROW_BG.get(cls, "transparent")
        org = kw.get("organic_sov", 0)
        paid = kw.get("paid_sov", 0)
        pf = kw.get("paid_fraction", 0)
        rank = kw.get("rank", "-")
        cat = str(kw.get("category", ""))[:20]
        out.append(
            f'<div class="lbrow" style="{gcols};background:{bg}">'
            f'<div class="lbrank">{i + 1}</div>'
            f'<div style="font-weight:600;font-size:13.5px;min-width:0;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap">'
            f'{_html.escape(str(kw.get("search_term", "")))}</div>'
            f'<div style="font-size:12px;color:var(--muted);overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap">{_html.escape(cat)}</div>'
            f'<div style="font-family:var(--mono);font-weight:600;font-size:14px;'
            f'text-align:center">#{rank}</div>'
            f'<div style="font-family:var(--mono);font-size:13px;text-align:right">'
            f'{org:.1f}%</div>'
            f'<div style="font-family:var(--mono);font-size:13px;text-align:right">'
            f'{paid:.1f}%</div>'
            f'<div style="font-family:var(--mono);font-size:13px;text-align:right">'
            f'{pf:.0f}%</div>'
            f'<div><span class="inc-tag" style="background:{tag_color}">'
            f'{_html.escape(cls)}</span></div></div>')
    out.append("</div>")
    if total > max_rows:
        out.append(f'<div style="font-family:var(--mono);font-size:11px;'
                   f'color:var(--muted2);margin-top:8px;text-align:right">'
                   f'Showing top {max_rows} of {total} terms</div>')
    if note:
        out.append(f'<div class="note" style="margin-top:12px">'
                   f'<span class="ic">&#9612;</span><p>{_inl(note)}</p></div>')
    return "".join(out)


def _incr_cannibal_cards(keywords: list[dict]) -> str:
    """Individual audit cards for each cannibalizing keyword (cap at 15)."""
    cannibal = [k for k in keywords if k.get("classification") == "Cannibalizing"]
    if not cannibal:
        return '<p style="color:var(--muted)">No cannibalizing keywords detected.</p>'
    shown = cannibal[:15]
    out = ['<div class="inc-grid">']
    for kw in shown:
        org = kw.get("organic_sov", 0)
        paid = kw.get("paid_sov", 0)
        comb = kw.get("combined_sov", 0)
        pf = kw.get("paid_fraction", 0)
        rank = kw.get("rank", "?")
        term = str(kw.get("search_term", ""))
        total = org + paid or 1
        wo = org / total * 100
        wp = paid / total * 100
        out.append(
            f'<div class="inc-card" style="border-left:4px solid #e05a00">'
            f'<div style="font-weight:800;font-size:16px;margin-bottom:12px">'
            f'{_html.escape(term)}</div>'
            # Stats row
            f'<div class="inc-stats" style="flex-wrap:wrap;gap:10px;margin-bottom:12px">'
            f'<span>Organic <b>{org:.1f}%</b></span>'
            f'<span>Sponsored <b>{paid:.1f}%</b></span>'
            f'<span>Combined <b>{comb:.1f}%</b></span>'
            f'<span>Paid Frac. <b>{pf:.0f}%</b></span>'
            f'<span>Rank <b>#{rank}</b></span></div>'
            # SOV bar
            f'<div class="inc-bar-wrap"><div class="inc-bar">'
            f'<i class="seg-org" style="width:{wo:.0f}%"></i>'
            f'<i class="seg-paid" style="width:{wp:.0f}%"></i></div></div>'
            # Insight + Action
            f'<div style="margin-top:12px;display:grid;gap:8px">'
            f'<div style="font-size:13px;color:var(--muted);display:flex;gap:8px">'
            f'<span style="flex:none">&#128161;</span>'
            f'<span>Strong organic rank (#{rank}) — already visible without ads</span></div>'
            f'<div style="font-size:13px;color:var(--ink);display:flex;gap:8px;font-weight:600">'
            f'<span style="flex:none">&#9889;</span>'
            f'<span>Reduce/pause paid spend — reallocate to growth terms</span></div>'
            f'</div></div>')
    out.append("</div>")
    if len(cannibal) > 15:
        out.append(f'<div style="font-family:var(--mono);font-size:11px;'
                   f'color:var(--muted2);margin-top:8px;text-align:right">'
                   f'Showing 15 of {len(cannibal)} cannibalizing terms</div>')
    return "".join(out)


def _incr_realloc_framework(ks: dict) -> str:
    """Three-priority budget reallocation narrative."""
    n_can = ks.get("cannibalizing", 0)
    n_bal = ks.get("balanced", 0)
    n_growth = ks.get("paid_dependent", 0) + ks.get("dark_spot", 0)
    return (
        '<div style="display:grid;gap:16px">'
        # Priority 1
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:14px;padding:22px;border-top:4px solid #e05a00">'
        '<div style="font-family:var(--mono);font-size:11px;letter-spacing:.1em;'
        'text-transform:uppercase;color:#e05a00;font-weight:700;margin-bottom:6px">'
        'Priority 1 — Immediate</div>'
        f'<h3 style="font-size:18px;font-weight:800;margin-bottom:6px">'
        f'{n_can} Cannibalization Terms</h3>'
        '<p style="font-size:14px;color:var(--muted)">Reduce or pause paid spend on '
        'keywords where organic rank is strong. Redeploy freed budget to growth '
        'keywords immediately. No organic rank risk — the brand already owns '
        'these positions.</p></div>'
        # Priority 2
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:14px;padding:22px;border-top:4px solid var(--sky)">'
        '<div style="font-family:var(--mono);font-size:11px;letter-spacing:.1em;'
        'text-transform:uppercase;color:var(--sky);font-weight:700;margin-bottom:6px">'
        'Priority 2 — Phased (30-60 Days)</div>'
        f'<h3 style="font-size:18px;font-weight:800;margin-bottom:6px">'
        f'{n_bal} Moderate-Risk Terms</h3>'
        '<p style="font-size:14px;color:var(--muted)">Systematic bid management: '
        'test paid-down scenarios over 30-60 days to find the optimal organic-paid '
        'mix. Monitor organic rank as paid spend is reduced gradually.</p></div>'
        # Priority 3
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:14px;padding:22px;border-top:4px solid var(--cobalt)">'
        '<div style="font-family:var(--mono);font-size:11px;letter-spacing:.1em;'
        'text-transform:uppercase;color:var(--cobalt);font-weight:700;margin-bottom:6px">'
        'Priority 3 — Sustained Growth</div>'
        f'<h3 style="font-size:18px;font-weight:800;margin-bottom:6px">'
        f'{n_growth} Growth Opportunity Terms</h3>'
        '<p style="font-size:14px;color:var(--muted)">Accelerate investment in '
        'paid-dependent keywords (ads are the lifeline) and dark-spot keywords '
        '(zero presence, pure upside). Build organic content in parallel to '
        'reduce long-term ad dependency.</p></div>'
        '</div>')


def _incr_next_steps(brand: str) -> str:
    """Three-week action timeline + CTA."""
    return (
        '<div style="display:grid;gap:16px">'
        # Week 1
        '<div style="display:flex;gap:16px;align-items:flex-start">'
        '<div style="flex:none;width:80px;font-family:var(--mono);font-size:12px;'
        'font-weight:700;color:var(--electric);padding-top:2px">Week 1</div>'
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:12px;padding:16px 20px;flex:1">'
        '<strong>Audit cannibalization terms.</strong> '
        'Pull paid spend on the flagged keywords. Confirm organic rank holds. '
        'Reallocate freed budget to growth-opportunity terms.</div></div>'
        # Week 2
        '<div style="display:flex;gap:16px;align-items:flex-start">'
        '<div style="flex:none;width:80px;font-family:var(--mono);font-size:12px;'
        'font-weight:700;color:var(--electric);padding-top:2px">Week 2</div>'
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:12px;padding:16px 20px;flex:1">'
        '<strong>Launch growth campaigns.</strong> '
        'Target paid-dependent and dark-spot keywords with new sponsored campaigns. '
        'Begin content optimization for organic coverage on high-value terms.</div></div>'
        # Week 3
        '<div style="display:flex;gap:16px;align-items:flex-start">'
        '<div style="flex:none;width:80px;font-family:var(--mono);font-size:12px;'
        'font-weight:700;color:var(--electric);padding-top:2px">Week 3+</div>'
        '<div style="background:var(--paper);border:1px solid var(--line);'
        'border-radius:12px;padding:16px 20px;flex:1">'
        '<strong>Monitor and optimize.</strong> '
        'Track organic rank changes on moderate-risk terms. Iterate bid strategy '
        'based on results. Expand to additional categories.</div></div>'
        '</div>')


def build_incrementality_report(scope: dict, ins: dict, d: dict,
                                narrative_source: str = "template") -> str:
    """Incrementality report — 8-section structure matching Mondelez sample."""
    brand = _html.escape(str(scope.get("brand_label", "")))
    src = "AI · OpenAI" if narrative_source == "openai" else "rule-based"
    h = d.get("hero", {})
    ks = d.get("keyword_summary", {})

    keywords = d.get("keywords", [])

    cat = _html.escape(_sentence(scope.get("category_value", "")))
    kw_count = d.get("keyword_summary", {}).get("total_keywords", len(keywords))

    # ── Cover page ───────────────────────────────────────────────────────
    hero = (
        f'<div class="cover" id="exec">'
        f'<div class="cover-accent-bar"></div>'
        f'<div class="cover-brand">CommerceIQ Intelligence</div>'
        f'<h1 class="cover-title">Incrementality &amp; iROAS Intelligence Report</h1>'
        f'<div class="cover-subtitle">{brand}</div>'
        f'<div class="cover-divider"></div>'
        f'<div class="cover-meta">'
        f'<span class="meta-label">Prepared by</span>'
        f'<span class="meta-value">CommerceIQ Strategic Intelligence Team</span>'
        f'<span class="meta-label">Prepared for</span>'
        f'<span class="meta-value">{brand} Retail Media Leadership</span>'
        f'<span class="meta-label">Category</span>'
        f'<span class="meta-value">{cat} — Amazon US</span>'
        f'<span class="meta-label">Keywords</span>'
        f'<span class="meta-value">{kw_count} search terms analysed</span>'
        f'<span class="meta-label">Status</span>'
        f'<span class="meta-value">Confidential — For Internal Use Only</span>'
        f'</div></div>')

    # ── Sticky section nav (anchor jump links) ───────────────────────────
    _nav_items = [
        ("exec", "01 Executive Summary"),
        ("thesis", "02 Central Thesis"),
        ("sov", "03 SOV Dashboard"),
        ("audit", "04 Cannibalization"),
        ("medium", "05 Moderate Risk"),
        ("growth", "06 Growth"),
        ("budget", "07 Reallocation"),
        ("next", "08 Next Steps"),
    ]
    nav_links = "".join(
        f'<a href="#{sid}">{_html.escape(lab)}</a>'
        for sid, lab in _nav_items)
    nav_bar = (
        f'<nav class="toc-nav"><div class="wrap">{nav_links}</div></nav>')

    secs = []

    # ── 02 Central Thesis ────────────────────────────────────────────────
    secs.append(_section(
        "02", "Central Thesis",
        ins.get("thesis", ""),
        _incr_thesis(d),
        section_id="thesis"))

    # ── 03 Organic SOV Dashboard ─────────────────────────────────────────
    org_sorted = sorted(keywords, key=lambda k: k.get("organic_sov", 0),
                        reverse=True)[:20]
    legend = ('<span><i style="background:linear-gradient(90deg,#C231FF,#a01fe0)"></i>Organic</span>'
              '<span><i style="background:linear-gradient(90deg,#5AAFFE,#1F22B2)"></i>Paid</span>')
    secs.append(_section(
        "03", "Organic SOV Dashboard",
        ins.get("sov_dashboard", ""),
        _incr_kw_table_v2(org_sorted, max_rows=20),
        legend=legend, section_id="sov"))

    # ── 04 Cannibalization Audit ─────────────────────────────────────────
    secs.append(_section(
        "04", "Cannibalization Audit",
        ins.get("cannibalization", ""),
        _incr_cannibal_cards(keywords),
        section_id="audit"))

    # ── 05 Moderate-Risk Cluster ─────────────────────────────────────────
    balanced = [k for k in keywords if k.get("classification") == "Balanced"]
    secs.append(_section(
        "05", "Moderate-Risk Cluster",
        ins.get("moderate_risk", ""),
        _incr_kw_table_v2(balanced, max_rows=30,
                          note=f"Showing top {min(30, len(balanced))} of "
                               f"{len(balanced)} moderate-risk terms"
                          if balanced else ""),
        section_id="medium"))

    # ── 06 Growth Opportunities ──────────────────────────────────────────
    paid_dep = [k for k in keywords if k.get("classification") == "Paid-dependent"]
    dark_spot = [k for k in keywords if k.get("classification") == "Dark Spot"]
    growth_body = ""
    if paid_dep:
        growth_body += (
            '<div style="margin-bottom:24px">'
            '<h3 style="font-size:17px;font-weight:800;margin-bottom:12px">'
            f'&#128308; Tier 1: Paid-dependent ({len(paid_dep)} terms)</h3>'
            '<p style="font-size:13px;color:var(--muted);margin-bottom:12px">'
            'Keywords where paid fraction &ge; 65%. If the brand stopped advertising, '
            'it would lose all visibility on these terms.</p>'
            f'{_incr_kw_table_v2(paid_dep, max_rows=20)}</div>')
    if dark_spot:
        growth_body += (
            '<div>'
            '<h3 style="font-size:17px;font-weight:800;margin-bottom:12px">'
            f'&#9899; Tier 2: Dark Spots ({len(dark_spot)} terms)</h3>'
            '<p style="font-size:13px;color:var(--muted);margin-bottom:12px">'
            'Keywords with combined SOV &lt; 0.5%. Zero presence, pure upside.</p>'
            f'{_incr_kw_table_v2(dark_spot, max_rows=20)}</div>')
    if not growth_body:
        growth_body = ('<p style="color:var(--muted)">No growth-opportunity '
                       'keywords identified — the brand has broad coverage.</p>')
    secs.append(_section(
        "06", "Growth Opportunities",
        ins.get("growth", ""), growth_body,
        section_id="growth"))

    # ── 07 Budget Reallocation Framework ─────────────────────────────────
    secs.append(_section(
        "07", "Budget Reallocation Framework",
        ins.get("reallocation", ""),
        _incr_realloc_framework(ks),
        section_id="budget"))

    # ── 08 Next Steps ────────────────────────────────────────────────────
    secs.append(_section(
        "08", "Next Steps",
        ins.get("next_steps", ""),
        _incr_next_steps(brand),
        section_id="next"))

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
        f'<link href="https://fonts.googleapis.com/css2?family=DM+Sans:'
        f'wght@400;500;600;700;800;900&family=DM+Mono:wght@400;500'
        f'&display=swap" rel="stylesheet">'
        f'<style>{_THEME_CSS}'
        f'html{{scroll-behavior:smooth;scroll-padding-top:48px}}'
        f'.toc-nav{{position:sticky;top:0;z-index:90;background:var(--paper);'
        f'border-bottom:1px solid var(--line);padding:10px 0;margin-bottom:-1px}}'
        f'.toc-nav .wrap{{display:flex;gap:20px;overflow-x:auto;'
        f'font-family:var(--mono);font-size:10px;letter-spacing:.08em;'
        f'text-transform:uppercase;font-weight:600}}'
        f'.toc-nav a{{color:var(--muted2);text-decoration:none;'
        f'white-space:nowrap;padding:6px 0;transition:color .15s}}'
        f'.toc-nav a:hover{{color:var(--electric)}}'
        f'</style></head><body>'
        f'<div class="topbar"><div class="wrap">'
        f'<div class="brandlogo"><span class="dot"></span>CommerceIQ</div>'
        f'<div class="confid">Incrementality Analysis Report</div>'
        f'</div></div>'
        f'{hero}{nav_bar}'
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
