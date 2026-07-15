"""Tests for the search volume integration:
  - sov/queries.py: search_term_volume_query()
  - sov/data.py: get_search_term_volume()
  - app.py: merge logic + themed dict enrichment
  - sov/report.py: Zero SOV section uses volume when present, crawls as fallback
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pandas as pd
import pytest


# ── Query tests ──────────────────────────────────────────────────────────────

class TestSearchTermVolumeQuery:
    _KWS = ["blender", "juicer"]

    def test_returns_string(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS)
        assert isinstance(q, str)

    def test_references_correct_table(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS)
        assert "common_catalog.aramus_ds.search_term_volume" in q

    def test_has_predicted_volume_column(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS)
        assert "predicted_volume" in q

    def test_divides_by_distinct_months_for_monthly_average(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS).upper()
        assert "COUNT(DISTINCT DATE_TRUNC" in q
        assert "NULLIF" in q

    def test_has_date_params(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS)
        assert ":s" in q
        assert ":e" in q

    def test_has_retailer_id_param(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS)
        assert ":rid" in q

    def test_groups_by_search_term(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(self._KWS).upper()
        assert "GROUP BY" in q
        assert "SEARCH_TERM" in q

    def test_contains_in_clause_with_keywords(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(["blender", "juicer"])
        assert "IN (" in q
        assert "'blender'" in q
        assert "'juicer'" in q

    def test_single_quote_escaped_in_keyword(self):
        from sov.queries import search_term_volume_query
        q = search_term_volume_query(["l'oreal"])
        assert "l''oreal" in q

    def test_raises_on_empty_keywords(self):
        from sov.queries import search_term_volume_query
        with pytest.raises(ValueError, match="empty"):
            search_term_volume_query([])

    def test_v_helper_uses_common_catalog(self):
        from sov.queries import _V
        assert _V().startswith("common_catalog.aramus_ds.")

    def test_v_helper_uses_correct_table(self):
        from sov.queries import _V
        assert _V().endswith("search_term_volume")


# ── Data accessor tests ──────────────────────────────────────────────────────

class TestGetSearchTermVolumeSampleMode:
    """In sample mode (default), always returns an empty DataFrame."""

    def _call(self, keywords=None):
        from sov.data import get_search_term_volume
        kws = keywords if keywords is not None else ["blender", "juicer"]
        return get_search_term_volume(kws,
                                      start=dt.date(2024, 1, 1),
                                      end=dt.date(2024, 1, 31))

    def test_returns_dataframe(self):
        result = self._call()
        assert isinstance(result, pd.DataFrame)

    def test_has_correct_columns(self):
        result = self._call()
        assert list(result.columns) == ["search_term", "search_volume"]

    def test_empty_in_sample_mode(self):
        result = self._call()
        assert result.empty

    def test_empty_keywords_returns_empty(self):
        result = self._call(keywords=[])
        assert result.empty

    def test_empty_keywords_has_correct_columns(self):
        result = self._call(keywords=[])
        assert list(result.columns) == ["search_term", "search_volume"]


class TestGetSearchTermVolumeLiveMode:
    """Live-mode tests using a mocked _run()."""

    def _live_result(self, keywords, mock_df):
        from sov.data import get_search_term_volume
        with patch("sov.data.SETTINGS") as mock_settings, \
             patch("sov.data._run", return_value=mock_df):
            mock_settings.is_live = True
            return get_search_term_volume(keywords,
                                          start=dt.date(2024, 1, 1),
                                          end=dt.date(2024, 1, 31))

    def test_returns_all_db_rows(self):
        """DB already filters via IN-clause; data accessor returns whatever DB returns."""
        raw = pd.DataFrame({
            "search_term": ["blender", "juicer"],
            "search_volume": [50000, 30000],
        })
        result = self._live_result(["blender", "juicer"], raw)
        assert set(result["search_term"].tolist()) == {"blender", "juicer"}

    def test_search_volume_is_integer(self):
        raw = pd.DataFrame({
            "search_term": ["blender"],
            "search_volume": [12345.0],
        })
        result = self._live_result(["blender"], raw)
        assert result["search_volume"].dtype == int or \
               result["search_volume"].dtype.kind == "i"

    def test_returns_correct_columns(self):
        raw = pd.DataFrame({
            "search_term": ["blender"],
            "search_volume": [5000],
        })
        result = self._live_result(["blender"], raw)
        assert list(result.columns) == ["search_term", "search_volume"]

    def test_empty_db_result_returns_empty(self):
        empty_df = pd.DataFrame()
        result = self._live_result(["blender"], empty_df)
        assert result.empty
        assert list(result.columns) == ["search_term", "search_volume"]

    def test_db_returns_only_requested_keywords(self):
        """IN-clause means DB only returns matching rows; accessor passes them through."""
        raw = pd.DataFrame({
            "search_term": ["blender"],
            "search_volume": [8000],
        })
        result = self._live_result(["blender"], raw)
        assert not result.empty
        assert result.iloc[0]["search_term"] == "blender"


# ── Merge logic tests ────────────────────────────────────────────────────────

class TestZeroSovVolumeMerge:
    """Unit tests for the merge+sort logic used in _build_deepdive."""

    def _merge(self, zsv_df: pd.DataFrame,
               vol_df: pd.DataFrame) -> pd.DataFrame:
        """Replicate the merge logic from app._build_deepdive."""
        if not zsv_df.empty and not vol_df.empty:
            zsv_df = zsv_df.merge(vol_df, on="search_term", how="left")
            zsv_df["search_volume"] = zsv_df["search_volume"].fillna(0).astype(int)
            zsv_df = zsv_df.sort_values("search_volume", ascending=False
                                        ).reset_index(drop=True)
        else:
            zsv_df["search_volume"] = 0
        return zsv_df

    def test_sorts_by_search_volume_descending(self):
        zsv = pd.DataFrame({
            "search_term": ["a", "b", "c"],
            "crawls": [100.0, 200.0, 50.0],
            "intensity": [1.0, 2.0, 0.5],
        })
        vol = pd.DataFrame({
            "search_term": ["a", "b", "c"],
            "search_volume": [1000, 5000, 2000],
        })
        result = self._merge(zsv, vol)
        assert result.iloc[0]["search_term"] == "b"
        assert result.iloc[1]["search_term"] == "c"
        assert result.iloc[2]["search_term"] == "a"

    def test_missing_keyword_gets_zero_volume(self):
        zsv = pd.DataFrame({
            "search_term": ["a", "b"],
            "crawls": [100.0, 200.0],
            "intensity": [1.0, 2.0],
        })
        vol = pd.DataFrame({
            "search_term": ["a"],
            "search_volume": [3000],
        })
        result = self._merge(zsv, vol)
        b_row = result[result["search_term"] == "b"]
        assert int(b_row["search_volume"].iloc[0]) == 0

    def test_empty_volume_sets_zero_column(self):
        zsv = pd.DataFrame({
            "search_term": ["a"],
            "crawls": [100.0],
            "intensity": [1.0],
        })
        vol = pd.DataFrame(columns=["search_term", "search_volume"])
        result = self._merge(zsv, vol)
        assert "search_volume" in result.columns
        assert int(result["search_volume"].iloc[0]) == 0

    def test_volume_preserved_in_themed_dict(self):
        zsv = pd.DataFrame({
            "search_term": ["blender", "juicer"],
            "crawls": [100.0, 200.0],
            "intensity": [10.0, 20.0],
            "search_volume": [50000, 30000],
        })
        themed_zero_sov = [
            {"kw": r["search_term"], "crawls": float(r["crawls"]),
             "volume": int(r.get("search_volume", 0))}
            for _, r in zsv.head(10).iterrows()
        ]
        assert themed_zero_sov[0]["volume"] == 50000
        assert themed_zero_sov[1]["volume"] == 30000


# ── Report renderer tests ────────────────────────────────────────────────────

class TestZeroSovReportRendering:
    """Tests for the Zero SOV section in build_themed_report."""

    _BASE_SCOPE = {
        "name": "T", "brand_label": "BrandX",
        "category_value": "TestCat", "level": "category",
        "cid": "t", "extras": {},
    }

    def _render(self, zero_sov_rows: list[dict]) -> str:
        from sov.report import build_themed_report
        return build_themed_report(
            scope=self._BASE_SCOPE, ins={},
            d={"zero_sov": zero_sov_rows})

    def test_uses_volume_when_present(self):
        html = self._render([
            {"kw": "blender", "crawls": 100.0, "volume": 50000},
            {"kw": "juicer", "crawls": 80.0, "volume": 30000},
        ])
        assert "avg. monthly searches" in html
        assert "50,000" in html

    def test_falls_back_to_crawls_when_no_volume(self):
        html = self._render([
            {"kw": "blender", "crawls": 100.0, "volume": 0},
            {"kw": "juicer", "crawls": 80.0, "volume": 0},
        ])
        assert "searches" in html
        assert "avg. monthly" not in html

    def test_falls_back_when_volume_key_missing(self):
        html = self._render([
            {"kw": "blender", "crawls": 100.0},
        ])
        assert "searches" in html

    def test_section_title_unchanged(self):
        html = self._render([
            {"kw": "blender", "crawls": 100.0, "volume": 50000},
        ])
        assert "Top Missed Opportunities" in html
        assert "Zero SOV" in html

    def test_keyword_name_appears(self):
        html = self._render([
            {"kw": "blender", "crawls": 100.0, "volume": 50000},
        ])
        assert "blender" in html
