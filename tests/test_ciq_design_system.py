"""Tests for CIQ design system compliance across reports and branding.

Validates that all report HTML outputs and branding constants adhere to
the CommerceIQ design system defined in skill.md:
  - Fonts: DM Sans + DM Mono
  - CIQ brand palette (#210235, #C231FF, #1F22B2, #5AAFFE, #0A0A0A, #FFFFFF)
  - Status colors: red (#DC2626), amber (#D97706), green (#047857), blue (#1F22B2)
  - Section headers: navy bg + accent pill for section number
  - Tables: border-collapse, alternating row colors
"""
from __future__ import annotations

import re

import pytest

import sov.branding as B
from sov.report import _THEME_CSS, _STYLE


# ── Branding constants ─────────────────────────────────────────────────────

class TestBrandingConstants:
    def test_deep_purple(self):
        assert B.DEEP_PURPLE == "#210235"

    def test_electric(self):
        assert B.ELECTRIC == "#C231FF"

    def test_cobalt(self):
        assert B.COBALT == "#1F22B2"

    def test_sky(self):
        assert B.SKY == "#5AAFFE"

    def test_white(self):
        assert B.WHITE == "#FFFFFF"

    def test_font_family_dm_sans(self):
        assert "DM Sans" in B.FONT_FAMILY

    def test_mono_family_dm_mono(self):
        assert "DM Mono" in B.MONO_FAMILY

    def test_font_family_no_old_fonts(self):
        assert "Inter" not in B.FONT_FAMILY
        assert "Helvetica" not in B.FONT_FAMILY
        assert "Hanken" not in B.FONT_FAMILY

    def test_mono_family_no_old_fonts(self):
        assert "IBM Plex" not in B.MONO_FAMILY

    def test_plotly_template_uses_dm_sans(self):
        tmpl = B.plotly_template()
        assert "DM Sans" in tmpl["layout"]["font"]["family"]


# ── CSS variables in _THEME_CSS ────────────────────────────────────────────

class TestThemeCSSVariables:
    def test_sans_variable(self):
        assert "'DM Sans'" in _THEME_CSS

    def test_mono_variable(self):
        assert "'DM Mono'" in _THEME_CSS

    def test_no_old_sans(self):
        assert "Hanken Grotesk" not in _THEME_CSS

    def test_no_old_mono(self):
        assert "IBM Plex Mono" not in _THEME_CSS

    def test_ink_color(self):
        assert "--ink:#0A0A0A" in _THEME_CSS

    def test_purple_variable(self):
        assert "--purple:#210235" in _THEME_CSS

    def test_electric_variable(self):
        assert "--electric:#C231FF" in _THEME_CSS

    def test_sky_variable(self):
        assert "--sky:#5AAFFE" in _THEME_CSS

    def test_cobalt_variable(self):
        assert "--cobalt:#1F22B2" in _THEME_CSS

    def test_status_red_bg(self):
        assert "--status-red-bg:#DC2626" in _THEME_CSS

    def test_status_red_fg(self):
        assert "--status-red-fg:#991B1B" in _THEME_CSS

    def test_status_amber_bg(self):
        assert "--status-amber-bg:#D97706" in _THEME_CSS

    def test_status_amber_fg(self):
        assert "--status-amber-fg:#92400E" in _THEME_CSS

    def test_status_green_bg(self):
        assert "--status-green-bg:#047857" in _THEME_CSS

    def test_status_green_fg(self):
        assert "--status-green-fg:#065F46" in _THEME_CSS

    def test_status_blue_bg(self):
        assert "--status-blue-bg:#1F22B2" in _THEME_CSS

    def test_status_blue_fg(self):
        assert "--status-blue-fg:#1E40AF" in _THEME_CSS


# ── Section header styling ─────────────────────────────────────────────────

class TestSectionHeaderCSS:
    def test_section_header_exists(self):
        assert ".section-header{" in _THEME_CSS

    def test_section_header_purple_bg(self):
        match = re.search(r"\.section-header\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--purple)" in match.group()

    def test_section_num_accent(self):
        assert ".section-num{" in _THEME_CSS
        match = re.search(r"\.section-num\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--electric)" in match.group()

    def test_section_title_exists(self):
        assert ".section-title{" in _THEME_CSS

    def test_legacy_secnum_still_present(self):
        assert ".secnum{" in _THEME_CSS

    def test_cover_purple_background(self):
        match = re.search(r"\.cover\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--purple)" in match.group()

    def test_topbar_dark(self):
        assert ".topbar{background:#120318" in _THEME_CSS


# ── Table / leaderboard alternating rows ───────────────────────────────────

class TestTableStyling:
    def test_leaderboard_alternating_rows(self):
        assert ".lbrow:nth-child(even){background:#FAFAFD}" in _THEME_CSS

    def test_legacy_table_border_collapse(self):
        assert "border-collapse: collapse" in _STYLE

    def test_legacy_table_alternating(self):
        assert "tr:nth-child(even)" in _STYLE


# ── Tier card CIQ status colors ───────────────────────────────────────────

class TestTierCardColors:
    def test_tier_a_green(self):
        assert "var(--status-green-bg)" in _THEME_CSS

    def test_tier_b_amber(self):
        assert "var(--status-amber-bg)" in _THEME_CSS

    def test_tier_c_red(self):
        assert "var(--status-red-bg)" in _THEME_CSS

    def test_tier_a_label_green(self):
        assert "var(--status-green-fg)" in _THEME_CSS

    def test_tier_b_label_amber(self):
        assert "var(--status-amber-fg)" in _THEME_CSS

    def test_tier_c_label_red(self):
        assert "var(--status-red-fg)" in _THEME_CSS

    def test_no_material_design_greens(self):
        assert "#4caf50" not in _THEME_CSS
        assert "#e8f5e9" not in _THEME_CSS

    def test_no_material_design_oranges(self):
        assert "#ff9800" not in _THEME_CSS
        assert "#fff8e1" not in _THEME_CSS

    def test_no_material_design_reds(self):
        assert "#ef5350" not in _THEME_CSS
        assert "#fce4ec" not in _THEME_CSS


# ── Reason chip CIQ colors ────────────────────────────────────────────────

class TestReasonChipColors:
    def test_reason_keep_uses_status_green(self):
        assert "var(--status-green-fg)" in _THEME_CSS

    def test_reason_add_uses_status_blue(self):
        assert "var(--status-blue-fg)" in _THEME_CSS

    def test_reason_remove_uses_status_red(self):
        assert "var(--status-red-fg)" in _THEME_CSS

    def test_no_material_reason_colors(self):
        assert "#2e7d32" not in _THEME_CSS
        assert "#1565c0" not in _THEME_CSS
        assert "#c62828" not in _THEME_CSS


# ── CTA section ───────────────────────────────────────────────────────────

class TestCTAStyling:
    def test_cta_dark_navy_background(self):
        match = re.search(r"\.cta\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--purple)" in match.group()

    def test_cta_radial_glow(self):
        assert re.search(r"\.cta::before.*radial-gradient", _THEME_CSS)


# ── Legacy style block ────────────────────────────────────────────────────

class TestLegacyStyleBlock:
    def test_uses_dm_sans(self):
        assert "DM Sans" in _STYLE

    def test_no_old_inter_font(self):
        assert "Inter" not in _STYLE

    def test_ink_color(self):
        assert "#0A0A0A" in _STYLE


# ── Google Fonts links in generated HTML ───────────────────────────────────

class TestStickyNavCSS:
    def test_sticky_nav_exists(self):
        assert ".sticky-nav{" in _THEME_CSS

    def test_nav_item_exists(self):
        assert ".nav-item{" in _THEME_CSS

    def test_nav_item_hover_electric(self):
        assert ".nav-item:hover{" in _THEME_CSS
        assert "var(--electric)" in _THEME_CSS


class TestExecKpiCSS:
    def test_exec_kpi_row_exists(self):
        assert ".exec-kpi-row{" in _THEME_CSS

    def test_exec_kpi_exists(self):
        assert ".exec-kpi{" in _THEME_CSS

    def test_exec_kpi_val_exists(self):
        assert ".exec-kpi-val{" in _THEME_CSS

    def test_exec_kpi_lbl_exists(self):
        assert ".exec-kpi-lbl{" in _THEME_CSS

    def test_prose_exists(self):
        assert ".prose{" in _THEME_CSS

    def test_deliverables_exists(self):
        assert ".deliverables" in _THEME_CSS

    def test_smooth_scrolling(self):
        assert "scroll-behavior:smooth" in _THEME_CSS


class TestCoverPage:
    def test_cover_css_exists(self):
        assert ".cover{" in _THEME_CSS
        assert ".cover-accent-bar{" in _THEME_CSS
        assert ".cover-brand{" in _THEME_CSS
        assert ".cover-title{" in _THEME_CSS
        assert ".cover-subtitle{" in _THEME_CSS
        assert ".cover-divider{" in _THEME_CSS
        assert ".cover-meta{" in _THEME_CSS
        assert ".meta-label{" in _THEME_CSS
        assert ".meta-value{" in _THEME_CSS

    def test_cover_accent_bar_uses_electric(self):
        match = re.search(r"\.cover-accent-bar\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--electric)" in match.group()

    def test_cover_brand_uses_electric(self):
        match = re.search(r"\.cover-brand\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--electric)" in match.group()

    def test_meta_label_uses_sky(self):
        match = re.search(r"\.meta-label\{[^}]+\}", _THEME_CSS)
        assert match
        assert "var(--sky)" in match.group()

    def test_cover_radial_glows(self):
        assert "radial-gradient" in _THEME_CSS

    def test_themed_report_has_cover(self):
        from sov.report import build_themed_report
        html = build_themed_report(
            scope={"name": "T", "brand_label": "TestBrand",
                   "category_value": "TestCat", "level": "category",
                   "cid": "t", "extras": {}}, ins={}, d={})
        assert 'class="cover"' in html
        assert "CommerceIQ Intelligence" in html
        assert "cover-accent-bar" in html
        assert "meta-label" in html
        assert "Confidential" in html

    def test_themed_report_has_sticky_nav(self):
        from sov.report import build_themed_report
        html = build_themed_report(
            scope={"name": "T", "brand_label": "TestBrand",
                   "category_value": "TestCat", "level": "category",
                   "cid": "t", "extras": {}}, ins={}, d={})
        assert 'class="sticky-nav"' in html
        assert 'class="nav-item"' in html
        assert 'href="#exec"' in html
        assert 'href="#win"' in html

    def test_themed_report_has_exec_summary(self):
        from sov.report import build_themed_report
        html = build_themed_report(
            scope={"name": "T", "brand_label": "TestBrand",
                   "category_value": "TestCat", "level": "category",
                   "cid": "t", "extras": {}},
            ins={"verdict": "TestBrand leads TestCat."},
            d={"hero": {"your_sov": 25.5, "rank": 2,
                        "organic": 15.0, "paid": 10.5}})
        assert 'id="exec"' in html
        assert "Executive Summary" in html
        assert "exec-kpi-row" in html
        assert "25.5%" in html
        assert "#2" in html
        assert "TestBrand leads TestCat." in html

    def test_themed_report_uses_section_header(self):
        from sov.report import build_themed_report
        html = build_themed_report(
            scope={"name": "T", "brand_label": "TestBrand",
                   "category_value": "TestCat", "level": "category",
                   "cid": "t", "extras": {}}, ins={}, d={})
        assert "section-header" in html
        assert "section-num" in html
        assert "section-title" in html


class TestGoogleFontsLinks:
    _SCOPE = {"name": "Test", "brand_label": "TestBrand",
              "category_value": "TestCat", "level": "category",
              "cid": "test", "extras": {}}

    def test_themed_report_loads_dm_fonts(self):
        from sov.report import build_themed_report

        html = build_themed_report(
            scope=self._SCOPE, ins={}, d={})
        assert "DM+Sans" in html
        assert "DM+Mono" in html
        assert "Hanken+Grotesk" not in html
        assert "IBM+Plex+Mono" not in html

    def test_category_report_loads_dm_fonts(self):
        from sov.report import build_category_report

        html = build_category_report(
            scope=self._SCOPE, ins={}, d={})
        assert "DM+Sans" in html
        assert "DM+Mono" in html
        assert "Hanken+Grotesk" not in html

    def test_category_report_has_sticky_nav(self):
        from sov.report import build_category_report

        html = build_category_report(
            scope=self._SCOPE, ins={}, d={
                "leaderboard": [{"brand": "A", "combined_sov": 10,
                                 "organic_pts": 5, "paid_pts": 5,
                                 "is_focus": False}],
                "keywords": [{"kw": "term", "crawls": 100}],
            })
        assert 'class="sticky-nav"' in html
        assert 'class="nav-item"' in html
        assert 'href="#exec"' in html
        assert 'href="#lb"' in html
        assert 'href="#kws"' in html
        assert 'href="#win"' in html

    def test_category_report_has_exec_summary(self):
        from sov.report import build_category_report

        html = build_category_report(
            scope=self._SCOPE,
            ins={"verdict": "BrandX leads Cat with 30.0% SOV."},
            d={"hero": {"top_brand": "BrandX", "top_sov": 30.0,
                        "brands": 8, "keywords": 50}})
        assert 'id="exec"' in html
        assert "Executive Summary" in html
        assert "exec-kpi-row" in html
        assert "BrandX" in html
        assert "30.0%" in html
        assert "BrandX leads Cat" in html

    def test_category_report_has_section_ids(self):
        from sov.report import build_category_report

        html = build_category_report(
            scope=self._SCOPE, ins={}, d={
                "leaderboard": [{"brand": "A", "combined_sov": 10,
                                 "organic_pts": 5, "paid_pts": 5,
                                 "is_focus": False}],
                "subcats": [{"sub": "S1", "leader": "A",
                             "leader_sov": 10.0}],
                "keywords": [{"kw": "term", "crawls": 100}],
            })
        assert 'id="lb"' in html
        assert 'id="subcats"' in html
        assert 'id="kws"' in html
        assert 'id="win"' in html

    def test_category_report_uses_section_header(self):
        from sov.report import build_category_report

        html = build_category_report(
            scope=self._SCOPE, ins={}, d={})
        assert "section-header" in html
        assert "section-num" in html
        assert "section-title" in html

    def test_incrementality_report_loads_dm_fonts(self):
        from sov.report import build_incrementality_report

        html = build_incrementality_report(
            scope=self._SCOPE, ins={}, d={})
        assert "DM+Sans" in html
        assert "DM+Mono" in html
        assert "Hanken+Grotesk" not in html


class TestIncrementalityHidden:
    """Verify that the Incrementality option is removed from the UI."""

    def test_app_radio_excludes_incrementality(self):
        """The st.radio call in app.py should not offer Incrementality."""
        import pathlib
        app_src = pathlib.Path("app.py").read_text()
        assert "📈 Incrementality" not in app_src, \
            "Incrementality should be hidden from the st.radio options"

    def test_is_incr_mode_always_false(self):
        """is_incr_mode must be hardcoded to False."""
        import pathlib
        app_src = pathlib.Path("app.py").read_text()
        assert "is_incr_mode = False" in app_src
