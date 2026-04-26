"""
rights/policy_engine.py
Aggregates individual license checks into a structured RightsDecision.
"""

from __future__ import annotations

from app.models import IncomingReport, OfficialAsset, RightsDecision
from rights.license_matrix import (
    check_license_dates,
    check_platform,
    check_region,
    check_uploader,
)


def evaluate_rights(report: IncomingReport, asset: OfficialAsset) -> RightsDecision:
    """
    Run all license checks for the given report + asset pair and produce
    a structured RightsDecision with individual check results and reasons.

    Args:
        report: Normalized incoming telemetry report.
        asset: The matched official asset from the catalog.

    Returns:
        RightsDecision with is_authorized and detailed reasons.
    """
    platform_ok, platform_reason = check_platform(report, asset)
    uploader_ok, uploader_reason = check_uploader(report, asset)
    region_ok, region_reason = check_region(report, asset)
    license_valid, license_reason = check_license_dates(report, asset)

    is_authorized = platform_ok and uploader_ok and region_ok and license_valid

    return RightsDecision(
        is_authorized=is_authorized,
        platform_ok=platform_ok,
        uploader_ok=uploader_ok,
        region_ok=region_ok,
        license_valid=license_valid,
        reasons=[platform_reason, uploader_reason, region_reason, license_reason],
    )
