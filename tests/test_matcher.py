"""
tests/test_matcher.py
Tests for fingerprint similarity, watermark detection, and full match orchestration.
"""

import pytest

from identify.fingerprint import fingerprint_similarity, hamming_distance
from identify.watermark import check_watermark
from identify.matcher import match_report
from ingest.schema_guard import validate_report
from ingest.normalizer import normalize_report
from data.mock_assets import get_asset_by_id


# ---------------------------------------------------------------------------
# Fingerprint / Hamming tests
# ---------------------------------------------------------------------------

def test_identical_fingerprints_score_one():
    fp = "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6"
    assert fingerprint_similarity(fp, fp) == 1.0


def test_completely_different_fingerprints_score_low():
    a = "ffffffffffffffffffffffffffffffff"
    b = "00000000000000000000000000000000"
    score = fingerprint_similarity(a, b)
    assert score == 0.0


def test_hamming_distance_identical():
    fp = "ffff"
    assert hamming_distance(fp, fp) == 0


def test_hamming_distance_one_bit():
    # fffe vs ffff differ in 1 bit
    assert hamming_distance("fffe", "ffff") == 1


def test_partial_match_score_between_zero_and_one():
    a = "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6"
    b = "d1e2f3a4b5c6d7e8ffffffffffffffff"
    score = fingerprint_similarity(a, b)
    assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# Watermark tests
# ---------------------------------------------------------------------------

def test_watermark_match_returns_true_and_boost():
    asset = get_asset_by_id("ASSET-002")
    detected, boost = check_watermark("WM-NBA-010", asset)
    assert detected is True
    assert boost > 0.0


def test_watermark_no_match_returns_false_zero():
    asset = get_asset_by_id("ASSET-002")
    detected, boost = check_watermark("WM-FAKE-999", asset)
    assert detected is False
    assert boost == 0.0


def test_none_watermark_returns_false():
    asset = get_asset_by_id("ASSET-002")
    detected, boost = check_watermark(None, asset)
    assert detected is False


# ---------------------------------------------------------------------------
# Full matcher tests
# ---------------------------------------------------------------------------

VALID_BASE = {
    "report_id": "RPT-MATCH-0001",
    "discovered_url": "https://www.youtube.com/watch?v=nba_finals_official",
    "platform": "youtube",
    "geo_country": "US",
    "detected_at": "2024-07-15T10:00:00",
    "media_type": "highlight_clip",
    "claimant_org": "RightsScan AI",
    "event_name": "NBA Finals 2024",
    "uploader_handle": "NBA_Official",
    "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
    "extracted_watermark": "WM-NBA-010",
    "screenshot_hash": "abc123",
    "confidence_hint": 0.95,
}


def _make_report(overrides: dict = {}):
    data = {**VALID_BASE, **overrides}
    report = validate_report(data)
    return normalize_report(report)


def test_known_fingerprint_matches_asset():
    report = _make_report()
    result = match_report(report)
    assert result.matched_asset_id == "ASSET-002"
    assert result.fingerprint_score == 1.0


def test_watermark_confirmed_on_match():
    report = _make_report()
    result = match_report(report)
    assert result.watermark_detected is True
    # watermark_score reflects the boost even when combined is capped at 1.0
    assert result.watermark_score > 0.0
    assert result.combined_confidence == 1.0


def test_unknown_fingerprint_returns_no_match():
    report = _make_report({"extracted_fingerprint": "0000000000000000ffffffffffffffff"})
    result = match_report(report)
    assert result.matched_asset_id is None


def test_match_without_watermark_has_zero_watermark_score():
    report = _make_report({"extracted_watermark": None})
    result = match_report(report)
    assert result.watermark_score == 0.0
    assert result.watermark_detected is False
