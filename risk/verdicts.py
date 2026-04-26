"""
risk/verdicts.py
Converts scoring output and match/rights signals into a final AnalysisVerdict.
This is the decision layer — it maps signals to one of the defined VerdictType values.
"""

from __future__ import annotations

from app.config import settings
from app.models import (
    AnalysisVerdict,
    IncomingReport,
    MatchResult,
    MediaType,
    RightsDecision,
    VerdictType,
)
from risk.scoring import compute_severity


def issue_verdict(
    report: IncomingReport,
    match: MatchResult,
    rights: RightsDecision | None,
) -> AnalysisVerdict:
    """
    Apply verdict logic to produce a final, actionable decision.

    Verdict priority (top to bottom):
    1. unknown_asset      — no fingerprint match above threshold
    2. authorized         — match found AND rights are fully valid
    3. urgent_live_leak   — live stream, high confidence, rights fail
    4. suspected_infringement — rights fail, moderate-to-high confidence
    5. manual_review      — conflicting signals (e.g., watermark says yes, platform says no)

    Args:
        report: Normalized incoming report.
        match: Result from the matching layer.
        rights: Rights decision; None when no asset matched.

    Returns:
        AnalysisVerdict with verdict type, severity, and reasoning.
    """
    reasoning: list[str] = list(match.match_notes)
    severity = compute_severity(report, match, rights)

    # --- No asset match ---
    if match.matched_asset_id is None:
        reasoning.append("No asset in catalog exceeded the fingerprint threshold.")
        return AnalysisVerdict(
            report_id=report.report_id,
            verdict=VerdictType.unknown_asset,
            severity_score=severity,
            matched_asset_id=None,
            combined_confidence=match.combined_confidence,
            rights_decision=None,
            reasoning=reasoning,
        )

    # rights should not be None when a match exists, but guard anyway
    if rights is None:
        reasoning.append("Rights check was skipped — treating as manual review.")
        return AnalysisVerdict(
            report_id=report.report_id,
            verdict=VerdictType.manual_review,
            severity_score=severity,
            matched_asset_id=match.matched_asset_id,
            combined_confidence=match.combined_confidence,
            rights_decision=None,
            reasoning=reasoning,
        )

    reasoning.extend(rights.reasons)

    # --- Fully authorized ---
    if rights.is_authorized:
        reasoning.append("All rights checks passed — distribution is authorized.")
        return AnalysisVerdict(
            report_id=report.report_id,
            verdict=VerdictType.authorized,
            severity_score=severity,
            matched_asset_id=match.matched_asset_id,
            combined_confidence=match.combined_confidence,
            rights_decision=rights,
            reasoning=reasoning,
        )

    # Rights have failed beyond this point
    is_high_confidence = match.combined_confidence >= settings.high_confidence_threshold

    # --- Urgent live leak ---
    if (
        report.media_type == MediaType.live_stream
        and is_high_confidence
        and not rights.is_authorized
    ):
        reasoning.append(
            "URGENT: Live stream with high-confidence fingerprint on unauthorized "
            "platform or region — immediate takedown recommended."
        )
        return AnalysisVerdict(
            report_id=report.report_id,
            verdict=VerdictType.urgent_live_leak,
            severity_score=severity,
            matched_asset_id=match.matched_asset_id,
            combined_confidence=match.combined_confidence,
            rights_decision=rights,
            reasoning=reasoning,
        )

    # --- Conflicting signals → manual review ---
    # Watermark confirmed, but exactly only the platform is wrong (region & license fine)
    # and the watermark match is definitive — could be a legitimate cross-platform upload gone wrong
    only_platform_failed = (
        not rights.platform_ok and rights.region_ok and rights.license_valid
    )
    if (
        only_platform_failed
        and match.watermark_detected
        and not match.fingerprint_score == 1.0
    ):
        reasoning.append(
            "Watermark confirmed, but platform is unauthorized — "
            "human review needed to determine intent."
        )
        return AnalysisVerdict(
            report_id=report.report_id,
            verdict=VerdictType.manual_review,
            severity_score=severity,
            matched_asset_id=match.matched_asset_id,
            combined_confidence=match.combined_confidence,
            rights_decision=rights,
            reasoning=reasoning,
        )

    # --- Suspected infringement (catch-all for rights failure) ---
    reasoning.append("Rights check failed — flagged as suspected infringement.")
    return AnalysisVerdict(
        report_id=report.report_id,
        verdict=VerdictType.suspected_infringement,
        severity_score=severity,
        matched_asset_id=match.matched_asset_id,
        combined_confidence=match.combined_confidence,
        rights_decision=rights,
        reasoning=reasoning,
    )
