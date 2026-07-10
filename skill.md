---
name: incrementality-report-html
description: >
  Generates a polished, branded CommerceIQ Incrementality & iROAS Intelligence Report as an
  HTML file from an uploaded CSV incrementality report. Use this skill whenever the user uploads
  a CSV file that contains columns like SEARCH TERM, iROAS, Organic SOV, Sponsored SOV,
  INCREMENTAL FRACTION, or ROAS — even if they don't say "incrementality report" explicitly.
  Triggers on: "make a report from this CSV", "generate the HTML", "create incrementality analysis",
  "same as last time but for [brand]", or any upload of an incrementality/iROAS CSV.
  Always produces a standalone .html file with the full 8-section CIQ report layout.
---
 
# Incrementality & iROAS Intelligence Report — HTML Generator
 
## What this skill produces
 
A single, self-contained `.html` file containing a full **CommerceIQ Incrementality & iROAS Intelligence Report** with:
 
- Dark navy cover page with CIQ branding
- Sticky navigation bar (8 sections)
- KPI summary cards
- Central thesis (3 structural problems, auto-derived from data)
- Organic SOV dashboard table with color-coded proportional bar visualisations
- Branded cannibalization audit cards (deep-dives on keywords with Organic SOV >50% **and** Sponsored SOV >0)
- Breakfast bar / medium-risk cluster section (if applicable)
- Growth opportunity tables: Tier 1 (iROAS ≥ $4.75) and Tier 2 (iROAS $4.40–$4.74)
- Budget reallocation framework (Priority 1 / 2 / 3)
- Next steps + CTA box
## CIQ Brand Colours (always use these)
 
```
--navy:   #210235   headlines / cover / section headers
--accent: #C231FF   electric accent / CTAs / section nums
--cobalt: #1F22B2   cobalt / supporting blue
--sky:    #5AAFFE   sky blue / secondary accent
--black:  #0A0A0A   body text
--white:  #FFFFFF   page background
```
 
Status colours (data-driven, do not change):
- Red:   #DC2626 bg / #991B1B text  → iROAS < $1.50, SOV > 50%
- Amber: #D97706 bg / #92400E text  → iROAS $1.50–$3.50, SOV 10–50%
- Green: #047857 bg / #065F46 text  → iROAS > $3.50, SOV < 10%
- Blue:  #1F22B2 bg / #1E40AF text  → iROAS $4.40–$4.74 (Tier 2 growth)
## Step-by-step workflow
 
### Step 1 — Read the CSV
 
Read the uploaded CSV from `/mnt/user-data/uploads/`. Expected columns:
```
SEARCH TERM, CATEGORY, SEARCH RANK, INCREMENTAL FRACTION, ROAS, iROAS, Organic SOV, Sponsored SOV
```
 
Parse with Python:
```python
import csv, re
 
def pct(s):
    if not s or s.strip() == '': return None
    return float(s.strip().replace('%','').replace(',',''))
 
def usd(s):
    if not s or s.strip() == '': return None
    return float(s.strip().replace('$','').replace(',',''))
 
rows = []
with open(filepath, newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for r in reader:
        # Normalise column names (strip whitespace/newlines)
        norm = {k.strip().split('\n')[0].strip(): v for k,v in r.items()}
        rows.append({
            'term':   norm.get('SEARCH TERM','').strip(),
            'rank':   norm.get('SEARCH RANK','').strip(),
            'inc_frac': pct(norm.get('INCREMENTAL FRACTION','')),
            'roas':   usd(norm.get('ROAS','')),
            'iroas':  usd(norm.get('iROAS','')),
            'org_sov': pct(norm.get('Organic SOV','')),
            'spon_sov': pct(norm.get('Sponsored SOV','')),
        })
rows = [r for r in rows if r['term'] and r['iroas'] is not None]
```
 
### Step 2 — Derive key statistics
 
```python
# Sort by organic SOV descending
by_sov = sorted(rows, key=lambda r: r['org_sov'] or 0, reverse=True)
 
# Critical cannibalization: Organic SOV > 50% AND Sponsored SOV is non-zero
# (sponsored spend must be present — no point flagging organic dominance if brand isn't running ads)
critical = [r for r in rows if (r['org_sov'] or 0) > 50 and (r['spon_sov'] or 0) > 0]
 
# Moderate risk: 10–50% SOV
moderate = [r for r in rows if 10 < (r['org_sov'] or 0) <= 50]
 
# Tier 1 growth: iROAS >= 4.75, Organic SOV < 5%
tier1 = sorted(
    [r for r in rows if r['iroas'] >= 4.75 and (r['org_sov'] or 0) < 5],
    key=lambda r: -r['iroas']
)
 
# Tier 2 growth: iROAS 4.40–4.74, Organic SOV < 5%
tier2 = sorted(
    [r for r in rows if 4.40 <= r['iroas'] < 4.75 and (r['org_sov'] or 0) < 5],
    key=lambda r: -r['iroas']
)
 
# KPI values
lowest_iroas  = min(rows, key=lambda r: r['iroas'])
highest_iroas = max(rows, key=lambda r: r['iroas'])
max_sov_row   = max(rows, key=lambda r: r['org_sov'] or 0)
total_keywords = len(rows)
```
 
### Step 3 — Generate the HTML
 
Use the **exact HTML structure** described in `scripts/html_template.py`.
 
Run:
```bash
python3 /home/claude/incrementality-report-html/scripts/html_template.py \
  --csv "/mnt/user-data/uploads/FILENAME.csv" \
  --brand "Brand Name" \
  --out "/mnt/user-data/outputs/Brand_Incrementality_Report.html"
```
 
If the script doesn't exist yet, generate the HTML inline following the structure below.
 
### Step 4 — HTML structure (sections in order)
 
1. **Cover** — dark navy (#210235), brand name, CIQ logo text, radial accent glows
2. **Sticky nav** — 8 anchor links, accent underline on hover
3. **01 Executive Summary** — 4 KPI cards + 4 prose paragraphs + bullet list
4. **02 Central Thesis** — 3 numbered cards: cannibalization / under-investment / medium-risk cluster
5. **03 Organic SOV Dashboard** — top 20 by Organic SOV, JS-rendered table with SOV bar fills
6. **04 Cannibalization Audit** — one audit-card per critical keyword (Organic SOV > 50% AND Sponsored SOV > 0)
7. **05 Medium-Risk Cluster** — table for moderate SOV terms (if any)
8. **06 Growth Opportunities** — Tier 1 table (green headers) + Tier 2 table (sky headers)
9. **07 Budget Reallocation** — Priority 1 (red), Priority 2 (amber), Priority 3 (green)
10. **08 Next Steps** — 3 realloc action cards + CTA box
### Step 5 — Output and present
 
```python
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_string)
```
 
Then call `present_files([output_path])`.
 
---
 
## Key design rules (never break these)
 
- **Font**: `DM Sans` + `DM Mono` from Google Fonts (already in template)
- **Section headers**: always `background: #210235; color: white` with section number in accent pill
- **iROAS column**: always color-coded — red < $1.50, amber $1.50–$3.50, green > $3.50, blue for Tier 2
- **SOV bars**: CSS div fills — red > 50% (only when Sponsored SOV > 0), amber 10–50%, green < 10%
- **Audit cards**: red top border (4px), light red background, stats row, italic insight, bold action
- **All tables**: `border-collapse: collapse`, alternating white / very-light-gray rows
- **CTA box**: dark navy background with radial purple glow, accent-bordered pill
## Brand name derivation
 
Infer brand name from the filename (e.g. `Ferrero-Kinder_...csv` → "Ferrero · Kinder") or ask the user if unclear.
 
## Error handling
 
- If `iROAS` column is missing but `ROAS` and `INCREMENTAL FRACTION` are present, compute: `iROAS = ROAS × (INCREMENTAL_FRACTION / 100)`
- If `Organic SOV` column is missing entirely, skip SOV-dependent sections and note this in the report
- Skip rows where `SEARCH TERM` is empty or `iROAS` cannot be parsed