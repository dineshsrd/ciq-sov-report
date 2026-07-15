"""Central configuration. Reads from environment (.env supported).

Priority order for every setting:
  1. OS environment variable (set by the process / docker / run.sh)
  2. .env file (via python-dotenv, local dev only)
  3. st.secrets (Streamlit Community Cloud — secrets pasted in the Cloud UI)
  4. Hard-coded default
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # load .env if python-dotenv is installed
    from dotenv import load_dotenv

    # override=True so edits to .env always win over any stale value already
    # present in the OS environment.
    load_dotenv(override=True)
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _clean(v: str | None) -> str:
    return (v or "").strip()


def _env(key: str, default: str = "") -> str:
    """Read an env var; fall back to st.secrets on Streamlit Community Cloud."""
    val = _clean(os.getenv(key))
    if not val:
        try:
            import streamlit as st  # noqa: PLC0415 — lazy import intentional
            secret = st.secrets.get(key)
            if secret is not None:
                val = _clean(str(secret))
        except Exception:
            pass
    return val or default


@dataclass(frozen=True)
class Settings:
    data_mode: str = _env("SOV_DATA_MODE", "sample")

    # Databricks
    db_hostname: str = _env("DATABRICKS_SERVER_HOSTNAME")
    db_http_path: str = _env("DATABRICKS_HTTP_PATH")
    db_token: str = _env("DATABRICKS_TOKEN")
    db_catalog: str = _env("DATABRICKS_CATALOG")
    db_schema: str = _env("DATABRICKS_SCHEMA", "ams_cubes")

    default_client_id: str = _env("SOV_DEFAULT_CLIENT_ID")

    # OpenAI
    openai_api_key: str = _env("OPENAI_API_KEY")
    openai_model: str = _env("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def is_live(self) -> bool:
        return self.data_mode.lower() == "live"

    @property
    def databricks_ready(self) -> bool:
        return bool(self.db_hostname and self.db_http_path and self.db_token)

    @property
    def openai_ready(self) -> bool:
        return bool(self.openai_api_key)

    def table(self, name: str) -> str:
        """Fully-qualified table name for the configured catalog/schema."""
        parts = [p for p in (self.db_catalog, self.db_schema, name) if p]
        return ".".join(parts)

    def qualified(self, schema: str, name: str) -> str:
        """Fully-qualified name for an explicit schema (e.g. aramus_ds)."""
        parts = [p for p in (self.db_catalog, schema, name) if p]
        return ".".join(parts)


SETTINGS = Settings()

# Table short names (the *_post_output cubes described in the schema).
TBL_PERFORMANCE = "sov_search_term_level_performance_post_output"
TBL_METADATA = "sov_search_term_metadata_post_output"
TBL_SKU = "sov_search_term_sku_mapping_data_post_output"
# Ad incrementality / efficiency (different schema)
SCHEMA_ARAMUS = "aramus_ds"
TBL_INCR = "search_incrementality_report"
# Search term volume — always in common_catalog.aramus_ds regardless of env
CATALOG_COMMON = "common_catalog"
TBL_SEARCH_VOLUME = "search_term_volume"
