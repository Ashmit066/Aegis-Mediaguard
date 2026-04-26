"""
rights/license_matrix.py
Helpers for evaluating a report against an asset's license constraints.
Each function returns a (passed: bool, reason: str) tuple for structured output.
"""

from __future__ import annotations

from datetime import timezone

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


def check_uploader(report: IncomingReport, asset: OfficialAsset) -> tuple[bool, str]:
    """
    Verify the report's uploader is authorized if the platform relies on UGC (user-generated content).
    """
    # Direct broadcasters are intrinsically authorized
    UGC_PLATFORMS = [
        "youtube",
        "twitter",
        "instagram",
        "facebook",
        "tiktok",
        "reddit",
        "vimeo",
        "dailymotion",
        "telegram",
    ]
    if report.platform not in UGC_PLATFORMS:
        return True, f"Direct broadcaster '{report.platform}' assumes uploader trust"

    authorized = [u.lower() for u in asset.authorized_uploaders]
    if not authorized:
        return True, "No specific uploader restrictions defined"

    handle = (report.uploader_handle or "anonymous").lower()
    if handle in authorized:
        return True, f"Uploader '{report.uploader_handle}' is an official account"

    return (
        False,
        f"Uploader '{report.uploader_handle}' is NOT authorized; "
        f"official accounts: {asset.authorized_uploaders}",
    )


def check_region(report: IncomingReport, asset: OfficialAsset) -> tuple[bool, str]:
    """
    Verify the report's geo_country is in the asset's authorized region list.
    Official uploaders on UGC platforms (e.g. @NBA on YouTube) broadcast globally —
    so if the uploader is verified official, we skip the region restriction.
    """
    # If uploader is official, bypass geo restriction (they broadcast globally)
    if report.uploader_handle and report.uploader_handle != "anonymous":
        authorized_uploaders = [u.lower() for u in asset.authorized_uploaders]
        if report.uploader_handle.lower() in authorized_uploaders:
            return True, f"Official uploader '{report.uploader_handle}' — geo restriction bypassed (global broadcast)"

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
