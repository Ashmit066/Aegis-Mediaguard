"""
ingest/normalizer.py
Post-validation normalization passes on a validated IncomingReport.
Ensures consistent casing, trims whitespace, and makes downstream
processing deterministic.
"""

from __future__ import annotations

from app.models import IncomingReport


def normalize_report(report: IncomingReport) -> IncomingReport:
    """
    Apply normalization rules to an already-validated report.

    Pydantic validators already handle platform and geo_country normalization
    during model construction, so this layer focuses on string hygiene for
    free-form fields and ensures the fingerprint is lowercased hex.

    Args:
        report: A validated IncomingReport instance.

    Returns:
        A new IncomingReport instance with normalized fields.
    """
    data = report.model_dump()

    # Normalize fingerprint to lowercase — keeps Hamming distance consistent
    data["extracted_fingerprint"] = data["extracted_fingerprint"].strip().lower()

    # Normalize optional watermark
    if data.get("extracted_watermark"):
        data["extracted_watermark"] = data["extracted_watermark"].strip().upper()

    # Trim uploader handle
    data["uploader_handle"] = data["uploader_handle"].strip()

    # Trim event_name and claimant_org
    data["event_name"] = data["event_name"].strip()
    data["claimant_org"] = data["claimant_org"].strip()

    return IncomingReport.model_validate(data)
