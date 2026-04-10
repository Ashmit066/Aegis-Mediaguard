"""
data/mock_assets.py
In-memory catalog of official sports media assets used during development.
Replace with a database-backed repository in production.
"""

from datetime import datetime, timezone
from typing import Optional

from app.models import MediaType, OfficialAsset

_CATALOG: list[OfficialAsset] = [
    OfficialAsset(
        asset_id="ASSET-001",
        title="Champions League Final 2024 Full Match",
        event_name="UEFA Champions League Final 2024",
        rights_holder="UEFA Media Rights",
        media_type=MediaType.full_match,
        canonical_fingerprint="a3f8b2c1d9e4f7a0b5c6d2e8f1a9b3c4",
        watermark_ids=["WM-UEFA-001", "WM-UEFA-002"],
        authorized_platforms=["youtube", "instagram"],
        authorized_regions=["GB", "DE", "FR", "IT", "ES"],
        valid_from=datetime(2024, 5, 1, tzinfo=timezone.utc),
        valid_to=datetime(2025, 5, 1, tzinfo=timezone.utc),
        priority_level=9,
    ),
    OfficialAsset(
        asset_id="ASSET-002",
        title="NBA Finals Game 7 Highlights",
        event_name="NBA Finals 2024",
        rights_holder="NBA Entertainment",
        media_type=MediaType.highlight_clip,
        canonical_fingerprint="d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
        watermark_ids=["WM-NBA-010", "WM-NBA-011"],
        authorized_platforms=["youtube", "twitter", "facebook"],
        authorized_regions=["US", "CA"],
        valid_from=datetime(2024, 6, 1, tzinfo=timezone.utc),
        valid_to=datetime(2025, 6, 1, tzinfo=timezone.utc),
        priority_level=8,
    ),
    OfficialAsset(
        asset_id="ASSET-003",
        title="IPL 2024 Live Stream — MI vs CSK",
        event_name="IPL 2024",
        rights_holder="Star Sports",
        media_type=MediaType.live_stream,
        canonical_fingerprint="f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5",
        watermark_ids=["WM-IPL-200"],
        authorized_platforms=["youtube"],
        authorized_regions=["IN"],
        valid_from=datetime(2024, 3, 22, tzinfo=timezone.utc),
        valid_to=datetime(2024, 5, 26, tzinfo=timezone.utc),
        priority_level=10,
    ),
    OfficialAsset(
        asset_id="ASSET-004",
        title="Wimbledon 2024 Men's Final Press Photos Pack",
        event_name="Wimbledon 2024",
        rights_holder="AELTC Media",
        media_type=MediaType.press_photo,
        canonical_fingerprint="1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
        watermark_ids=["WM-WIMB-050"],
        authorized_platforms=["twitter", "instagram"],
        authorized_regions=["GB", "US", "AU"],
        valid_from=datetime(2024, 7, 1, tzinfo=timezone.utc),
        valid_to=datetime(2025, 7, 1, tzinfo=timezone.utc),
        priority_level=6,
    ),
    OfficialAsset(
        asset_id="ASSET-005",
        title="FIFA World Cup 2022 Classic Match Archive",
        event_name="FIFA World Cup 2022",
        rights_holder="FIFA TV",
        media_type=MediaType.full_match,
        canonical_fingerprint="9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c",
        watermark_ids=["WM-FIFA-300", "WM-FIFA-301"],
        authorized_platforms=["youtube", "facebook", "vimeo"],
        authorized_regions=["US", "GB", "DE", "FR", "BR", "JP", "AU"],
        valid_from=datetime(2023, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2024, 1, 1, tzinfo=timezone.utc),  # EXPIRED
        priority_level=7,
    ),
]

# Keyed by asset_id for O(1) lookup
_CATALOG_INDEX: dict[str, OfficialAsset] = {a.asset_id: a for a in _CATALOG}


def get_all_assets() -> list[OfficialAsset]:
    """Return the full asset catalog."""
    return list(_CATALOG)


def get_asset_by_id(asset_id: str) -> Optional[OfficialAsset]:
    """Fetch a single asset by its identifier."""
    return _CATALOG_INDEX.get(asset_id)
