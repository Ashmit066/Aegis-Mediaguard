"""
tests/test_rights.py
Tests for the rights policy engine — platform, region, and date checks.
"""

import pytest
from datetime import datetime, timezone

from rights.policy_engine import evaluate_rights
from ingest.schema_guard import validate_report
from ingest.normalizer import normalize_report
from data.mock_assets import get_asset_by_id


def _make_report(overrides: dict = {}):
    base = {
        "report_id": "RPT-RIGHTS-0001",
        "discovered_url": "https://www.youtube.com/watch?v=nba_test",
        "platform": "youtube",
        "geo_country": "US",
        "detected_at": "2024-07-15T10:00:00",
        "media_type": "highlight_clip",
        "claimant_org": "RightsScan AI",
        "event_name": "NBA Finals 2024",
        "uploader_handle": "test_user",
        "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
        "extracted_watermark": "WM-NBA-010",
        "screenshot_hash": "abc123",
        "confidence_hint": 0.9,
    }
    data = {**base, **overrides}
    report = validate_report(data)
    return normalize_report(report)


def test_fully_authorized():
    """youtube + US + within license window → authorized."""
    report = _make_report()
    asset = get_asset_by_id("ASSET-002")
    decision = evaluate_rights(report, asset)
    assert decision.is_authorized is True
    assert decision.platform_ok is True
    assert decision.region_ok is True
    assert decision.license_valid is True


def test_unauthorized_platform():
    """tiktok is not in NBA authorized_platforms."""
    report = _make_report({"platform": "tiktok"})
    asset = get_asset_by_id("ASSET-002")
    decision = evaluate_rights(report, asset)
    assert decision.platform_ok is False
    assert decision.is_authorized is False


def test_unauthorized_region():
    """IN is not in NBA authorized_regions (US, CA only)."""
    report = _make_report({"geo_country": "IN"})
    asset = get_asset_by_id("ASSET-002")
    decision = evaluate_rights(report, asset)
    assert decision.region_ok is False
    assert decision.is_authorized is False


def test_expired_license():
    """FIFA World Cup 2022 license expired 2024-01-01; detect in July 2024."""
    report = _make_report({
        "detected_at": "2024-07-10T12:00:00",
        "platform": "youtube",
        "geo_country": "US",
        "event_name": "FIFA World Cup 2022",
        "extracted_fingerprint": "9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c",
    })
    asset = get_asset_by_id("ASSET-005")
    decision = evaluate_rights(report, asset)
    assert decision.license_valid is False
    assert decision.is_authorized is False


def test_reasons_list_has_three_entries():
    """Policy engine always returns exactly three reason strings."""
    report = _make_report()
    asset = get_asset_by_id("ASSET-002")
    decision = evaluate_rights(report, asset)
    assert len(decision.reasons) == 3


def test_authorized_reason_message_content():
    report = _make_report()
    asset = get_asset_by_id("ASSET-002")
    decision = evaluate_rights(report, asset)
    assert any("authorized" in r.lower() for r in decision.reasons)
