#!/usr/bin/env bash
# One command to set up and launch the app.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing dependencies…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

# One-time browser download for PDF export (safe to re-run).
python -m playwright install chromium >/dev/null 2>&1 || \
  echo "(Playwright chromium not installed — PDF export will be unavailable; HTML still works.)"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from template (running in SAMPLE mode by default)."
fi

echo "Launching… open the URL Streamlit prints below."
exec streamlit run app.py
