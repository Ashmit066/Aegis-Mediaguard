"""
identify/watermark.py
Watermark evidence verification against the official asset catalog.
A watermark match provides a strong, secondary signal of content identity.
"""

from __future__ import annotations

from typing import Optional

from app.models import OfficialAsset
from app.config import settings


def check_watermark(
    extracted_watermark: Optional[str],
    asset: OfficialAsset,
) -> tuple[bool, float]:
    """
    Check whether the extracted watermark ID appears in the asset's
    official watermark list.

    Args:
        extracted_watermark: Watermark string pulled from the discovered media.
        asset: The matched official asset to check against.

    Returns:
        A tuple of (detected: bool, confidence_boost: float).
        If detected, the boost is settings.watermark_confidence_boost; else 0.0.
    """
    if not extracted_watermark:
        return False, 0.0

    normalized = extracted_watermark.strip().upper()
    detected = normalized in [wm.upper() for wm in asset.watermark_ids]
    boost = settings.watermark_confidence_boost if detected else 0.0
    return detected, boost
