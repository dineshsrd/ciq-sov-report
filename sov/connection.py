"""Databricks SQL connection (live mode only).

`databricks-sql-connector` is imported lazily so the rest of the app works
without it installed. You own the credentials (env vars in config.py); this
module just opens a connection and runs parameterized queries.
"""
from __future__ import annotations

import threading

import pandas as pd

from config import SETTINGS

_conn = None
_lock = threading.Lock()


def _connect():
    from databricks import sql  # lazy import

    return sql.connect(
        server_hostname=SETTINGS.db_hostname,
        http_path=SETTINGS.db_http_path,
        access_token=SETTINGS.db_token,
    )


def _get_conn():
    global _conn
    with _lock:
        if _conn is None:
            if not SETTINGS.databricks_ready:
                raise RuntimeError(
                    "Databricks is not configured. Set DATABRICKS_SERVER_HOSTNAME, "
                    "DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN in your .env."
                )
            _conn = _connect()
        return _conn


def run_query(sql_text: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a query and return a DataFrame. Reconnects once on failure."""
    global _conn
    for attempt in (1, 2):
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute(sql_text, parameters=params or {})
                desc = cur.description or []
                cols = [c[0] for c in desc]
                rows = cur.fetchall()
            df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
            # Databricks stores columns UPPERCASE; normalize so the rest of
            # the pipeline (which uses lowercase) works regardless of source.
            df.columns = [str(c).lower() for c in df.columns]
            return df
        except Exception:
            with _lock:  # drop the dead connection and retry once
                _conn = None
            if attempt == 2:
                raise
    return pd.DataFrame()


def test_connection() -> tuple[bool, str]:
    try:
        df = run_query("SELECT 1 AS ok")
        if not df.empty:
            return True, "Connected to Databricks."
        return False, "Connected, but test query returned no rows."
    except Exception as e:  # pragma: no cover - depends on live env
        return False, f"{type(e).__name__}: {e}"
