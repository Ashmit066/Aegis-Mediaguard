"""
tests/test_schema.py
Schema validation and normalization tests.
"""

import pytest
from datetime import datetime, timezone

from ingest.schema_guard import validate_report, SchemaValidationError
from ingest.normalizer import normalize_report


VALID_BASE = {
    "report_id": "RPT-TEST-0001",
    "discovered_url": "https://www.youtube.com/watch?v=test_clip_001",
    "platform": "YouTube",
    "geo_country": "us",
    "detected_at": "2024-07-01T10:00:00",
    "media_type": "highlight_clip",
    "claimant_org": "RightsScan AI",
    "event_name": "NBA Finals 2024",
    "uploader_handle": "test_uploader",
    "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
    "extracted_watermark": "WM-NBA-010",
    "screenshot_hash": "abc123",
    "confidence_hint": 0.9,
}


def test_valid_report_parses():
    report = validate_report(VALID_BASE)
    assert report.report_id == "RPT-TEST-0001"


def test_platform_normalized_to_lowercase():
    report = validate_report(VALID_BASE)
    assert report.platform == "youtube"


def test_unknown_platform_becomes_unknown():
    data = {**VALID_BASE, "platform": "MyWeirdPlatform"}
    report = validate_report(data)
    assert report.platform == "unknown"


def test_geo_normalized_to_uppercase():
    report = validate_report(VALID_BASE)
    assert report.geo_country == "US"


def test_unknown_geo_becomes_UNKNOWN():
    data = {**VALID_BASE, "geo_country": "XX"}
    report = validate_report(data)
    assert report.geo_country == "UNKNOWN"


def test_extra_fields_rejected():
    data = {**VALID_BASE, "injected_field": "evil"}
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_report(data)
    assert any("injected_field" in e["field"] for e in exc_info.value.errors)


def test_invalid_media_type_rejected():
    data = {**VALID_BASE, "media_type": "VHS_tape"}
    with pytest.raises(SchemaValidationError):
        validate_report(data)


def test_short_report_id_rejected():
    data = {**VALID_BASE, "report_id": "short"}
    with pytest.raises(SchemaValidationError):
        validate_report(data)


def test_confidence_hint_out_of_range_rejected():
    data = {**VALID_BASE, "confidence_hint": 1.5}
    with pytest.raises(SchemaValidationError):
        validate_report(data)


def test_normalizer_lowercases_fingerprint():
    report = validate_report(VALID_BASE)
    report_norm = normalize_report(report)
    assert report_norm.extracted_fingerprint == report_norm.extracted_fingerprint.lower()


def test_normalizer_uppercases_watermark():
    report = validate_report(VALID_BASE)
    report_norm = normalize_report(report)
    assert report_norm.extracted_watermark == "WM-NBA-010"


def test_none_watermark_stays_none():
    data = {**VALID_BASE, "extracted_watermark": None}
    report = validate_report(data)
    report_norm = normalize_report(report)
    assert report_norm.extracted_watermark is None
