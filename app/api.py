from __future__ import annotations

from fastapi import APIRouter
from typing import Dict

from app.config import settings
from app.models import (
    LedgerEntry,
    LedgerVerifyResult,
    OfficialAsset,
)
from data.mock_assets import get_all_assets
from ledger.audit import get_ledger, verify_chain

router = APIRouter()

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", tags=["system"])
def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


# ---------------------------------------------------------------------------
# Asset catalog
# ---------------------------------------------------------------------------


@router.get("/assets", response_model=list[OfficialAsset], tags=["assets"])
def list_assets() -> list[OfficialAsset]:
    return get_all_assets()


# ---------------------------------------------------------------------------
# Core Analysis Endpoint (Real Pipeline with Simulated URL Scraping)
# ---------------------------------------------------------------------------


@router.post("/reports/analyze", tags=["reports"])
def analyze_report(raw_body: Dict):
    """
    Core entrypoint for the Aegis MediaGuard real-time analysis pipeline.

    This endpoint takes a raw JSON payload containing a 'url' and 'description',
    extracts metadata from the URL via a scraper, and uses either generative AI
    (Gemini) or heuristic mapping to simulate a perceptual video fingerprint match.

    It then validates the payload schema, evaluates the distribution against the
    official rights catalog (checking platform, uploader, region, and license dates),
    and appends all actions to the immutable audit ledger.

    Returns:
        JSON response with the Verdict, severity score, and detailed rights evaluation flags.
    """
    import uuid
    import random
    from datetime import datetime
    from app.scraper import scrape_url_metadata, simulate_fingerprint_from_metadata
    from ingest.schema_guard import validate_report
    from ingest.normalizer import normalize_report
    from workers.sandbox import run_match_in_sandbox
    from rights.policy_engine import evaluate_rights
    from risk.verdicts import issue_verdict
    from ledger.audit import append_event
    from app.models import EvidenceEvent

    url = raw_body.get("url", "")
    description = raw_body.get("description", "")

    # 1. Scrape metadata from URL
    metadata = scrape_url_metadata(url)

    # 2. Simulate fingerprint
    simulated_fingerprint = simulate_fingerprint_from_metadata(metadata, description)
    if not simulated_fingerprint:
        simulated_fingerprint = "".join(
            [random.choice("0123456789abcdef") for _ in range(32)]
        )

    # Parse platform dynamically
    from urllib.parse import urlparse
    import re

    parsed_url = urlparse(url if url.startswith("http") else f"https://{url}")
    domain = parsed_url.netloc.replace("www.", "")
    domain_name = domain.split(".")[0] if "." in domain else domain

    # --- Normalize short/alias domains ---
    SHORT_DOMAIN_MAP = {
        "youtu.be": "youtube",
        "t.me":     "telegram",
        "fb.com":   "facebook",
        "fb.watch": "facebook",
        "ig.com":   "instagram",
    }
    if domain in SHORT_DOMAIN_MAP:
        domain_name = SHORT_DOMAIN_MAP[domain]
    elif domain_name == "youtu":
        domain_name = "youtube"
    elif domain_name == "t":
        domain_name = "telegram"

    if len(domain_name) < 2:
        domain_name = f"site_{domain_name}"

    from app.models import KNOWN_PLATFORMS
    platform = domain_name
    for p in KNOWN_PLATFORMS:
        if p in url.lower():
            platform = p
            break

    # --- Extract uploader handle from URL ---
    # Handles: youtube.com/@NBA, youtube.com/c/StarSports, youtube.com/user/nba
    uploader_handle = "anonymous"
    uploader_match = re.search(r"/@([a-zA-Z0-9_.-]+)", url)
    if uploader_match:
        uploader_handle = "@" + uploader_match.group(1).lower()
    else:
        # Try /c/ or /user/ style URLs
        channel_match = re.search(r"/(?:c|user|channel)/([a-zA-Z0-9_.-]+)", url)
        if channel_match:
            uploader_handle = "@" + channel_match.group(1).lower()

    # --- Smart geo-region inference ---
    # Rule 1: Official platform → use that platform's home region
    PLATFORM_REGION = {
        "hotstar":     "IN", "jiohotstar": "IN", "jiocinema": "IN",
        "sonyliv":     "IN", "fancode":    "IN",
        "skysports":   "GB", "btsport":    "GB", "nowtv": "GB",
        "foxcricket":  "AU", "kayo":       "AU",
        "dazn":        "US",
        "espn":        "US", "appletvplus":"US",
        "paramountplus":"US",
        "canal":       "FR",
        "dmax":        "DE",
    }
    geo_country = PLATFORM_REGION.get(platform, "US")

    # Rule 2: If we extracted an OFFICIAL uploader handle, allow ANY region
    # (e.g. @premierleague posts globally on YouTube)
    # We signal this by setting geo to a wildcard sentinel that the rights engine will respect.
    # We do this by checking the uploader against the matched asset's list after the fingerprint match.
    # For now, store the raw handle; the check_uploader function will evaluate it.

    # Rule 3: YouTube regional channels — infer region from channel name
    UPLOADER_REGION_HINTS = {
        "@starsportsindia": "IN",   "@iplt20": "IN",    "@jiocinema": "IN",
        "@sonyliv": "IN",           "@fancode": "IN",
        "@skysports": "GB",         "@btsport": "GB",
        "@foxcricket": "AU",        "@kayo": "AU",
        "@espn": "US",              "@nba": "US",        "@mls": "US",
        "@bundesliga": "DE",        "@laliga": "ES",     "@seriea": "IT",
        "@ligue1": "FR",            "@premierleague": "GB",
        "@uefa": "DE",              "@fifaworldcup": "US","@bwf": "MY",
        "@prokabaddi": "IN",        "@wimbledon": "GB",
        "@indiansuperleague": "IN", "@eredivisie": "NL",
        "@aleaguemen": "AU",
    }
    if uploader_handle in UPLOADER_REGION_HINTS:
        geo_country = UPLOADER_REGION_HINTS[uploader_handle]

    # Construct IncomingReport payload format
    report_data = {
        "report_id": f"RPT-LIVE-{str(uuid.uuid4())[:8]}",
        "discovered_url": url if url.startswith("http") else f"https://{url}",
        "platform": platform,
        "geo_country": geo_country,
        "detected_at": datetime.utcnow().isoformat(),
        "media_type": (
            "live_stream" if "live" in description.lower() else "highlight_clip"
        ),
        "claimant_org": "Hackathon Demo",
        "event_name": metadata.get("title", "Unknown Event")[:250] or "Unknown Event",
        "uploader_handle": uploader_handle,
        "extracted_fingerprint": simulated_fingerprint,
        "extracted_watermark": None,
        "screenshot_hash": None,
        "confidence_hint": 0.95,
    }

    try:
        append_event(EvidenceEvent.REPORT_RECEIVED, {"url": url})

        valid_report = validate_report(report_data)
        append_event(
            EvidenceEvent.SCHEMA_VALIDATED, {"report_id": valid_report.report_id}
        )

        norm_report = normalize_report(valid_report)
        append_event(
            EvidenceEvent.REPORT_NORMALIZED, {"report_id": norm_report.report_id}
        )

        match_result = run_match_in_sandbox(norm_report)
        append_event(
            EvidenceEvent.MATCH_COMPLETED,
            {"matched_asset_id": match_result.matched_asset_id},
        )

        rights_decision = None
        if match_result.matched_asset_id:
            from data.mock_assets import get_asset_by_id

            asset = get_asset_by_id(match_result.matched_asset_id)
            if asset:
                rights_decision = evaluate_rights(norm_report, asset)
                append_event(
                    EvidenceEvent.RIGHTS_DECIDED,
                    {"is_authorized": rights_decision.is_authorized},
                )

        verdict = issue_verdict(norm_report, match_result, rights_decision)

        append_event(
            EvidenceEvent.VERDICT_ISSUED,
            {"verdict": verdict.verdict, "severity": verdict.severity_score},
        )

        return {
            "report_id": verdict.report_id,
            "status": "success",
            "verdict": verdict.verdict.upper(),
            "risk_score": verdict.severity_score,
            "confidence": verdict.combined_confidence,
            "flags": verdict.reasoning,
            "message": "Analysis completed successfully",
            "matched_asset_id": verdict.matched_asset_id,
            "rights": rights_decision.model_dump() if rights_decision else None,
        }
    except Exception as e:
        print(f"Error in pipeline: {e}")
        append_event(EvidenceEvent.ANALYSIS_FAILED, {"error": str(e)})
        return {
            "report_id": "error",
            "status": "failed",
            "verdict": "ERROR",
            "risk_score": 0,
            "confidence": 0,
            "flags": [str(e)],
            "message": "Internal error",
        }


# ---------------------------------------------------------------------------
# Audit ledger
# ---------------------------------------------------------------------------


@router.get("/ledger", response_model=list[LedgerEntry], tags=["ledger"])
def fetch_ledger() -> list[LedgerEntry]:
    return get_ledger()


@router.get("/ledger/verify", response_model=LedgerVerifyResult, tags=["ledger"])
def verify_ledger() -> LedgerVerifyResult:
    return verify_chain()


# ---------------------------------------------------------------------------
# Agent (dummy safe version)
# ---------------------------------------------------------------------------


@router.get("/cases/{case_id}/agent-summary", tags=["agent"])
def agent_case_summary(case_id: str):
    return {
        "case_id": case_id,
        "summary": "This is a demo agent summary. Potential piracy detected based on keywords.",
        "recommended_action": "Investigate and take down if necessary",
    }
