"""
identify/matcher.py
Orchestrates fingerprint and watermark comparison across the entire asset catalog.
Returns the best-matching asset or signals that no match was found.
"""

from __future__ import annotations

from app.config import settings
from app.models import IncomingReport, MatchResult, OfficialAsset
from data.mock_assets import get_all_assets
from identify.fingerprint import fingerprint_similarity
from identify.watermark import check_watermark


def match_report(report: IncomingReport) -> MatchResult:
    """
    Compare an incoming report against every asset in the catalog.

    Strategy:
    1. Compute fingerprint similarity for every asset.
    2. Select the asset with the highest fingerprint score that exceeds the
       configured threshold.
    3. Apply watermark check against the best candidate.
    4. Combine scores; watermark boost can push confidence above the threshold.

    Args:
        report: A validated, normalized IncomingReport.

    Returns:
        A MatchResult. If no asset exceeds the threshold, matched_asset_id
        will be None.
    """
    catalog: list[OfficialAsset] = get_all_assets()
    notes: list[str] = []

    best_asset: OfficialAsset | None = None
    best_fp_score: float = 0.0

    for asset in catalog:
        score = fingerprint_similarity(
            report.extracted_fingerprint,
            asset.canonical_fingerprint,
        )
        if score > best_fp_score:
            best_fp_score = score
            best_asset = asset

    if best_asset is None or best_fp_score < settings.fingerprint_match_threshold:
        notes.append(
            f"Best fingerprint score {best_fp_score:.3f} is below "
            f"threshold {settings.fingerprint_match_threshold}"
        )
        return MatchResult(
            fingerprint_score=round(best_fp_score, 4),
            match_notes=notes,
        )

    notes.append(
        f"Fingerprint matched asset {best_asset.asset_id} "
        f"with score {best_fp_score:.3f}"
    )

    wm_detected, wm_boost = check_watermark(report.extracted_watermark, best_asset)
    watermark_score = wm_boost

    if wm_detected:
        notes.append(
            f"Watermark '{report.extracted_watermark}' confirmed in asset "
            f"{best_asset.asset_id}"
        )
    else:
        notes.append("No matching watermark found")

    combined = min(1.0, best_fp_score + wm_boost)

    return MatchResult(
        matched_asset_id=best_asset.asset_id,
        fingerprint_score=round(best_fp_score, 4),
        watermark_score=round(watermark_score, 4),
        combined_confidence=round(combined, 4),
        watermark_detected=wm_detected,
        match_notes=notes,
    )
