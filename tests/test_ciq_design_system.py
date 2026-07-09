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
    def test_secnum_accent_pill(self):
        assert "background:var(--electric)" in _THEME_CSS
        assert ".secnum{" in _THEME_CSS

    def test_secnum_white_text(self):
        match = re.search(r"\.secnum\{[^}]+\}", _THEME_CSS)
        assert match
        secnum_css = match.group()
        assert "color:#fff" in secnum_css

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

    def test_incrementality_report_loads_dm_fonts(self):
        from sov.report import build_incrementality_report

        html = build_incrementality_report(
            scope=self._SCOPE, ins={}, d={})
        assert "DM+Sans" in html
        assert "DM+Mono" in html
        assert "Hanken+Grotesk" not in html
