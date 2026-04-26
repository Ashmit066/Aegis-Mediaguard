"""
tests/test_api.py
Integration tests for all HTTP endpoints via FastAPI TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTHORIZED_PAYLOAD = {
    "report_id": "RPT-API-AUTH-001",
    "discovered_url": "https://www.youtube.com/watch?v=nba_finals_official_clip",
    "platform": "youtube",
    "geo_country": "US",
    "detected_at": "2024-07-15T10:00:00",
    "media_type": "highlight_clip",
    "claimant_org": "RightsScan AI",
    "event_name": "NBA Finals 2024",
    "uploader_handle": "NBA_Official",
    "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
    "extracted_watermark": "WM-NBA-010",
    "screenshot_hash": "abc123def456",
    "confidence_hint": 0.95,
}


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_assets_returns_list():
    r = client.get("/assets")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "asset_id" in data[0]


def test_analyze_authorized():
    r = client.post("/reports/analyze", json=AUTHORIZED_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "authorized"
    assert body["severity_score"] < 40


def test_analyze_unauthorized_platform():
    payload = {**AUTHORIZED_PAYLOAD, "report_id": "RPT-API-PLAT-002", "platform": "tiktok"}
    r = client.post("/reports/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "suspected_infringement"


def test_analyze_unauthorized_geo():
    payload = {**AUTHORIZED_PAYLOAD, "report_id": "RPT-API-GEO-003", "geo_country": "IN"}
    r = client.post("/reports/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] in ("suspected_infringement", "manual_review")


def test_analyze_expired_license():
    payload = {
        **AUTHORIZED_PAYLOAD,
        "report_id": "RPT-API-EXP-004",
        "detected_at": "2024-07-10T12:00:00",
        "platform": "youtube",
        "geo_country": "US",
        "event_name": "FIFA World Cup 2022",
        "extracted_fingerprint": "9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c",
        "extracted_watermark": "WM-FIFA-300",
    }
    r = client.post("/reports/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "suspected_infringement"
    assert body["rights_decision"]["license_valid"] is False


def test_analyze_urgent_live_leak():
    payload = {
        **AUTHORIZED_PAYLOAD,
        "report_id": "RPT-API-LIVE-005",
        "platform": "reddit",
        "geo_country": "US",
        "media_type": "live_stream",
        "event_name": "IPL 2024",
        "extracted_fingerprint": "f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5",
        "extracted_watermark": "WM-IPL-200",
        "detected_at": "2024-04-10T18:00:00",
    }
    r = client.post("/reports/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "urgent_live_leak"
    assert body["severity_score"] >= 85


def test_analyze_unknown_asset():
    payload = {
        **AUTHORIZED_PAYLOAD,
        "report_id": "RPT-API-UNK-006",
        "extracted_fingerprint": "0000000000000000ffffffffffffffff",
        "extracted_watermark": None,
    }
    r = client.post("/reports/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "unknown_asset"


def test_analyze_invalid_schema():
    bad_payload = {"report_id": "bad", "platform": "youtube"}  # many missing fields
    r = client.post("/reports/analyze", json=bad_payload)
    assert r.status_code == 422
    body = r.json()
    assert "errors" in body["detail"]


def test_analyze_extra_field_rejected():
    payload = {**AUTHORIZED_PAYLOAD, "report_id": "RPT-API-EXTRA-007", "evil_field": "hacked"}
    r = client.post("/reports/analyze", json=payload)
    assert r.status_code == 422


def test_ledger_grows_after_analysis():
    before = len(client.get("/ledger").json())
    client.post("/reports/analyze", json={**AUTHORIZED_PAYLOAD, "report_id": "RPT-API-LED-008"})
    after = len(client.get("/ledger").json())
    assert after > before


def test_ledger_verify_intact():
    r = client.get("/ledger/verify")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
