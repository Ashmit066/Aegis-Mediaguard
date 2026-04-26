"""
tests/test_verdicts.py
End-to-end verdict tests covering all defined VerdictType outcomes.
"""

import pytest

from identify.matcher import match_report
from ingest.normalizer import normalize_report
from ingest.schema_guard import validate_report
from rights.policy_engine import evaluate_rights
from risk.verdicts import issue_verdict
from data.mock_assets import get_asset_by_id
from app.models import VerdictType


def _pipeline(overrides: dict = {}):
    """Helper: run the full verdict pipeline from a report dict."""
    base = {
        "report_id": "RPT-VERDICT-0001",
        "discovered_url": "https://www.youtube.com/watch?v=test",
        "platform": "youtube",
        "geo_country": "US",
        "detected_at": "2024-07-15T10:00:00",
        "media_type": "highlight_clip",
        "claimant_org": "RightsScan AI",
        "event_name": "NBA Finals 2024",
        "uploader_handle": "user",
        "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
        "extracted_watermark": "WM-NBA-010",
        "screenshot_hash": None,
        "confidence_hint": 0.95,
    }
    data = {**base, **overrides}
    report = normalize_report(validate_report(data))
    match = match_report(report)
    rights = None
    if match.matched_asset_id:
        asset = get_asset_by_id(match.matched_asset_id)
        if asset:
            rights = evaluate_rights(report, asset)
    return issue_verdict(report, match, rights)


def test_authorized_verdict():
    verdict = _pipeline()
    assert verdict.verdict == VerdictType.authorized
    assert verdict.severity_score < 40


def test_unauthorized_platform_is_suspected_infringement():
    verdict = _pipeline({"platform": "tiktok"})
    assert verdict.verdict == VerdictType.suspected_infringement
    assert verdict.severity_score >= 55


def test_unauthorized_region_is_suspected_infringement():
    verdict = _pipeline({"geo_country": "IN"})
    # NBA asset only allows US, CA
    assert verdict.verdict in (VerdictType.suspected_infringement, VerdictType.manual_review)


def test_expired_license_verdict():
    verdict = _pipeline({
        "detected_at": "2024-07-10T12:00:00",
        "platform": "youtube",
        "geo_country": "US",
        "event_name": "FIFA World Cup 2022",
        "extracted_fingerprint": "9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c",
        "extracted_watermark": "WM-FIFA-300",
    })
    assert verdict.verdict == VerdictType.suspected_infringement
    assert verdict.rights_decision is not None
    assert verdict.rights_decision.license_valid is False


def test_urgent_live_leak_verdict():
    verdict = _pipeline({
        "platform": "reddit",
        "geo_country": "US",
        "media_type": "live_stream",
        "event_name": "IPL 2024",
        "extracted_fingerprint": "f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5",
        "extracted_watermark": "WM-IPL-200",
        "detected_at": "2024-04-10T18:00:00",
    })
    assert verdict.verdict == VerdictType.urgent_live_leak
    assert verdict.severity_score >= 85


def test_unknown_asset_verdict():
    verdict = _pipeline({
        "extracted_fingerprint": "0000000000000000ffffffffffffffff",
        "extracted_watermark": None,
    })
    assert verdict.verdict == VerdictType.unknown_asset
    assert verdict.matched_asset_id is None


def test_severity_score_in_range():
    verdict = _pipeline()
    assert 0 <= verdict.severity_score <= 100


def test_reasoning_is_non_empty():
    verdict = _pipeline()
    assert len(verdict.reasoning) > 0
