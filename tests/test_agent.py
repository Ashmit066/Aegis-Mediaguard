"""
tests/test_agent.py
Tests for the agentic triage layer.

Covers:
- Agent summary generated for an infringement case
- Agent summary generated for unknown asset
- Guardrails reject unsafe agent actions
- Agent endpoint does not modify the deterministic verdict
- Agent endpoint fails gracefully for a missing case_id
- Draft takedown notice is included for actionable verdicts
- Draft takedown notice is absent for authorized cases
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from agent.policy import AgentAction, check_policy
from agent.orchestrator import attempt_blocked_action

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------

INFRINGEMENT_PAYLOAD = {
    "report_id": "RPT-AGENT-INF-001",
    "discovered_url": "https://www.tiktok.com/@pirate/nba_finals_stolen",
    "platform": "tiktok",
    "geo_country": "US",
    "detected_at": "2024-07-16T14:32:00",
    "media_type": "highlight_clip",
    "claimant_org": "RightsScan AI",
    "event_name": "NBA Finals 2024",
    "uploader_handle": "pirate_user99",
    "extracted_fingerprint": "d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
    "extracted_watermark": None,
    "screenshot_hash": None,
    "confidence_hint": 0.88,
}

UNKNOWN_ASSET_PAYLOAD = {
    "report_id": "RPT-AGENT-UNK-002",
    "discovered_url": "https://www.dailymotion.com/video/mystery_clip",
    "platform": "dailymotion",
    "geo_country": "FR",
    "detected_at": "2024-07-01T09:30:00",
    "media_type": "highlight_clip",
    "claimant_org": "RightsScan AI",
    "event_name": "Unknown Regional League",
    "uploader_handle": "sports_mix",
    "extracted_fingerprint": "0000000000000000ffffffffffffffff",
    "extracted_watermark": None,
    "screenshot_hash": None,
    "confidence_hint": 0.30,
}

AUTHORIZED_PAYLOAD = {
    "report_id": "RPT-AGENT-AUTH-003",
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

LIVE_LEAK_PAYLOAD = {
    "report_id": "RPT-AGENT-LIVE-004",
    "discovered_url": "https://www.reddit.com/r/cricket/ipl_live_pirate",
    "platform": "reddit",
    "geo_country": "US",
    "detected_at": "2024-04-10T18:00:00",
    "media_type": "live_stream",
    "claimant_org": "Star Sports Guard",
    "event_name": "IPL 2024",
    "uploader_handle": "cricket_free_stream",
    "extracted_fingerprint": "f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5",
    "extracted_watermark": "WM-IPL-200",
    "screenshot_hash": None,
    "confidence_hint": 0.97,
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _analyze_and_get_summary(payload: dict) -> tuple[dict, dict]:
    """Submit a report and fetch its agent summary.  Returns (verdict, summary)."""
    r1 = client.post("/reports/analyze", json=payload)
    assert r1.status_code == 200, r1.text
    verdict = r1.json()

    r2 = client.get(f"/cases/{payload['report_id']}/agent-summary")
    assert r2.status_code == 200, r2.text
    return verdict, r2.json()


# ---------------------------------------------------------------------------
# Test: infringement case produces a full summary
# ---------------------------------------------------------------------------

def test_agent_summary_for_infringement_case():
    verdict, summary = _analyze_and_get_summary(INFRINGEMENT_PAYLOAD)

    assert summary["case_id"] == INFRINGEMENT_PAYLOAD["report_id"]
    assert summary["verdict"] == "suspected_infringement"
    assert summary["urgency_label"] in ("HIGH", "CRITICAL", "MEDIUM")
    assert len(summary["summary"]) > 20
    assert isinstance(summary["key_evidence"], list)
    assert len(summary["key_evidence"]) >= 1
    assert len(summary["recommended_action"]) > 10


def test_agent_summary_infringement_has_draft_notice():
    _, summary = _analyze_and_get_summary(INFRINGEMENT_PAYLOAD)
    # Infringement cases should include a draft takedown notice
    assert summary["draft_takedown_notice"] is not None
    assert "DRAFT TAKEDOWN NOTICE" in summary["draft_takedown_notice"]
    assert "tiktok" in summary["draft_takedown_notice"].lower()


# ---------------------------------------------------------------------------
# Test: unknown asset case
# ---------------------------------------------------------------------------

def test_agent_summary_for_unknown_asset():
    verdict, summary = _analyze_and_get_summary(UNKNOWN_ASSET_PAYLOAD)

    assert summary["verdict"] == "unknown_asset"
    assert summary["matched_asset_id"] is None
    assert "unknown" in summary["summary"].lower() or "not" in summary["summary"].lower()
    # Unknown asset has no takedown notice
    assert summary["draft_takedown_notice"] is None


# ---------------------------------------------------------------------------
# Test: urgent live leak
# ---------------------------------------------------------------------------

def test_agent_summary_for_live_leak_is_critical():
    verdict, summary = _analyze_and_get_summary(LIVE_LEAK_PAYLOAD)

    assert summary["verdict"] == "urgent_live_leak"
    assert summary["urgency_label"] == "CRITICAL"
    assert summary["draft_takedown_notice"] is not None
    assert "DRAFT" in summary["draft_takedown_notice"]


# ---------------------------------------------------------------------------
# Test: authorized case has low urgency and no takedown notice
# ---------------------------------------------------------------------------

def test_agent_summary_for_authorized_case():
    verdict, summary = _analyze_and_get_summary(AUTHORIZED_PAYLOAD)

    assert summary["verdict"] == "authorized"
    assert summary["urgency_label"] == "LOW"
    assert summary["draft_takedown_notice"] is None


# ---------------------------------------------------------------------------
# Test: guardrails reject unsafe actions via policy layer
# ---------------------------------------------------------------------------

def test_policy_blocks_verdict_override():
    result = check_policy(AgentAction.OVERRIDE_VERDICT)
    assert result.allowed is False
    assert "immutable" in result.reason.lower() or "enforcement" in result.reason.lower()


def test_policy_blocks_ledger_deletion():
    result = check_policy(AgentAction.DELETE_LEDGER_ENTRY)
    assert result.allowed is False
    assert "append-only" in result.reason.lower() or "chain" in result.reason.lower()


def test_policy_blocks_rights_mutation():
    result = check_policy(AgentAction.MUTATE_RIGHTS_DATA)
    assert result.allowed is False


def test_policy_blocks_direct_enforcement():
    result = check_policy(AgentAction.EXECUTE_TAKEDOWN)
    assert result.allowed is False
    assert "human" in result.reason.lower()


def test_policy_blocks_catalog_mutation():
    result = check_policy(AgentAction.MODIFY_ASSET_CATALOG)
    assert result.allowed is False


def test_attempt_blocked_action_returns_structured_error():
    result = attempt_blocked_action(AgentAction.OVERRIDE_VERDICT)
    assert result["allowed"] is False
    assert result["action"] == "override_verdict"
    assert len(result["reason"]) > 10


# ---------------------------------------------------------------------------
# Test: allowed actions pass policy
# ---------------------------------------------------------------------------

def test_policy_allows_get_case_evidence():
    result = check_policy(AgentAction.GET_CASE_EVIDENCE)
    assert result.allowed is True


def test_policy_allows_draft_takedown():
    result = check_policy(AgentAction.DRAFT_TAKEDOWN_NOTICE)
    assert result.allowed is True


# ---------------------------------------------------------------------------
# Test: agent endpoint does not modify the deterministic verdict
# ---------------------------------------------------------------------------

def test_agent_endpoint_does_not_modify_verdict():
    payload = {**INFRINGEMENT_PAYLOAD, "report_id": "RPT-AGENT-IMMUT-005"}

    r1 = client.post("/reports/analyze", json=payload)
    original_verdict = r1.json()["verdict"]
    original_severity = r1.json()["severity_score"]

    # Call agent summary
    client.get(f"/cases/RPT-AGENT-IMMUT-005/agent-summary")

    # Re-fetch the analysis by re-analyzing the same report_id
    # (same case_id means same slot in the store — verdict should be identical)
    r2 = client.post("/reports/analyze", json=payload)
    assert r2.json()["verdict"] == original_verdict
    assert r2.json()["severity_score"] == original_severity


# ---------------------------------------------------------------------------
# Test: missing case_id returns 404
# ---------------------------------------------------------------------------

def test_agent_endpoint_404_for_missing_case():
    r = client.get("/cases/RPT-DOES-NOT-EXIST-999/agent-summary")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: agent summary contains case_id and verdict fields
# ---------------------------------------------------------------------------

def test_agent_summary_response_shape():
    payload = {**INFRINGEMENT_PAYLOAD, "report_id": "RPT-AGENT-SHAPE-006"}
    _, summary = _analyze_and_get_summary(payload)

    required_keys = {
        "case_id", "verdict", "severity_score", "urgency_label",
        "summary", "key_evidence", "recommended_action",
        "prior_related_case_count",
    }
    assert required_keys.issubset(summary.keys())