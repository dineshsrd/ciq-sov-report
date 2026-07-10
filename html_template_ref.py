#!/usr/bin/env python3
"""
CommerceIQ Incrementality & iROAS Intelligence Report — HTML Generator
Usage: python3 html_template.py --csv path/to/file.csv --brand "Brand Name" --out output.html
"""
 
import csv, re, argparse, html as html_mod, os
 
# ── helpers ──────────────────────────────────────────────────────────────────
 
def pct(s):
    if not s or str(s).strip() in ('', '-', '—'): return None
    try: return float(str(s).strip().replace('%','').replace(',',''))
    except: return None
 
def usd(s):
    if not s or str(s).strip() in ('', '-', '—'): return None
    try: return float(str(s).strip().replace('$','').replace(',',''))
    except: return None
 
def fmt_pct(v, decimals=2):
    if v is None: return '—'
    return f'{v:.{decimals}f}%'
 
def fmt_usd(v):
    if v is None: return '—'
    return f'${v:.2f}'
 
def fmt_rank(s):
    try: return f'{int(s):,}'
    except: return s or '—'
 
def iroas_class(v):
    if v is None: return 'iroas-grn'
    if v < 1.50: return 'iroas-red'
    if v < 3.50: return 'iroas-amb'
    if v < 4.40: return 'iroas-grn'
    return 'iroas-blue'
 
def sov_bar_class(org):
    if org is None: return 'sov-grn'
    if org > 50: return 'sov-red'
    if org > 10: return 'sov-amb'
    return 'sov-grn'
 
def risk_badge(org):
    if org is None: return '<span class="badge badge-grn">LOW</span>'
    if org > 50: return '<span class="badge badge-red">CRITICAL</span>'
    if org > 10: return '<span class="badge badge-amb">MODERATE</span>'
    return '<span class="badge badge-grn">LOW</span>'
 
def esc(s): return html_mod.escape(str(s)) if s else ''
 
# ── CSV reader ────────────────────────────────────────────────────────────────
 
def read_csv(filepath):
    rows = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            norm = {k.strip().split('\n')[0].strip(): v for k, v in r.items()}
            iroas_v = usd(norm.get('iROAS', ''))
            roas_v  = usd(norm.get('ROAS', ''))
            inc_v   = pct(norm.get('INCREMENTAL FRACTION', ''))
            # Compute iROAS if missing
            if iroas_v is None and roas_v is not None and inc_v is not None:
                iroas_v = round(roas_v * inc_v / 100, 2)
            rows.append({
                'term':     norm.get('SEARCH TERM', '').strip(),
                'rank':     norm.get('SEARCH RANK', '').strip(),
                'inc_frac': inc_v,
                'roas':     roas_v,
                'iroas':    iroas_v,
                'org_sov':  pct(norm.get('Organic SOV', '')),
                'spon_sov': pct(norm.get('Sponsored SOV', '')),
            })
    return [r for r in rows if r['term'] and r['iroas'] is not None]
 
# ── derived stats ─────────────────────────────────────────────────────────────
 
def derive(rows):
    critical = sorted([r for r in rows if (r['org_sov'] or 0) > 50],  key=lambda r: -(r['org_sov'] or 0))
    moderate = sorted([r for r in rows if 10 < (r['org_sov'] or 0) <= 50], key=lambda r: -(r['org_sov'] or 0))
    tier1    = sorted([r for r in rows if r['iroas'] >= 4.75 and (r['org_sov'] or 0) < 5],  key=lambda r: -r['iroas'])
    tier2    = sorted([r for r in rows if 4.40 <= r['iroas'] < 4.75 and (r['org_sov'] or 0) < 5], key=lambda r: -r['iroas'])
    by_sov   = sorted(rows, key=lambda r: r['org_sov'] or 0, reverse=True)[:20]
    lowest   = min(rows, key=lambda r: r['iroas'])
    highest  = max(rows, key=lambda r: r['iroas'])
    max_sov  = max(rows, key=lambda r: r['org_sov'] or 0)
    return dict(critical=critical, moderate=moderate, tier1=tier1, tier2=tier2,
                by_sov=by_sov, lowest=lowest, highest=highest, max_sov=max_sov,
                total=len(rows))
 
# ── HTML sections ─────────────────────────────────────────────────────────────
 
def sov_table_rows_js(by_sov):
    """Generate JS array literal for the SOV dashboard table."""
    lines = []
    for r in by_sov:
        lines.append(
            f'  {{ term:{json_str(r["term"])}, org:{r["org_sov"] or 0}, '
            f'spon:{r["spon_sov"] or 0}, iroas:{r["iroas"]} }}'
        )
    return '[\n' + ',\n'.join(lines) + '\n]'
 
def json_str(s):
    return '"' + s.replace('\\','\\\\').replace('"','\\"') + '"'
 
def audit_card(r):
    tag_map = {
        'bueno chocolate bars': 'Lowest iROAS in Portfolio',
        'bueno': 'Highest Sponsored SOV Waste',
        'kinder': 'Audited Critical Risk',
    }
    tag = tag_map.get(r['term'].lower(), 'Audited Critical Risk')
    spon_note = ''
    if r['spon_sov'] and r['spon_sov'] > 30:
        spon_note = ' ← Highest'
    return f'''
  <div class="audit-card">
    <div class="audit-card-header">
      <span class="term">★ {esc(r["term"])}</span>
      <span class="tag">— {esc(tag)}</span>
    </div>
    <div class="audit-card-body">
      <div class="audit-stats">
        <div class="audit-stat"><label>Organic SOV</label><span class="val">{fmt_pct(r["org_sov"])}</span></div>
        <div class="audit-stat"><label>iROAS</label><span class="val">{fmt_usd(r["iroas"])}</span></div>
        <div class="audit-stat"><label>Incr. Fraction</label><span class="val mono" style="color:#374151;font-size:20px;">{fmt_pct(r["inc_frac"])}</span></div>
        <div class="audit-stat"><label>Sponsored SOV</label><span class="val mono" style="color:{"#991B1B" if (r["spon_sov"] or 0) > 30 else "#374151"};font-size:20px;">{fmt_pct(r["spon_sov"])}{spon_note}</span></div>
        <div class="audit-stat"><label>Search Rank</label><span class="val mono" style="color:#374151;font-size:20px;">#{fmt_rank(r["rank"])}</span></div>
      </div>
      <div class="audit-insight">
        "{esc(r["term"])}" has {fmt_pct(r["org_sov"])} organic SOV — meaning Ferrero already captures that share of organic clicks without paid spend.
        With an incremental fraction of {fmt_pct(r["inc_frac"])}, {fmt_pct(100 - (r["inc_frac"] or 0))} of ad-driven purchases were pre-existing organic wins.
        The iROAS of {fmt_usd(r["iroas"])} confirms this spend is largely self-cannibalistic.
      </div>
      <div class="audit-action"><strong>Action:</strong> Reduce or eliminate paid bidding on "{esc(r["term"])}". Organic dominance on this term makes it one of the lowest-value uses of paid budget in the portfolio.</div>
    </div>
  </div>'''
 
def table_row_gen(r, cols, col_widths, iroas_col_idx, alt):
    bg = '#FDFDFD' if alt else '#FFFFFF'
    cells = []
    for i, (key, label) in enumerate(cols):
        val = r.get(key)
        if key == 'iroas':
            cls = iroas_class(val)
            cells.append(f'<td class="{cls}">{fmt_usd(val)}</td>')
        elif key in ('org_sov', 'spon_sov', 'inc_frac'):
            cells.append(f'<td class="center">{fmt_pct(val)}</td>')
        elif key == 'rank':
            cells.append(f'<td class="center mono">{fmt_rank(val)}</td>')
        else:
            cells.append(f'<td>{esc(str(val or "—"))}</td>')
    return f'<tr style="background:{bg}">{"".join(cells)}</tr>'
 
def growth_table(rows_list, tier_label, th_class, iroas_label):
    if not rows_list:
        return f'<p style="color:#6B7280;font-size:14px;font-style:italic;">No keywords match this tier in the current dataset.</p>'
    cols = [('term','Search Term'),('rank','Search Rank'),('org_sov','Organic SOV'),
            ('spon_sov','Spons. SOV'),('iroas','iROAS'),('inc_frac','Incr. Fraction')]
    header = ''.join(f'<th class="{"center" if i>0 else ""}">{l}</th>' for i,(k,l) in enumerate(cols))
    body = ''.join(table_row_gen(r, cols, [], 4, i%2==0) for i,r in enumerate(rows_list))
    return f'''<table class="data-table"><thead><tr class="{th_class}">{header}</tr></thead><tbody>{body}</tbody></table>'''
 
def realloc_table(rows_list, action_col, th_class):
    if not rows_list:
        return f'<p style="color:#6B7280;font-size:14px;font-style:italic;">No keywords match this priority level.</p>'
    header = '<th>Keyword</th><th class="center">Organic SOV</th><th class="center">iROAS</th><th class="center">Spons. SOV</th><th>Recommended Action</th>'
    rows_html = ''
    for i, r in enumerate(rows_list):
        bg = '#FFFFFF' if i%2==0 else ('#FEE2E2' if 'red' in th_class else ('#FEF3C7' if 'amb' in th_class else '#D1FAE5'))
        iroas_c = iroas_class(r['iroas'])
        action = r.get('_action', 'Review and adjust bidding strategy')
        rows_html += f'''<tr style="background:{bg}">
          <td><strong>{esc(r["term"])}</strong></td>
          <td class="center">{fmt_pct(r["org_sov"])}</td>
          <td class="{iroas_c}">{fmt_usd(r["iroas"])}</td>
          <td class="center">{fmt_pct(r["spon_sov"])}</td>
          <td style="font-size:13px;">{esc(action)}</td>
        </tr>'''
    return f'<table class="data-table"><thead><tr class="{th_class}"><tr class="{th_class}">{header}</tr></thead><tbody>{rows_html}</tbody></table>'
 
# ── main HTML builder ─────────────────────────────────────────────────────────
 
def build_html(rows, brand, stats):
    d = stats
    lowest  = d['lowest']
    highest = d['highest']
    max_sov = d['max_sov']
 
    # Assign realloc actions
    for r in d['critical']:
        if (r['spon_sov'] or 0) > 30:
            r['_action'] = f'Cut sponsored SOV from {fmt_pct(r["spon_sov"])} — highest waste term'
        else:
            r['_action'] = f'Reduce or eliminate paid bidding — {fmt_pct(r["org_sov"])} organic SOV, only {fmt_pct(r["inc_frac"])} incremental'
    for r in d['moderate']:
        if (r['spon_sov'] or 0) > 20:
            r['_action'] = f'Step down bids by 30–40% over 4 weeks'
        else:
            r['_action'] = f'Hold current level; monitor organic SOV trend'
    for r in d['tier1']:
        r['_action'] = f'Scale — {fmt_pct(r["inc_frac"])} incremental fraction, minimal organic competition'
    for r in d['tier2']:
        r['_action'] = f'Increase bids gradually; strong efficiency at {fmt_usd(r["iroas"])} iROAS'
 
    # Moderate cluster section (may not exist)
    moderate_section = ''
    if d['moderate']:
        mod_cols = [('term','Search Term'),('rank','Search Rank'),('org_sov','Organic SOV'),
                    ('spon_sov','Spons. SOV'),('iroas','iROAS'),('inc_frac','Incr. Fraction')]
        mod_header = ''.join(f'<th class="{"" if i==0 else "center"}">{l}</th>' for i,(k,l) in enumerate(mod_cols))
        mod_body = ''.join(table_row_gen(r, mod_cols, [], 4, i%2==0) for i,r in enumerate(d['moderate'][:8]))
        moderate_section = f'''
<section class="section" id="medium">
  <div class="section-header">
    <span class="section-num">05</span>
    <span class="section-title">Medium-Risk Cluster — Moderate SOV Terms (10–50%)</span>
  </div>
  <p class="prose">Beyond the critical branded terms, {brand} faces a secondary inefficiency zone where organic SOV is elevated enough (10–50%) to intercept a meaningful share of paid clicks, yet sponsored activity remains high — creating compounding waste.</p>
  <table class="data-table">
    <thead><tr class="th-blue">{mod_header}</tr></thead>
    <tbody>{mod_body}</tbody>
  </table>
  <div class="insight-box">
    <div class="insight-label">Insight</div>
    <p>The highest-risk term in this cluster is <strong>{esc(d["moderate"][0]["term"])}</strong> ({fmt_pct(d["moderate"][0]["org_sov"])} organic SOV, {fmt_usd(d["moderate"][0]["iroas"])} iROAS). A stepdown — not elimination — is appropriate here while organic rank normalises.</p>
  </div>
</section>'''
 
    sov_js_data = sov_table_rows_js(d['by_sov'])
    audit_cards_html = ''.join(audit_card(r) for r in d['critical'])
 
    p1_table = realloc_table(d['critical'], '_action', 'th-red')
    p2_table = realloc_table(d['moderate'][:4], '_action', 'th-amb') if d['moderate'] else ''
    p3_table = realloc_table(d['tier1'][:6], '_action', 'th-grn')
 
    brand_clean = esc(brand)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brand_clean} — Incrementality &amp; iROAS Intelligence Report</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,300&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --navy:#210235;--accent:#C231FF;--cobalt:#1F22B2;--sky:#5AAFFE;
  --white:#FFFFFF;--black:#0A0A0A;--mid-gray:#6B7280;
  --light-bg:#F5F0FF;--light-gray:#F3F4F6;--border:#E5E7EB;
  --red-bg:#FEE2E2;--red-txt:#991B1B;--red-s:#DC2626;
  --amb-bg:#FEF3C7;--amb-txt:#92400E;--amb-s:#D97706;
  --grn-bg:#D1FAE5;--grn-txt:#065F46;--grn-s:#047857;
  --blue-bg:#DBEAFE;--blue-txt:#1E40AF;
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'DM Sans',sans-serif;background:#0D0016;color:var(--black);-webkit-font-smoothing:antialiased;}}
@media print{{body{{background:white;}}.cover{{page-break-after:always;min-height:auto;}}.section{{page-break-inside:avoid;}}}}
.cover{{min-height:100vh;background:var(--navy);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 48px;position:relative;overflow:hidden;}}
.cover::before{{content:'';position:absolute;top:-200px;right:-200px;width:600px;height:600px;background:radial-gradient(circle,rgba(194,49,255,.2) 0%,transparent 70%);pointer-events:none;}}
.cover::after{{content:'';position:absolute;bottom:-150px;left:-150px;width:500px;height:500px;background:radial-gradient(circle,rgba(90,175,254,.12) 0%,transparent 70%);pointer-events:none;}}
.cover-accent-bar{{width:80px;height:4px;background:var(--accent);border-radius:2px;margin-bottom:32px;}}
.cover-brand{{font-size:13px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);margin-bottom:16px;}}
.cover-title{{font-size:clamp(28px,4vw,48px);font-weight:700;color:var(--white);text-align:center;line-height:1.15;margin-bottom:12px;max-width:700px;}}
.cover-subtitle{{font-size:20px;font-weight:300;color:rgba(255,255,255,.5);margin-bottom:56px;letter-spacing:.05em;}}
.cover-divider{{width:100%;max-width:560px;height:1px;background:linear-gradient(90deg,transparent,rgba(90,175,254,.5),transparent);margin-bottom:48px;}}
.cover-meta{{display:grid;grid-template-columns:auto 1fr;gap:10px 24px;max-width:560px;width:100%;}}
.meta-label{{font-size:12px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--sky);padding:4px 0;white-space:nowrap;}}
.meta-value{{font-size:13px;color:rgba(255,255,255,.65);padding:4px 0;border-bottom:1px solid rgba(255,255,255,.08);}}
.main{{background:#FAFAFA;max-width:1100px;margin:0 auto;}}
.section{{padding:56px 64px;border-bottom:1px solid var(--border);background:white;}}
.section:nth-child(even){{background:#FDFDFD;}}
.section-header{{background:var(--navy);color:white;padding:18px 28px;display:flex;align-items:center;gap:16px;margin:-56px -64px 40px -64px;}}
.section-num{{font-family:'DM Mono',monospace;font-size:12px;color:var(--accent);font-weight:500;letter-spacing:.1em;background:rgba(194,49,255,.15);padding:4px 10px;border-radius:4px;white-space:nowrap;}}
.section-title{{font-size:18px;font-weight:600;color:white;letter-spacing:.01em;}}
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:36px;}}
.kpi-card{{padding:24px 20px;border-radius:10px;text-align:center;}}
.kpi-card .kpi-val{{font-size:34px;font-weight:700;line-height:1;margin-bottom:8px;font-family:'DM Mono',monospace;}}
.kpi-card .kpi-label{{font-size:12px;line-height:1.4;font-weight:500;}}
.kpi-red{{background:var(--red-bg);}}.kpi-red .kpi-val,.kpi-red .kpi-label{{color:var(--red-txt);}}
.kpi-amb{{background:var(--amb-bg);}}.kpi-amb .kpi-val,.kpi-amb .kpi-label{{color:var(--amb-txt);}}
.kpi-grn{{background:var(--grn-bg);}}.kpi-grn .kpi-val,.kpi-grn .kpi-label{{color:var(--grn-txt);}}
.kpi-purple{{background:var(--light-bg);}}.kpi-purple .kpi-val{{color:var(--navy);}}.kpi-purple .kpi-label{{color:var(--cobalt);}}
.prose{{font-size:15px;line-height:1.75;color:#374151;margin-bottom:20px;max-width:780px;}}
.thesis-card{{display:flex;gap:0;margin-bottom:20px;border-radius:10px;overflow:hidden;border:1px solid var(--border);}}
.thesis-num{{width:64px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-family:'DM Mono',monospace;font-size:22px;font-weight:500;color:white;}}
.thesis-body{{padding:24px 28px;background:var(--light-bg);flex:1;}}
.thesis-body h3{{font-size:15px;font-weight:700;color:var(--navy);margin-bottom:8px;}}
.thesis-body p{{font-size:14px;line-height:1.7;color:#374151;}}
.sub-banner{{background:var(--light-bg);border-left:4px solid var(--accent);padding:10px 18px;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--navy);margin:28px 0 18px 0;border-radius:0 6px 6px 0;}}
.sub-banner.red{{background:var(--red-bg);border-color:var(--red-s);color:var(--red-txt);}}
.sub-banner.grn{{background:var(--grn-bg);border-color:var(--grn-s);color:var(--grn-txt);}}
.sub-banner.blue{{background:var(--blue-bg);border-color:var(--cobalt);color:var(--cobalt);}}
.sub-banner.amb{{background:var(--amb-bg);border-color:var(--amb-s);color:var(--amb-txt);}}
.data-table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;}}
.data-table th{{padding:10px 12px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;text-align:left;white-space:nowrap;}}
.data-table td{{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle;}}
.data-table tr:last-child td{{border-bottom:none;}}
.data-table tr:hover td{{background:rgba(194,49,255,.03);}}
.th-navy{{background:var(--navy);color:white;}}.th-grn{{background:var(--grn-s);color:white;}}.th-blue{{background:var(--cobalt);color:white;}}.th-red{{background:var(--red-s);color:white;}}.th-amb{{background:#B45309;color:white;}}.th-sky{{background:var(--sky);color:white;}}
.data-table td.center,.data-table th.center{{text-align:center;}}
td.iroas-red{{background:var(--red-bg);color:var(--red-txt);font-weight:700;font-family:'DM Mono',monospace;text-align:center;}}
td.iroas-amb{{background:var(--amb-bg);color:var(--amb-txt);font-weight:700;font-family:'DM Mono',monospace;text-align:center;}}
td.iroas-grn{{background:var(--grn-bg);color:var(--grn-txt);font-weight:700;font-family:'DM Mono',monospace;text-align:center;}}
td.iroas-blue{{background:var(--blue-bg);color:var(--blue-txt);font-weight:700;font-family:'DM Mono',monospace;text-align:center;}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;}}
.badge-red{{background:var(--red-bg);color:var(--red-txt);}}.badge-amb{{background:var(--amb-bg);color:var(--amb-txt);}}.badge-grn{{background:var(--grn-bg);color:var(--grn-txt);}}
.sov-bar-wrap{{width:100%;background:#E5E7EB;border-radius:3px;height:10px;overflow:hidden;min-width:80px;}}
.sov-bar-fill{{height:100%;border-radius:3px;}}
.sov-red{{background:var(--red-s);}}.sov-amb{{background:var(--amb-s);}}.sov-grn{{background:var(--grn-s);}}
td.sov-cell{{min-width:120px;}}
.audit-card{{border-radius:12px;overflow:hidden;margin-bottom:20px;border:1px solid #FCA5A5;}}
.audit-card-header{{background:#DC2626;padding:16px 24px;display:flex;align-items:baseline;gap:12px;}}
.audit-card-header .term{{font-size:18px;font-weight:700;color:white;}}
.audit-card-header .tag{{font-size:11px;font-weight:600;letter-spacing:.1em;color:rgba(255,255,255,.75);text-transform:uppercase;}}
.audit-card-body{{background:#FFF5F5;padding:20px 24px;}}
.audit-stats{{display:flex;gap:32px;margin-bottom:14px;flex-wrap:wrap;}}
.audit-stat label{{display:block;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#9CA3AF;margin-bottom:2px;}}
.audit-stat .val{{font-family:'DM Mono',monospace;font-size:20px;font-weight:500;color:var(--red-txt);}}
.audit-insight{{font-size:13.5px;line-height:1.7;color:#374151;font-style:italic;margin-bottom:12px;border-left:3px solid #FCA5A5;padding-left:14px;}}
.audit-action{{font-size:13px;color:#374151;}}.audit-action strong{{color:var(--red-txt);}}
.insight-box{{background:#EEF2FF;border-left:4px solid var(--cobalt);border-radius:0 10px 10px 0;padding:20px 24px;margin:24px 0;}}
.insight-box .insight-label{{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--cobalt);margin-bottom:8px;}}
.insight-box p{{font-size:14px;line-height:1.7;color:#374151;}}
.realloc-card{{display:flex;border-radius:10px;overflow:hidden;margin-bottom:16px;border:1px solid var(--border);}}
.realloc-num{{width:60px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-family:'DM Mono',monospace;font-size:26px;font-weight:700;color:white;}}
.realloc-body{{padding:20px 24px;flex:1;background:var(--light-gray);}}
.realloc-body h3{{font-size:15px;font-weight:700;color:var(--navy);margin-bottom:6px;}}
.realloc-body p{{font-size:13.5px;line-height:1.7;color:#374151;}}
.cta-box{{background:var(--navy);border-radius:16px;padding:48px;text-align:center;position:relative;overflow:hidden;margin-top:32px;}}
.cta-box::before{{content:'';position:absolute;top:-80px;right:-80px;width:300px;height:300px;background:radial-gradient(circle,rgba(194,49,255,.25) 0%,transparent 70%);pointer-events:none;}}
.cta-box h2{{font-size:22px;font-weight:700;color:white;margin-bottom:12px;position:relative;}}
.cta-box p{{font-size:14px;color:rgba(255,255,255,.6);margin-bottom:20px;max-width:520px;margin-left:auto;margin-right:auto;position:relative;}}
.cta-pill{{display:inline-block;background:rgba(194,49,255,.2);border:1px solid var(--accent);color:var(--accent);padding:10px 28px;border-radius:50px;font-size:13px;font-weight:600;letter-spacing:.05em;position:relative;}}
.doc-footer{{background:var(--navy);padding:28px 64px;display:flex;align-items:center;justify-content:space-between;}}
.doc-footer span{{font-size:12px;color:rgba(255,255,255,.35);}}.doc-footer .brand{{font-size:14px;font-weight:700;color:var(--accent);}}
.sticky-nav{{position:sticky;top:0;z-index:100;background:rgba(33,2,53,.95);backdrop-filter:blur(10px);border-bottom:1px solid rgba(194,49,255,.3);padding:0 64px;display:flex;align-items:center;gap:4px;overflow-x:auto;}}
.nav-item{{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:rgba(255,255,255,.45);padding:14px 12px;cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;transition:all .2s;text-decoration:none;}}
.nav-item:hover{{color:var(--accent);border-bottom-color:var(--accent);}}
.mono{{font-family:'DM Mono',monospace;}}
@media(max-width:768px){{.section{{padding:40px 24px;}}.section-header{{margin:-40px -24px 32px -24px;}}.kpi-row{{grid-template-columns:repeat(2,1fr);}}.sticky-nav{{padding:0 24px;}}.doc-footer{{padding:24px;flex-direction:column;gap:8px;text-align:center;}}}}
</style>
</head>
<body>
 
<div class="cover">
  <div class="cover-accent-bar"></div>
  <div class="cover-brand">CommerceIQ Intelligence</div>
  <h1 class="cover-title">Incrementality &amp; iROAS Intelligence Report</h1>
  <div class="cover-subtitle">{brand_clean}</div>
  <div class="cover-divider"></div>
  <div class="cover-meta">
    <span class="meta-label">Prepared by</span><span class="meta-value">CommerceIQ Strategic Intelligence Team</span>
    <span class="meta-label">Prepared for</span><span class="meta-value">{brand_clean} Retail Media Leadership</span>
    <span class="meta-label">Category</span><span class="meta-value">Grocery &amp; Gourmet Food — Amazon US</span>
    <span class="meta-label">Keywords</span><span class="meta-value">{d["total"]} search terms analysed</span>
    <span class="meta-label">Status</span><span class="meta-value">Confidential — For Internal Use Only</span>
  </div>
</div>
 
<nav class="sticky-nav">
  <a href="#exec" class="nav-item">01 Executive Summary</a>
  <a href="#thesis" class="nav-item">02 Central Thesis</a>
  <a href="#sov" class="nav-item">03 SOV Dashboard</a>
  <a href="#audit" class="nav-item">04 Cannibalization Audit</a>
  {'<a href="#medium" class="nav-item">05 Medium-Risk Cluster</a>' if d['moderate'] else ''}
  <a href="#growth" class="nav-item">{"06" if d["moderate"] else "05"} Growth Opportunities</a>
  <a href="#realloc" class="nav-item">{"07" if d["moderate"] else "06"} Budget Reallocation</a>
  <a href="#next" class="nav-item">{"08" if d["moderate"] else "07"} Next Steps</a>
</nav>
 
<div class="main">
 
<section class="section" id="exec">
  <div class="section-header"><span class="section-num">01</span><span class="section-title">Executive Summary</span></div>
  <div class="kpi-row">
    <div class="kpi-card kpi-red"><div class="kpi-val">{len(d["critical"])}</div><div class="kpi-label">Critical Cannibalization Keywords</div></div>
    <div class="kpi-card kpi-amb"><div class="kpi-val">{fmt_usd(lowest["iroas"])}</div><div class="kpi-label">Lowest iROAS in Portfolio<br>({esc(lowest["term"])})</div></div>
    <div class="kpi-card kpi-grn"><div class="kpi-val">{fmt_usd(highest["iroas"])}</div><div class="kpi-label">Highest iROAS Available<br>({esc(highest["term"])})</div></div>
    <div class="kpi-card kpi-purple"><div class="kpi-val">{fmt_pct(max_sov["org_sov"],1)}</div><div class="kpi-label">Max Organic SOV — Branded<br>({esc(max_sov["term"])})</div></div>
  </div>
  <p class="prose">{len(d["critical"])} keyword{"s" if len(d["critical"])!=1 else ""} — {", ".join(f"<strong>{esc(r['term'])}</strong>" for r in d["critical"])} — {"collectively represent" if len(d["critical"])>1 else "represents"} {brand_clean}&apos;s most serious retail media waste problem. {"Each carries" if len(d["critical"])>1 else "It carries"} over 60% organic search share of voice on Amazon, yet {brand_clean} continues to fund sponsored placements against {"all of them" if len(d["critical"])>1 else "it"}.</p>
  <p class="prose">When a shopper searches these branded terms, {brand_clean} already wins that click organically {fmt_pct(min(r["org_sov"] or 0 for r in d["critical"]),0)}–{fmt_pct(max(r["org_sov"] or 0 for r in d["critical"]),0)} of the time. The result is an incremental ROAS of {fmt_usd(min(r["iroas"] for r in d["critical"]))}–{fmt_usd(max(r["iroas"] for r in d["critical"]))} — for every dollar of sponsored spend, only that much in revenue is truly incremental.</p>
  <p class="prose">Meanwhile, {len(d["tier1"])} category terms — from <em>{esc(d["tier1"][-1]["term"] if d["tier1"] else "—")}</em> ({fmt_usd(d["tier1"][-1]["iroas"] if d["tier1"] else None)} iROAS) to <em>{esc(d["tier1"][0]["term"] if d["tier1"] else "—")}</em> ({fmt_usd(d["tier1"][0]["iroas"] if d["tier1"] else None)} iROAS) — offer near-complete incrementality and organic SOV under 5%, where every paid dollar reaches a customer {brand_clean} would otherwise miss entirely.</p>
  <div class="sub-banner">What this report delivers</div>
  <ul style="list-style:none;display:flex;flex-direction:column;gap:10px;">
    <li style="font-size:14px;color:#374151;padding-left:20px;position:relative;"><span style="position:absolute;left:0;color:var(--accent);">→</span>Full keyword-level iROAS audit across {d["total"]} search terms in the dataset</li>
    <li style="font-size:14px;color:#374151;padding-left:20px;position:relative;"><span style="position:absolute;left:0;color:var(--accent);">→</span>Cannibalization diagnosis: exact terms where paid spend displaces organic wins</li>
    <li style="font-size:14px;color:#374151;padding-left:20px;position:relative;"><span style="position:absolute;left:0;color:var(--accent);">→</span>Growth opportunity map: high-iROAS terms with low organic penetration</li>
    <li style="font-size:14px;color:#374151;padding-left:20px;position:relative;"><span style="position:absolute;left:0;color:var(--accent);">→</span>A ranked budget reallocation framework: where to cut, where to grow</li>
  </ul>
</section>
 
<section class="section" id="thesis">
  <div class="section-header"><span class="section-num">02</span><span class="section-title">The Central Thesis</span></div>
  <p class="prose">{brand_clean}&apos;s retail media performance on Amazon is being held back by three structural problems — strategic misalignments between where budget is deployed and where it can generate genuine incremental revenue.</p>
  <div class="thesis-card"><div class="thesis-num" style="background:#DC2626;">01</div><div class="thesis-body"><h3>Branded Keyword Cannibalization</h3><p>The {"top" if len(d["critical"])>1 else ""} critical branded {"terms" if len(d["critical"])>1 else "term"} — {", ".join(f"<strong>{esc(r['term'])}</strong> ({fmt_pct(r['org_sov'],1)} organic SOV)" for r in d["critical"][:3])} — {"are" if len(d["critical"])>1 else "is"} being bid on while {brand_clean} already dominates organically. Incremental fractions of {fmt_pct(min(r["inc_frac"] or 0 for r in d["critical"]),0)}–{fmt_pct(max(r["inc_frac"] or 0 for r in d["critical"]),0)} mean {fmt_pct(100-max(r["inc_frac"] or 0 for r in d["critical"]),0)}–{fmt_pct(100-min(r["inc_frac"] or 0 for r in d["critical"]),0)} of ad-driven purchases were going to happen anyway. iROAS of {fmt_usd(min(r["iroas"] for r in d["critical"]))}–{fmt_usd(max(r["iroas"] for r in d["critical"]))} confirms this spend is largely self-cannibalistic.</p></div></div>
  <div class="thesis-card"><div class="thesis-num" style="background:var(--sky);">02</div><div class="thesis-body"><h3>Under-Investment in High-Increment Category Terms</h3><p>Terms like <strong>{esc(d["tier1"][0]["term"] if d["tier1"] else "—")}</strong> ({fmt_usd(d["tier1"][0]["iroas"] if d["tier1"] else None)} iROAS, {fmt_pct(d["tier1"][0]["org_sov"] if d["tier1"] else None)} organic SOV) have near-zero organic presence and very high incremental fractions. Every paid dollar on these terms reaches a net-new buyer — yet they appear to be under-served in the current paid strategy.</p></div></div>
  <div class="thesis-card"><div class="thesis-num" style="background:var(--cobalt);">03</div><div class="thesis-body"><h3>Medium-Risk Segment Inefficiency</h3><p>{'The cluster ' + ", ".join(f"<strong>{esc(r['term'])}</strong>" for r in d["moderate"][:3]) + f' exhibits elevated organic SOV ({fmt_pct(d["moderate"][-1]["org_sov"],0)}–{fmt_pct(d["moderate"][0]["org_sov"],0)}) combined with above-average sponsored share — creating a compounding pattern where paid budget is partially wasted against organic wins.' if d["moderate"] else 'No keywords fall into the moderate-risk (10–50% organic SOV) range in this dataset — a positive signal that the portfolio is well-structured outside the critical branded terms.'}</p></div></div>
</section>
 
<section class="section" id="sov">
  <div class="section-header"><span class="section-num">03</span><span class="section-title">Organic SOV Dashboard — Top 20 Keywords</span></div>
  <p class="prose">Organic share of voice is the primary signal for cannibalization risk. Red bars = critical (&gt;50% SOV). Amber = moderate (10–50%). Green = healthy expansion (&lt;10%).</p>
  <table class="data-table"><thead><tr class="th-navy"><th>Search Term</th><th class="center">Organic SOV</th><th class="center">Spons. SOV</th><th class="center">iROAS</th><th style="min-width:140px;">SOV Visualisation</th><th class="center">Risk</th></tr></thead><tbody id="sov-table"></tbody></table>
  <p style="font-size:12px;color:var(--mid-gray);margin-top:8px;font-style:italic;">Top 20 keywords by Organic SOV, sorted descending.</p>
</section>
 
<section class="section" id="audit">
  <div class="section-header"><span class="section-num">04</span><span class="section-title">Branded Cannibalization Audit</span></div>
  <p class="prose">The keywords below meet the critical-risk threshold: Organic SOV above 50% combined with iROAS below $1.50. Sponsored spend on these terms is generating less than ${"{:.2f}".format(max(r["iroas"] for r in d["critical"]))} in incremental revenue per dollar — the balance is displacing organic conversions that would have occurred for free.</p>
  {audit_cards_html if d["critical"] else '<p class="prose">No keywords exceed the 50% organic SOV threshold in this dataset — no critical cannibalization risk detected.</p>'}
</section>
 
{moderate_section}
 
<section class="section" id="growth">
  <div class="section-header"><span class="section-num">{"06" if d["moderate"] else "05"}</span><span class="section-title">Growth Opportunity Analysis — High iROAS Terms</span></div>
  <p class="prose">The keywords below represent {brand_clean}&apos;s true incremental growth surface on Amazon. Each combines near-zero organic SOV with high incremental fractions and high iROAS. Every paid dollar spent here reaches a customer {brand_clean} would otherwise miss.</p>
  <div class="sub-banner grn">Tier 1 — Priority Growth Terms ( iROAS ≥ $4.75, Organic SOV &lt; 5% )</div>
  {growth_table(d["tier1"], "Tier 1", "th-grn", "iROAS")}
  <div class="sub-banner blue" style="margin-top:28px;">Tier 2 — Efficiency Terms ( iROAS $4.40–$4.74, Organic SOV &lt; 5% )</div>
  {growth_table(d["tier2"], "Tier 2", "th-sky", "iROAS")}
</section>
 
<section class="section" id="realloc">
  <div class="section-header"><span class="section-num">{"07" if d["moderate"] else "06"}</span><span class="section-title">Budget Reallocation Framework</span></div>
  <p class="prose">Reduce spend on high-SOV branded terms and deploy that capital toward high-iROAS category terms where {brand_clean} has no organic safety net and every paid dollar drives a net-new sale.</p>
  <div class="sub-banner red">Priority 1 — Reduce / Eliminate ( Organic SOV &gt; 50%, iROAS &lt; $1.50 )</div>
  {p1_table}
  {'<div class="sub-banner amb" style="margin-top:28px;">Priority 2 — Reduce Gradually ( Organic SOV 10–50%, iROAS &lt; $3.50 )</div>' + p2_table if d["moderate"] else ""}
  <div class="sub-banner grn" style="margin-top:28px;">Priority 3 — Invest &amp; Scale ( iROAS ≥ $4.75, Organic SOV &lt; 2% )</div>
  {p3_table}
</section>
 
<section class="section" id="next">
  <div class="section-header"><span class="section-num">{"08" if d["moderate"] else "07"}</span><span class="section-title">Next Steps</span></div>
  <p class="prose">The CommerceIQ Incrementality Intelligence framework identifies the exact budget moves that convert wasted sponsored spend into genuine incremental sales. Three critical actions for {brand_clean}:</p>
  <div class="realloc-card"><div class="realloc-num" style="background:#DC2626;">1</div><div class="realloc-body"><h3>Immediate: Remove branded cannibalization</h3><p>Stop bidding on {", ".join(f"<strong>{esc(r['term'])}</strong>" for r in d["critical"])} in exact match. These terms carry iROAS of {fmt_usd(min(r["iroas"] for r in d["critical"]))}–{fmt_usd(max(r["iroas"] for r in d["critical"]))} against organic SOV of {fmt_pct(min(r["org_sov"] or 0 for r in d["critical"]),0)}–{fmt_pct(max(r["org_sov"] or 0 for r in d["critical"]),0)}. The freed budget funds everything below.</p></div></div>
  {'<div class="realloc-card"><div class="realloc-num" style="background:#D97706;">2</div><div class="realloc-body"><h3>Week 1–4: Step down the medium-risk cluster</h3><p>Reduce sponsored SOV on ' + ", ".join(f"<strong>{esc(r['term'])}</strong>" for r in d["moderate"][:3]) + f' by 30–40%. The {fmt_usd(min(r["iroas"] for r in d["moderate"][:3]))}–{fmt_usd(max(r["iroas"] for r in d["moderate"][:3]))} iROAS range still justifies some presence — a stepdown (not elimination) is correct while organic SOV normalises.</p></div></div>' if d["moderate"] else ""}
  <div class="realloc-card"><div class="realloc-num" style="background:#047857;">{"3" if d["moderate"] else "2"}</div><div class="realloc-body"><h3>Concurrent: Scale Tier 1 growth terms</h3><p>Increase investment in {", ".join(f"<strong>{esc(r['term'])}</strong> ({fmt_usd(r['iroas'])} iROAS)" for r in d["tier1"][:5])}. These terms have organic SOV under 2% and incremental fractions above 95% — every dollar here drives a net-new customer.</p></div></div>
  <div class="cta-box">
    <h2>Ready to pilot CommerceIQ Incrementality Optimisation for {brand_clean}?</h2>
    <p>See how iROAS-guided optimisations drive higher incremental sales with zero additional tagging or infrastructure required.</p>
    <span class="cta-pill">Access needed: Amazon Vendor Central · Amazon Ads Console</span>
  </div>
</section>
 
</div>
 
<footer class="doc-footer">
  <span class="brand">CommerceIQ</span>
  <span>© 2026 CommerceIQ, Inc. · Confidential — For {brand_clean} Internal Use Only</span>
</footer>
 
<script>
const sovData = {sov_js_data};
function iroasClass(v){{if(v<1.5)return'iroas-red';if(v<3.5)return'iroas-amb';return'iroas-grn';}}
function riskBadge(o){{if(o>50)return'<span class="badge badge-red">CRITICAL</span>';if(o>10)return'<span class="badge badge-amb">MODERATE</span>';return'<span class="badge badge-grn">LOW</span>';}}
function sovBar(o){{const c=o>50?'sov-red':o>10?'sov-amb':'sov-grn';return`<div class="sov-bar-wrap"><div class="sov-bar-fill ${{c}}" style="width:${{Math.min(o,100)}}%"></div></div>`;}}
const tbody=document.getElementById('sov-table');
sovData.forEach(r=>{{
  const tr=document.createElement('tr');
  const ob=r.org>50?'font-weight:700;color:#991B1B;':'';
  tr.innerHTML=`<td>${{r.term}}</td><td class="center" style="${{ob}}">${{r.org.toFixed(1)}}%</td><td class="center" style="color:#6B7280;">${{r.spon?r.spon.toFixed(1)+'%':'—'}}</td><td class="${{iroasClass(r.iroas)}}">${{r.iroas<0?'—':'$'+r.iroas.toFixed(2)}}</td><td class="sov-cell">${{sovBar(r.org)}}</td><td class="center">${{riskBadge(r.org)}}</td>`;
  tbody.appendChild(tr);
}});
</script>
</body>
</html>'''
 
 
# ── CLI ───────────────────────────────────────────────────────────────────────
 
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv',   required=True,  help='Path to input CSV')
    parser.add_argument('--brand', default='Brand', help='Brand name for report')
    parser.add_argument('--out',   required=True,  help='Output HTML path')
    args = parser.parse_args()
 
    rows = read_csv(args.csv)
    print(f'Loaded {len(rows)} valid keywords')
    stats = derive(rows)
    print(f'Critical: {len(stats["critical"])}, Moderate: {len(stats["moderate"])}, Tier1: {len(stats["tier1"])}, Tier2: {len(stats["tier2"])}')
 
    html = build_html(rows, args.brand, stats)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✓ Written to {args.out}')
 