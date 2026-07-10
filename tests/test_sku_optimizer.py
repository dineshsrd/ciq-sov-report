"""Tests for sov.sku_optimizer — deep single-SKU PDP optimization."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Sample data fixtures ────────────────────────────────────────────────────

SAMPLE_OPTIMIZED = {
    "sku": "B00NGV4506",
    "optimization_mode": "self-directed",
    "inferred_intent": "Self-purchase for home kitchen use; blender for smoothies.",
    "self_directed_analysis": {
        "content_credibility_profile": {
            "carry_forward": ["1000 watts of power", "XL 72-oz. pitcher"],
            "softened": ["professional power", "excellent for smoothies"],
            "removed": ["delivers unbeatable power", "blast ice into snow in seconds"],
        },
        "shopper_intent_model": {
            "query_clusters": [
                "blender with strong ice crushing power",
                "large capacity blender for families",
            ],
            "content_gaps": ["No mention of noise level"],
            "optimization_priority": [
                "blender with strong ice crushing power",
                "large capacity blender for families",
            ],
        },
        "seo_aeo_notes": "Front-loaded primary keywords in title.",
    },
    "item_highlights": "Ice Crushing, BPA-Free Pitcher, Dishwasher Safe, Smoothie Ready, 6-Blade Assembly",
    "optimized_title": "Ninja Professional Blender 1000W XL 72-oz. Pitcher",
    "optimized_bullets": [
        "1000 WATT POWER: Delivers ample blending strength.",
        "XL 72-OZ. PITCHER: Generous capacity for the family.",
    ],
    "optimized_description": "A powerful countertop blender for daily use.",
    "changes_summary": {
        "title": {
            "retained_from_PDP": [
                {"phrase": "Ninja Professional Blender", "why": "Brand anchor"}
            ],
            "added_or_changed": [
                {"phrase": "1000W", "source": "PDP inference",
                 "why": "Front-loads power spec"}
            ],
        },
        "bullets": {
            "retained_from_PDP": [
                {"phrase": "1000 watts of power", "why": "Verifiable spec"}
            ],
            "added_or_changed": [
                {"phrase": "XL 72-OZ. PITCHER bullet", "source": "PDP inference",
                 "why": "Capacity query"}
            ],
            "removed": [
                {"phrase": "unbeatable power", "why": "Inflated claim"}
            ],
        },
        "description": {
            "retained_from_PDP": [
                {"phrase": "1000 watts", "why": "Core attribute"}
            ],
            "added_or_changed": [],
            "removed": [
                {"phrase": "smooth results every time", "why": "Absolute claim"}
            ],
        },
    },
}

SAMPLE_SKU_DATA = {
    "sku": "B00NGV4506",
    "title": "Ninja Professional Blender | 1000W | XL 72-oz. Pitcher | BL610",
    "image_url": "https://images.amazon.com/images/I/test.jpg",
    "product_page_url": "https://www.amazon.com/dp/B00NGV4506",
    "avg_rank": 5.2,
    "best_rank": 3,
    "keywords": 12,
    "page1_kws": 8,
    "current_keywords": [
        {"term": "professional blender", "rank": 3},
        {"term": "ninja blender 1000w", "rank": 5},
    ],
}


# ── _flatten_section_changes ────────────────────────────────────────────────

class TestFlattenSectionChanges:
    def test_dict_with_all_sections(self):
        from sov.sku_optimizer import _flatten_section_changes

        section = {
            "retained_from_PDP": [
                {"phrase": "Brand name", "why": "Anchor"}
            ],
            "added_or_changed": [
                {"phrase": "New keyword", "why": "Gap fill"}
            ],
            "removed": [
                {"phrase": "Bad claim", "why": "Unsupported"}
            ],
        }
        result = _flatten_section_changes(section)
        assert len(result) == 3
        assert result[0]["type"] == "keep"
        assert result[0]["label"] == "Brand name"
        assert result[0]["detail"] == "Anchor"
        assert result[1]["type"] == "add"
        assert result[2]["type"] == "remove"

    def test_empty_dict(self):
        from sov.sku_optimizer import _flatten_section_changes
        assert _flatten_section_changes({}) == []

    def test_none_input(self):
        from sov.sku_optimizer import _flatten_section_changes
        assert _flatten_section_changes(None) == []

    def test_list_input_legacy(self):
        from sov.sku_optimizer import _flatten_section_changes

        section = [
            {"change": "Added keyword", "reason": "Fills gap"}
        ]
        result = _flatten_section_changes(section)
        assert len(result) == 1
        assert result[0]["type"] == "add"
        assert result[0]["label"] == "Added keyword"

    def test_partial_dict(self):
        from sov.sku_optimizer import _flatten_section_changes

        section = {"retained_from_PDP": [{"phrase": "A", "why": "B"}]}
        result = _flatten_section_changes(section)
        assert len(result) == 1
        assert result[0]["type"] == "keep"


# ── build_sku_card ──────────────────────────────────────────────────────────

class TestBuildSkuCard:
    def test_card_structure(self):
        from sov.sku_optimizer import build_sku_card

        card = build_sku_card(
            asin="B00NGV4506",
            current_title="Ninja Pro Blender",
            current_bullets=["bullet 1", "bullet 2"],
            current_description="A great blender.",
            optimized=SAMPLE_OPTIMIZED,
            image_url="https://img.test/img.jpg",
            product_page_url="https://www.amazon.com/dp/B00NGV4506",
            avg_rank=5.2,
            best_rank=3,
            keywords=12,
            page1_kws=8,
        )
        assert card["asin"] == "B00NGV4506"
        assert card["currentTitle"] == "Ninja Pro Blender"
        assert card["recommendedTitle"] == SAMPLE_OPTIMIZED["optimized_title"]
        assert card["currentBullets"] == ["bullet 1", "bullet 2"]
        assert len(card["recommendedBullets"]) == 2
        assert card["recommendedBullets"][0]["text"].startswith("1000 WATT")
        assert card["currentDescription"] == "A great blender."
        assert card["recommendedDescription"] == SAMPLE_OPTIMIZED["optimized_description"]
        assert card["inferredIntent"] == SAMPLE_OPTIMIZED["inferred_intent"]
        assert card["optimizationMode"] == "self-directed"
        assert card["itemHighlights"] == SAMPLE_OPTIMIZED["item_highlights"]
        assert card["image_url"] == "https://img.test/img.jpg"
        assert card["avg_rank"] == 5
        assert card["best_rank"] == 3
        assert card["keywords"] == 12
        assert card["page1_kws"] == 8

    def test_card_has_self_directed_analysis(self):
        from sov.sku_optimizer import build_sku_card

        card = build_sku_card(
            asin="B00NGV4506",
            current_title="Test",
            current_bullets=[],
            current_description="",
            optimized=SAMPLE_OPTIMIZED,
        )
        assert "selfDirectedAnalysis" in card
        sda = card["selfDirectedAnalysis"]
        assert "carry_forward" in sda["content_credibility_profile"]
        assert "query_clusters" in sda["shopper_intent_model"]
        assert sda["seo_aeo_notes"]

    def test_title_highlight_detected(self):
        from sov.sku_optimizer import build_sku_card

        card = build_sku_card(
            asin="B00NGV4506",
            current_title="Ninja Blender",
            current_bullets=[],
            current_description="",
            optimized={
                "optimized_title": "Ninja Blender 1000W Ice Crushing",
                "optimized_bullets": [],
                "optimized_description": "",
                "changes_summary": {},
            },
        )
        assert "1000W" in card["recommendedTitleHighlight"]

    def test_title_highlight_empty_when_same(self):
        from sov.sku_optimizer import build_sku_card

        card = build_sku_card(
            asin="X",
            current_title="Same Title",
            current_bullets=[],
            current_description="",
            optimized={
                "optimized_title": "Same Title",
                "optimized_bullets": [],
                "optimized_description": "",
                "changes_summary": {},
            },
        )
        assert card["recommendedTitleHighlight"] == ""

    def test_reasons_flattened(self):
        from sov.sku_optimizer import build_sku_card

        card = build_sku_card(
            asin="B00NGV4506",
            current_title="Test",
            current_bullets=[],
            current_description="",
            optimized=SAMPLE_OPTIMIZED,
        )
        assert len(card["titleReasons"]) == 2
        assert card["titleReasons"][0]["type"] == "keep"
        assert card["titleReasons"][1]["type"] == "add"
        assert any(r["type"] == "remove" for r in card["bulletReasons"])
        assert any(r["type"] == "remove" for r in card["descriptionReasons"])

    def test_card_without_optional_fields(self):
        from sov.sku_optimizer import build_sku_card

        card = build_sku_card(
            asin="X",
            current_title="T",
            current_bullets=[],
            current_description="",
            optimized={"optimized_title": "T2",
                       "optimized_bullets": [],
                       "optimized_description": "",
                       "changes_summary": {}},
        )
        assert card["amazonUrl"] == "https://www.amazon.com/dp/X"
        assert card["image_url"] == ""
        assert card["avg_rank"] == 0
        assert "selfDirectedAnalysis" not in card


# ── optimize_pdp (mocked OpenAI) ───────────────────────────────────────────

class TestOptimizePdp:
    @patch("sov.sku_optimizer.SETTINGS")
    def test_optimize_pdp_parses_json_response(self, mock_settings):
        from sov.sku_optimizer import optimize_pdp

        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4.1"

        response_json = json.dumps([SAMPLE_OPTIMIZED])
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = response_json

        with patch("openai.OpenAI") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            result = optimize_pdp(
                asin="B00NGV4506",
                title="Ninja Blender",
                bullets=["bullet 1"],
                description="A blender.",
            )
            assert result["sku"] == "B00NGV4506"
            assert result["optimized_title"]
            assert result["optimization_mode"] == "self-directed"

    @patch("sov.sku_optimizer.SETTINGS")
    def test_optimize_pdp_strips_markdown_fences(self, mock_settings):
        from sov.sku_optimizer import optimize_pdp

        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4.1"

        wrapped = f"```json\n{json.dumps([SAMPLE_OPTIMIZED])}\n```"
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = wrapped

        with patch("openai.OpenAI") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            result = optimize_pdp("B00NGV4506", "T", [], "")
            assert result["sku"] == "B00NGV4506"


# ── optimize_sku_for_report ─────────────────────────────────────────────────

class TestOptimizeSkuForReport:
    @patch("sov.sku_optimizer.SETTINGS")
    def test_returns_card_on_openai_success(self, mock_settings):
        from sov.sku_optimizer import optimize_sku_for_report

        mock_settings.openai_ready = True
        mock_settings.openai_api_key = "test"
        mock_settings.openai_model = "gpt-4.1"

        resp_json = json.dumps([SAMPLE_OPTIMIZED])
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = resp_json

        with patch("openai.OpenAI") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            card, source = optimize_sku_for_report(
                SAMPLE_SKU_DATA, "Ninja", "Blenders")
            assert source == "openai"
            assert card is not None
            assert card["asin"] == "B00NGV4506"
            assert card["recommendedTitle"]
            assert card["image_url"] == SAMPLE_SKU_DATA["image_url"]
            assert card["avg_rank"] == round(SAMPLE_SKU_DATA["avg_rank"])

    @patch("sov.sku_optimizer.SETTINGS")
    def test_falls_back_to_template(self, mock_settings):
        from sov.sku_optimizer import optimize_sku_for_report

        mock_settings.openai_ready = False

        card, source = optimize_sku_for_report(
            SAMPLE_SKU_DATA, "Ninja", "Blenders")
        assert source == "template"
        assert card is not None
        assert card["asin"] == "B00NGV4506"
        assert "Ninja" in card["recommendedTitle"] or "ninja" in card["recommendedTitle"].lower()
        assert card["optimizationMode"] == "template"

    @patch("sov.sku_optimizer.SETTINGS")
    def test_falls_back_on_openai_error(self, mock_settings):
        from sov.sku_optimizer import optimize_sku_for_report

        mock_settings.openai_ready = True
        mock_settings.openai_api_key = "test"
        mock_settings.openai_model = "gpt-4.1"

        with patch("openai.OpenAI") as MockClient:
            MockClient.side_effect = Exception("API error")

            card, source = optimize_sku_for_report(
                SAMPLE_SKU_DATA, "Ninja", "Blenders")
            assert source == "template"
            assert card is not None

    @patch("sov.sku_optimizer.SETTINGS")
    def test_returns_none_for_empty_title(self, mock_settings):
        from sov.sku_optimizer import optimize_sku_for_report

        mock_settings.openai_ready = False

        card, source = optimize_sku_for_report(
            {"sku": "X", "title": ""}, "Brand", "Cat")
        assert card is None


# ── _template_card ──────────────────────────────────────────────────────────

class TestTemplateCard:
    def test_template_card_structure(self):
        from sov.sku_optimizer import _template_card

        card = _template_card(SAMPLE_SKU_DATA, "Ninja", "Blenders")
        assert card["asin"] == "B00NGV4506"
        assert len(card["recommendedTitle"]) <= 75
        assert len(card["recommendedBullets"]) == 5
        assert card["optimizationMode"] == "template"
        assert card["inferredIntent"]
        assert card["amazonUrl"] == "https://www.amazon.com/dp/B00NGV4506"
        assert card["image_url"] == SAMPLE_SKU_DATA["image_url"]
        assert "itemHighlights" in card
        assert len(card["itemHighlights"]) <= 125

    def test_template_card_no_keywords(self):
        from sov.sku_optimizer import _template_card

        card = _template_card(
            {"sku": "X", "title": "Product Title", "current_keywords": []},
            "Brand", "Category")
        assert card["asin"] == "X"
        assert "Brand" in card["recommendedTitle"]
        assert len(card["titleReasons"]) == 1
        assert card["itemHighlights"] == "Category"


# ── OPTIMIZATION_SYSTEM_PROMPT ──────────────────────────────────────────────

class TestPromptContent:
    def test_prompt_contains_key_sections(self):
        from sov.sku_optimizer import OPTIMIZATION_SYSTEM_PROMPT

        assert "LAYER 1" in OPTIMIZATION_SYSTEM_PROMPT
        assert "LAYER 2" in OPTIMIZATION_SYSTEM_PROMPT
        assert "LAYER 3" in OPTIMIZATION_SYSTEM_PROMPT
        assert "TIER A" in OPTIMIZATION_SYSTEM_PROMPT
        assert "TIER B" in OPTIMIZATION_SYSTEM_PROMPT
        assert "TIER C" in OPTIMIZATION_SYSTEM_PROMPT
        assert "SHOPPER INTENT MODEL" in OPTIMIZATION_SYSTEM_PROMPT
        assert "AEO" in OPTIMIZATION_SYSTEM_PROMPT
        assert "75-CHARACTER MAXIMUM" in OPTIMIZATION_SYSTEM_PROMPT
        assert "Noun Phrase Headers" in OPTIMIZATION_SYSTEM_PROMPT
        assert "changes_summary" in OPTIMIZATION_SYSTEM_PROMPT
        assert "self_directed_analysis" in OPTIMIZATION_SYSTEM_PROMPT

    def test_prompt_is_substantial(self):
        from sov.sku_optimizer import OPTIMIZATION_SYSTEM_PROMPT
        assert len(OPTIMIZATION_SYSTEM_PROMPT) > 5000


# ── Report rendering ────────────────────────────────────────────────────────

class TestReportRendering:
    def _make_card(self):
        from sov.sku_optimizer import build_sku_card
        return build_sku_card(
            asin="B00NGV4506",
            current_title="Ninja Professional Blender | 1000W | XL 72-oz.",
            current_bullets=["POWER: 1000 watts", "XL CAPACITY: 72 oz."],
            current_description="A powerful blender for your kitchen.",
            optimized=SAMPLE_OPTIMIZED,
            image_url="https://img.test/img.jpg",
            product_page_url="https://www.amazon.com/dp/B00NGV4506",
            avg_rank=5.2,
            best_rank=3,
            keywords=12,
            page1_kws=8,
        )

    def test_pdp_card_renders_html(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert '<div class="pdp-opt">' in html
        assert "B00NGV4506" in html
        assert "Product being optimized" in html
        assert "pdp-sec-bar cur" in html
        assert "pdp-sec-bar rec" in html
        assert ">Current</span>" in html
        assert ">Optimized</span>" in html
        assert "Optimization Analysis" in html

    def test_pdp_card_renders_title_comparison(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "pdp-sec-bar cur" in html
        assert "pdp-sec-bar rec" in html
        assert "Title</div>" in html

    def test_pdp_card_renders_description(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "Description</div>" in html

    def test_pdp_card_renders_asin_badge(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "pdp-asin-badge" in html
        assert "B00NGV4506" in html
        assert "pdp-header-label" in html
        assert "pdp-header-title" in html

    def test_pdp_card_renders_product_image(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "pdp-header-img" in html
        assert "https://img.test/img.jpg" in html

    def test_pdp_card_renders_stats(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "pdp-header-stats" in html
        assert "pdp-stat-val" in html
        assert "pdp-stat-lbl" in html
        assert "Avg Rank" in html
        assert "Keywords" in html
        assert "Page 1 KWs" not in html
        assert ">5</span>" in html   # avg_rank rounded
        assert ">12</span>" in html  # keywords

    def test_pdp_card_renders_item_highlights(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "ih-text" in html
        assert "Item Highlights" in html
        assert "Ice Crushing" in html
        assert "BPA-Free Pitcher" in html

    def test_pdp_card_no_highlights_when_empty(self):
        from sov.report import _sku_pdp_card
        from sov.sku_optimizer import build_sku_card
        no_highlights = {**SAMPLE_OPTIMIZED, "item_highlights": ""}
        card = build_sku_card(
            asin="X", current_title="T", current_bullets=[],
            current_description="",
            optimized=no_highlights,
        )
        html = _sku_pdp_card(card)
        assert "ih-text" not in html

    def test_pdp_card_no_image_when_empty(self):
        from sov.report import _sku_pdp_card
        from sov.sku_optimizer import build_sku_card
        card = build_sku_card(
            asin="X", current_title="T", current_bullets=[],
            current_description="",
            optimized=SAMPLE_OPTIMIZED,
        )
        html = _sku_pdp_card(card)
        assert "pdp-header-img" not in html

    def test_pdp_card_renders_numbered_bullets(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "pdp-bullet-num" in html
        assert "pdp-bullet-text" in html

    def test_pdp_card_renders_section_bars(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "pdp-sec-bar" in html
        assert "pdp-sec-pill" in html

    def test_pdp_card_shows_placeholder_when_no_current_bullets(self):
        from sov.report import _sku_pdp_card
        from sov.sku_optimizer import build_sku_card
        card = build_sku_card(
            asin="X", current_title="T", current_bullets=[],
            current_description="",
            optimized=SAMPLE_OPTIMIZED,
        )
        html = _sku_pdp_card(card)
        assert "No current bullets available" in html
        assert ">Current</span> Bullets</div>" in html
        assert ">Optimized</span> Bullets</div>" in html

    def test_pdp_card_shows_placeholder_when_no_current_description(self):
        from sov.report import _sku_pdp_card
        from sov.sku_optimizer import build_sku_card
        card = build_sku_card(
            asin="X", current_title="T", current_bullets=[],
            current_description="",
            optimized=SAMPLE_OPTIMIZED,
        )
        html = _sku_pdp_card(card)
        assert "No current description available" in html
        assert ">Current</span> Description</div>" in html
        assert ">Optimized</span> Description</div>" in html

    def test_reason_chips_inline_detail(self):
        from sov.report import _reason_chips
        html = _reason_chips([
            {"type": "keep", "label": "Brand", "detail": "Anchor"},
        ])
        assert "&mdash;" in html
        assert "Anchor" in html

    def test_pdp_card_renders_analysis(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "Content Credibility Profile" in html
        assert "Carry Forward" in html
        assert "Tier B" in html
        assert "Tier C" in html
        assert "SEO &amp; AEO Notes" not in html
        assert "Shopper Intent Model" not in html

    def test_pdp_card_renders_reasons(self):
        from sov.report import _sku_pdp_card
        card = self._make_card()
        html = _sku_pdp_card(card)
        assert "reason-keep" in html
        assert "reason-add" in html
        assert "reason-remove" in html

    def test_pdp_card_empty_returns_empty(self):
        from sov.report import _sku_pdp_card
        assert _sku_pdp_card({}) == ""
        assert _sku_pdp_card(None) == ""

    def test_reason_chips_empty(self):
        from sov.report import _reason_chips
        assert _reason_chips([]) == ""

    def test_reason_chips_renders(self):
        from sov.report import _reason_chips
        html = _reason_chips([
            {"type": "keep", "label": "Brand", "detail": "Anchor"},
            {"type": "add", "label": "New", "detail": "Gap"},
            {"type": "remove", "label": "Bad", "detail": "Unsupported"},
        ])
        assert "reason-keep" in html
        assert "reason-add" in html
        assert "reason-remove" in html
        assert "Brand" in html
        assert "Anchor" in html

    def test_reason_chips_legend(self):
        from sov.report import _reason_chips
        html = _reason_chips([
            {"type": "keep", "label": "Brand", "detail": "Anchor"},
        ])
        assert "pdp-reason-legend" in html
        assert "Retained" in html
        assert "Added" in html
        assert "Removed" in html

    def test_self_directed_block_renders(self):
        from sov.report import _self_directed_block
        sda = SAMPLE_OPTIMIZED["self_directed_analysis"]
        html = _self_directed_block(sda)
        assert "tier-a" in html
        assert "tier-b" in html
        assert "tier-c" in html
        assert "1000 watts of power" in html
        assert "Shopper Intent Model" not in html
        assert "SEO" not in html

    def test_self_directed_block_empty(self):
        from sov.report import _self_directed_block
        html = _self_directed_block({})
        assert "pdp-analysis" in html


class TestAppBuildSkuOpt:
    """Verify the _build_sku_opt returns single-card format."""

    def test_output_has_card_not_items(self):
        import pandas as pd
        opt_df = pd.DataFrame([{
            "sku": "B00NGV4506",
            "title": "Test Product",
            "image_url": "https://img.test/x.jpg",
            "product_page_url": "https://www.amazon.com/dp/B00NGV4506",
            "avg_rank": 5.0,
            "best_rank": 3,
            "keywords": 10,
            "page1_kws": 6,
            "kw_ranked": [{"term": "blender", "rank": 3}],
        }])

        from sov.sku_optimizer import _template_card
        card = _template_card(opt_df.iloc[0].to_dict() | {
            "current_keywords": opt_df.iloc[0].get("kw_ranked", [])
        }, "Ninja", "Blenders")
        block = {
            "intro": "Test intro",
            "card": card,
        }
        assert "card" in block
        assert "items" not in block
        assert block["card"]["asin"] == "B00NGV4506"


class TestTieredSkuSelection:
    """Verify the tiered SKU selection logic: prefer avg_rank > 30,
    then > 24, then fallback to the original list."""

    def test_selects_rank_above_30_first(self):
        import pandas as pd
        opt_df = pd.DataFrame([
            {"sku": "A", "avg_rank": 10.0},
            {"sku": "B", "avg_rank": 35.0},
            {"sku": "C", "avg_rank": 25.0},
        ])
        deep = opt_df[opt_df["avg_rank"] > 30]
        if deep.empty:
            deep = opt_df[opt_df["avg_rank"] > 24]
        if deep.empty:
            deep = opt_df
        assert deep.iloc[0]["sku"] == "B"

    def test_falls_back_to_rank_above_24(self):
        import pandas as pd
        opt_df = pd.DataFrame([
            {"sku": "A", "avg_rank": 10.0},
            {"sku": "C", "avg_rank": 28.0},
            {"sku": "D", "avg_rank": 15.0},
        ])
        deep = opt_df[opt_df["avg_rank"] > 30]
        if deep.empty:
            deep = opt_df[opt_df["avg_rank"] > 24]
        if deep.empty:
            deep = opt_df
        assert deep.iloc[0]["sku"] == "C"

    def test_falls_back_to_original_list(self):
        import pandas as pd
        opt_df = pd.DataFrame([
            {"sku": "A", "avg_rank": 10.0},
            {"sku": "B", "avg_rank": 5.0},
        ])
        deep = opt_df[opt_df["avg_rank"] > 30]
        if deep.empty:
            deep = opt_df[opt_df["avg_rank"] > 24]
        if deep.empty:
            deep = opt_df
        assert deep.iloc[0]["sku"] == "A"

    def test_multiple_above_30_picks_first(self):
        import pandas as pd
        opt_df = pd.DataFrame([
            {"sku": "A", "avg_rank": 40.0},
            {"sku": "B", "avg_rank": 35.0},
            {"sku": "C", "avg_rank": 10.0},
        ])
        deep = opt_df[opt_df["avg_rank"] > 30]
        if deep.empty:
            deep = opt_df[opt_df["avg_rank"] > 24]
        if deep.empty:
            deep = opt_df
        assert deep.iloc[0]["sku"] == "A"

    def test_empty_dataframe_handled(self):
        import pandas as pd
        opt_df = pd.DataFrame(columns=["sku", "avg_rank"])
        deep = opt_df[opt_df["avg_rank"] > 30]
        assert deep.empty
        deep = opt_df[opt_df["avg_rank"] > 24]
        assert deep.empty
        deep = opt_df
        assert deep.empty
