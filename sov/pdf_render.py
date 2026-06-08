"""Standalone HTML->PDF renderer (run as a subprocess by report.html_to_pdf).

Usage:  python -m sov.pdf_render <input.html> <output.pdf>

Kept separate so Playwright's sync API never runs inside Streamlit's event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path


def render(html_path: str, pdf_path: str) -> None:
    from playwright.sync_api import sync_playwright

    uri = Path(html_path).resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 1400})
        page.goto(uri, wait_until="networkidle")
        # Give Plotly time to draw the SVGs before printing.
        try:
            page.wait_for_selector(".plotly-graph-div .main-svg", timeout=15000)
        except Exception:
            page.wait_for_timeout(2500)
        page.wait_for_timeout(800)
        page.pdf(path=pdf_path, format="A4", print_background=True,
                 margin={"top": "12mm", "bottom": "12mm",
                         "left": "10mm", "right": "10mm"})
        browser.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m sov.pdf_render <input.html> <output.pdf>",
              file=sys.stderr)
        sys.exit(2)
    render(sys.argv[1], sys.argv[2])
