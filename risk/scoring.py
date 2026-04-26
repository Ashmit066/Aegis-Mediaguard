"""
risk/scoring.py
Computes a severity score from 0 to 100 based on match confidence,
rights decision, media type, and watermark evidence.
"""

from __future__ import annotations

from app.models import IncomingReport, MatchResult, MediaType, RightsDecision


def compute_severity(
    report: IncomingReport,
    match: MatchResult,
    rights: RightsDecision | None,
) -> int:
    """
    Assign an integer severity score from 0 (no risk) to 100 (critical).

    Scoring logic:
    - Base score: combined_confidence × 60
    - Rights violation: +25
    - Live stream media type: +10
    - Watermark confirmed: +5
    - Platform failure only (softer): no extra
    - No match: score stays low

    Args:
        report: Normalized incoming report.
        match: Result from the matching layer.
        rights: Rights decision (None if asset was not found).

    Returns:
        Integer severity in [0, 100].
    """
    score: float = 0.0

    # Base from fingerprint confidence — only meaningful when rights are violated
    # For authorized content, keep score low regardless of confidence
    if rights is not None and rights.is_authorized:
        # Low base: authorized distribution is expected; watermark is a good sign
        score += match.combined_confidence * 10
        return min(100, round(score))

    # Rights check failed or no asset found
    score += match.combined_confidence * 55

    if rights is not None and not rights.is_authorized:
        score += 25

        # Expired license is more severe than geo/platform mismatch alone
        if not rights.license_valid:
            score += 5

    # Live streams require urgent treatment
    if report.media_type == MediaType.live_stream:
        score += 10

    # Watermark confirmation is strong evidence of real content — increases severity
    if match.watermark_detected and (rights is None or not rights.is_authorized):
        score += 5

    return min(100, round(score))
