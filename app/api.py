"""
app/api.py
FastAPI router definitions for all Aegis MediaGuard endpoints.

Changes from v1:
- Added _CASE_STORE (in-memory dict) that persists every analysis result.
- POST /reports/analyze now writes a case entry after issuing the verdict.
- Added GET /cases/{case_id}/agent-summary (new agentic triage endpoint).
- All original endpoints are unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models import (
    AgentSummary,
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
# In-memory case store
# Keyed by report_id (== case_id).  Each value is a raw dict containing the
# objects produced at each pipeline stage so the agent layer can read them
# without re-running any logic.
# ---------------------------------------------------------------------------
_CASE_STORE: dict[str, dict] = {}


def _persist_case(
    report: IncomingReport,
    match,
    rights,
    verdict: AnalysisVerdict,
    asset_title: str = "Unknown",
    rights_holder: str = "Unknown",
) -> None:
    """Write a completed analysis to the case store.  Never raises."""
    _CASE_STORE[verdict.report_id] = {
        "report": report,
        "match": match,
        "rights_decision": rights,
        "verdict": verdict,
        "asset_title": asset_title,
        "rights_holder": rights_holder,
    }


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
    6. Case persistence (new) -- stores result for agent retrieval
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
    asset_title = "Unknown"
    rights_holder_name = "Unknown"
    if match.matched_asset_id:
        asset = get_asset_by_id(match.matched_asset_id)
        if asset:
            rights = evaluate_rights(report, asset)
            asset_title = asset.title
            rights_holder_name = asset.rights_holder
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

    # --- Stage 5: Persist case for agent retrieval ---
    _persist_case(report, match, rights, verdict, asset_title, rights_holder_name)

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


# ---------------------------------------------------------------------------
# Agent triage endpoint
# ---------------------------------------------------------------------------

@router.get("/cases/{case_id}/agent-summary", response_model=AgentSummary, tags=["agent"])
def agent_case_summary(case_id: str) -> AgentSummary:
    """
    Read-only agentic triage summary for an analyzed case.

    This endpoint:
    - Reads the stored case from the enforcement pipeline's case store.
    - Passes structured evidence through policy-gated agent tools.
    - Returns an advisory triage summary including urgency, recommended
      action, and a draft takedown notice where appropriate.
    - Never modifies the stored verdict, rights data, or audit ledger.

    Args:
        case_id: The report_id returned by POST /reports/analyze.

    Returns:
        AgentSummary -- advisory output, not authoritative.

    Raises:
        404: If the case_id is not found in the case store.
        403: If any internal agent action violates policy (defensive).
    """
    if case_id not in _CASE_STORE:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found. Submit the report first via POST /reports/analyze.",
        )

    from agent.orchestrator import PolicyViolationError, run_case_summary

    try:
        summary_dict = run_case_summary(case_id)
    except PolicyViolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return AgentSummary(**summary_dict)