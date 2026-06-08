"""Persistent report history. Each generated report's HTML is saved to disk
with a small manifest so users can look back at / re-download past reports."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / ".reports"
_MANIFEST = _DIR / "manifest.json"
_CAP = 200  # keep the most recent N reports


def _load() -> list[dict]:
    try:
        return json.loads(_MANIFEST.read_text())
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    _DIR.mkdir(exist_ok=True)
    _MANIFEST.write_text(json.dumps(entries, indent=1))


def save_report(scope: dict, html: str, source: str = "") -> dict:
    """Persist one report; returns its manifest entry."""
    _DIR.mkdir(exist_ok=True)
    rid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:5]
    try:
        (_DIR / f"{rid}.html").write_text(html, encoding="utf-8")
    except Exception:
        return {}
    entry = {
        "id": rid,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "name": str(scope.get("name", "")).strip(),
        "brand": str(scope.get("brand_label", "")),
        "category": str(scope.get("category_value", "")),
        "level_label": str(scope.get("level_label", "")),
        "metric": str(scope.get("metric_label", "")),
        "date_min": str(scope.get("date_min", "")),
        "date_max": str(scope.get("date_max", "")),
        "source": source,
    }
    entries = _load()
    entries.insert(0, entry)
    # prune beyond cap (and delete their html files)
    for old in entries[_CAP:]:
        try:
            (_DIR / f"{old['id']}.html").unlink(missing_ok=True)
        except Exception:
            pass
    entries = entries[:_CAP]
    _save(entries)
    return entry


def list_reports() -> list[dict]:
    return _load()


def load_html(rid: str) -> str | None:
    f = _DIR / f"{rid}.html"
    try:
        return f.read_text(encoding="utf-8") if f.exists() else None
    except Exception:
        return None
