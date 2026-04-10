"""
app/api.py
FastAPI router definitions for all Aegis MediaGuard endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models import (
    AnalysisVerdict,
    EvidenceEvent,
    IncomingReport,
    LedgerEntry,
    LedgerVerifyResult,
    OfficialAsset,
    VerdictType,
)
from data.mock_assets import get_all_assets, get_asset_by_id
from ingest.normalizer import normalize_report
from ingest.schema_guard import SchemaValidationError, validate_report
from ledger.audit import append_event, get_ledger, verify_chain
from rights.policy_engine import evaluate_rights
from risk.verdicts import issue_verdict
from workers.sandbox import run_match_in_sandbox

router = APIRouter()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", tags=["system"])
def health_check() -> dict:
    """Liveness probe — returns app name and version."""
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


# ---------------------------------------------------------------------------
# Asset catalog
# ---------------------------------------------------------------------------

@router.get("/assets", response_model=list[OfficialAsset], tags=["assets"])
def list_assets() -> list[OfficialAsset]:
    """Return all official sports media assets in the in-memory catalog."""
    return get_all_assets()


# ---------------------------------------------------------------------------
# Core analysis pipeline
# ---------------------------------------------------------------------------

@router.post("/reports/analyze", response_model=AnalysisVerdict, tags=["reports"])
def analyze_report(raw_body: dict) -> AnalysisVerdict:
    """
    Full analysis pipeline for an incoming telemetry report.

    Pipeline stages:
    1. Schema validation + normalization
    2. Fingerprint + watermark matching (subprocess-sandboxed)
    3. Rights evaluation
    4. Verdict issuance
    5. Ledger recording at each stage
    """
    # --- Stage 1: Schema validation ---
    try:
        report: IncomingReport = validate_report(raw_body)
    except SchemaValidationError as exc:
        append_event(
            EvidenceEvent.ANALYSIS_FAILED,
            {"reason": "schema_validation_failed", "errors": exc.errors},
        )
        raise HTTPException(status_code=422, detail={"errors": exc.errors})

    append_event(
        EvidenceEvent.REPORT_RECEIVED,
        {"report_id": report.report_id, "platform": report.platform},
    )
    append_event(EvidenceEvent.SCHEMA_VALIDATED, {"report_id": report.report_id})

    # --- Stage 1b: Normalize ---
    report = normalize_report(report)
    append_event(EvidenceEvent.REPORT_NORMALIZED, {"report_id": report.report_id})

    # --- Stage 2: Match (sandboxed subprocess) ---
    try:
        match = run_match_in_sandbox(report)
    except TimeoutError as exc:
        append_event(
            EvidenceEvent.ANALYSIS_FAILED,
            {"report_id": report.report_id, "reason": str(exc)},
        )
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        append_event(
            EvidenceEvent.ANALYSIS_FAILED,
            {"report_id": report.report_id, "reason": str(exc)},
        )
        raise HTTPException(status_code=500, detail=str(exc))

    append_event(
        EvidenceEvent.MATCH_COMPLETED,
        {
            "report_id": report.report_id,
            "matched_asset_id": match.matched_asset_id,
            "combined_confidence": match.combined_confidence,
        },
    )

    if match.watermark_detected:
        append_event(
            EvidenceEvent.WATERMARK_DETECTED,
            {
                "report_id": report.report_id,
                "watermark": report.extracted_watermark,
                "asset_id": match.matched_asset_id,
            },
        )

    # --- Stage 3: Rights evaluation ---
    rights = None
    if match.matched_asset_id:
        asset = get_asset_by_id(match.matched_asset_id)
        if asset:
            rights = evaluate_rights(report, asset)
            append_event(
                EvidenceEvent.RIGHTS_DECIDED,
                {
                    "report_id": report.report_id,
                    "is_authorized": rights.is_authorized,
                    "reasons": rights.reasons,
                },
            )

    # --- Stage 4: Verdict ---
    verdict = issue_verdict(report, match, rights)
    append_event(
        EvidenceEvent.VERDICT_ISSUED,
        {
            "report_id": report.report_id,
            "verdict": verdict.verdict.value,
            "severity_score": verdict.severity_score,
        },
    )

    return verdict


# ---------------------------------------------------------------------------
# Audit ledger
# ---------------------------------------------------------------------------

@router.get("/ledger", response_model=list[LedgerEntry], tags=["ledger"])
def fetch_ledger() -> list[LedgerEntry]:
    """Return all entries in the tamper-evident audit ledger."""
    return get_ledger()


@router.get("/ledger/verify", response_model=LedgerVerifyResult, tags=["ledger"])
def verify_ledger() -> LedgerVerifyResult:
    """
    Walk the ledger and verify every hash link.
    Returns a result indicating whether the chain is intact.
    """
    return verify_chain()
