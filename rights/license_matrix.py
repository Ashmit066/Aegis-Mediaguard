"""
rights/license_matrix.py
Helpers for evaluating a report against an asset's license constraints.
Each function returns a (passed: bool, reason: str) tuple for structured output.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import IncomingReport, OfficialAsset


def check_platform(report: IncomingReport, asset: OfficialAsset) -> tuple[bool, str]:
    """
    Verify the report's platform is in the asset's authorized platform list.
    """
    authorized = [p.lower() for p in asset.authorized_platforms]
    if report.platform in authorized:
        return True, f"Platform '{report.platform}' is authorized"
    return (
        False,
        f"Platform '{report.platform}' is NOT authorized; "
        f"allowed: {asset.authorized_platforms}",
    )


def check_region(report: IncomingReport, asset: OfficialAsset) -> tuple[bool, str]:
    """
    Verify the report's geo_country is in the asset's authorized region list.
    """
    authorized = [r.upper() for r in asset.authorized_regions]
    if report.geo_country in authorized:
        return True, f"Region '{report.geo_country}' is authorized"
    return (
        False,
        f"Region '{report.geo_country}' is NOT authorized; "
        f"allowed: {asset.authorized_regions}",
    )


def check_license_dates(
    report: IncomingReport, asset: OfficialAsset
) -> tuple[bool, str]:
    """
    Check whether the detection timestamp falls within the asset's license window.
    """
    detected = report.detected_at
    # Make timezone-aware for comparison
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=timezone.utc)

    valid_from = asset.valid_from
    valid_to = asset.valid_to

    if detected < valid_from:
        return (
            False,
            f"Detection at {detected.isoformat()} is BEFORE license start "
            f"{valid_from.isoformat()}",
        )
    if detected > valid_to:
        return (
            False,
            f"Detection at {detected.isoformat()} is AFTER license expiry "
            f"{valid_to.isoformat()}",
        )
    return True, f"License valid: {valid_from.date()} → {valid_to.date()}"
