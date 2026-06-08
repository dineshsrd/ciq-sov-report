# Category & Keyword Positioning (CommerceIQ)

A single local service that turns the `ams_cubes` SOV cubes into a shareable,
CommerceIQ-branded **positioning report** for any brand on Amazon: where the
brand stands across its **categories (L1)** and **keywords**, who's winning,
the **paid-vs-organic incrementality**, and the **whitespace** — exportable to
**interactive HTML + PDF** with a "talk to us" call-to-action.

Built for non-technical users: pick a brand, pick a category, click **Generate**.
`client_id` is never shown — brands are labeled by their own product brands.

---

## Quick start

```bash
./run.sh
```

Creates a virtualenv, installs everything, and launches the app (opens at
http://localhost:8501). Runs in **sample mode** by default if `.env` says so.

For live data, `.env` is already configured for Databricks
(`client_catalog.ams_cubes.*`). Key settings:

```ini
SOV_DATA_MODE=live
DATABRICKS_SERVER_HOSTNAME=dbc-...cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/...
DATABRICKS_TOKEN=dapi...
DATABRICKS_CATALOG=client_catalog
DATABRICKS_SCHEMA=ams_cubes
SOV_DEFAULT_CLIENT_ID=1064     # optional: pre-select a brand on load
OPENAI_API_KEY=sk-...          # optional; falls back to a rule-based narrative
OPENAI_MODEL=gpt-4.1
```

---

## Two views

1. **Category overview** (pick *🌐 All categories*) — the brand's SOV across all
   its L1 categories: strongest, weakest, biggest opportunities.
2. **Category deep-dive** (pick a specific category) — tabs:

| Tab | What it answers |
|---|---|
| **Brand leaderboard** | Who leads the category by SOV%, where you rank |
| **Keyword positioning** | Your SOV/rank per keyword vs the leader |
| **Incrementality** | Organic vs paid-driven SOV (paid lift = Combined − Organic) |
| **SOV trend** | Are you gaining or losing share over time |
| **Movers** | Biggest SOV gains/losses (first vs last week) |
| **Whitespace** | High-volume keywords where your SOV is low |
| **Ad-type mix** | SP vs Organic vs SB vs Combined |
| **Position depth** | Page-1 → Top-10 → … → Top-2 (premium real estate) |
| **Branded vs generic** | Your SOV split by keyword type |
| **Product shelf** | The ASINs (titles + images) winning a keyword |

Lens is configurable (SP / Organic / Combined) as is the position cutoff.

---

## How SOV is computed (the important bits)

`SOV% = client_count / total_count × 100`, rolled up to category/keyword level.

- **`total_*` is an all-brands total repeated on every brand row.** The
  numerator sums freely; the denominator is **de-duplicated per
  `(search_term, feed_date)`** before summing — else SOV inflates past 100%.
- **Metadata is de-duplicated in the join.** A keyword can be tagged under
  multiple category paths; joining raw fans out the performance rows and breaks
  SOV. The queries collapse metadata to one row per keyword (per category).
- **Per-account.** The catalog is multi-tenant; SOV is only valid within one
  `client_id` (the `client`/`comp` flag and totals are account-specific). The
  app scopes to one account and labels it by its brand names.
- **Scale.** Aggregation is pushed into SQL (returns thousands of rows, not
  hundreds of thousands), and the keyword×brand pull is capped to the top
  keywords by crawl volume to avoid CloudFetch throttling on huge categories.

Validated against live data: SOV sums to **100.0%** for SP, Organic, SB and
Combined.

---

## Architecture (single service)

```
app.py                 Streamlit UI (the whole service)
config.py              env + settings
sov/
  metrics.py           metric/column definitions + category levels
  branding.py          brand colors + Plotly theme
  queries.py           parameterized, SQL-side-aggregated Databricks queries
  connection.py        Databricks SQL connector (lazy import, lowercases cols)
  data.py              data access — chooses sample vs live, casts DECIMAL→float
  sample_data.py       synthetic, internally-consistent data
  transforms.py        SOV math (leaderboard, positioning, incrementality, …)
  charts.py            brand-themed Plotly figures
  narrative.py         OpenAI insights (falls back to a rule-based template)
  report.py            HTML report + PDF export + CommerceIQ CTA
  pdf_render.py        headless-Chromium HTML→PDF (subprocess)
smoke_test.py          end-to-end pipeline check (honors SOV_DATA_MODE)
```

---

## Notes

- **No OpenAI key (or auth/rate error)?** Reports still generate with a
  rule-based insights summary — the LLM path degrades gracefully.
- **PDF** uses Playwright's headless Chromium (`python -m playwright install
  chromium`, done by `run.sh`). If unavailable, the interactive HTML export
  always works and is self-contained (safe to email).
- Tables: `client_catalog.ams_cubes.sov_search_term_level_performance_post_output`,
  `…_metadata_post_output`, `…_sku_mapping_data_post_output`.
