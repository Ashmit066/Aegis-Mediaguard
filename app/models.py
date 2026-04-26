"""
app/models.py
Core Pydantic models for incoming reports, assets, verdicts, and evidence.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MediaType(str, Enum):
    live_stream = "live_stream"
    highlight_clip = "highlight_clip"
    full_match = "full_match"
    press_photo = "press_photo"
    podcast = "podcast"


class VerdictType(str, Enum):
    authorized = "authorized"
    suspected_infringement = "suspected_infringement"
    urgent_live_leak = "urgent_live_leak"
    manual_review = "manual_review"
    unknown_asset = "unknown_asset"
    invalid_report = "invalid_report"


class EvidenceEvent(str, Enum):
    REPORT_RECEIVED = "REPORT_RECEIVED"
    REPORT_NORMALIZED = "REPORT_NORMALIZED"
    SCHEMA_VALIDATED = "SCHEMA_VALIDATED"
    MATCH_COMPLETED = "MATCH_COMPLETED"
    WATERMARK_DETECTED = "WATERMARK_DETECTED"
    RIGHTS_DECIDED = "RIGHTS_DECIDED"
    VERDICT_ISSUED = "VERDICT_ISSUED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


KNOWN_PLATFORMS = {
    "youtube",
    "twitter",
    "instagram",
    "tiktok",
    "facebook",
    "twitch",
    "reddit",
    "vimeo",
    "dailymotion",
    "hotstar",
    "jiohotstar",
    "jiocinema",
    "sonyliv",
    "fancode",
    "skysports",
    "foxcricket",
    "paramount",
    "paramountplus",
    "unknown",
}

ISO3166_SAMPLE = {
    "US",
    "GB",
    "IN",
    "DE",
    "FR",
    "JP",
    "AU",
    "CA",
    "BR",
    "ZA",
    "NG",
    "MX",
    "KR",
    "IT",
    "ES",
    "NL",
    "PL",
    "RU",
    "CN",
    "SG",
    "UNKNOWN",
}


# ---------------------------------------------------------------------------
# Incoming telemetry report
# ---------------------------------------------------------------------------


class IncomingReport(BaseModel):
    """
    Telemetry payload submitted by a web crawler or monitoring agent.
    Extra fields are forbidden to prevent schema pollution.
    """

    model_config = {"extra": "forbid"}

    report_id: str = Field(..., min_length=8, max_length=64)
    discovered_url: str = Field(..., min_length=10, max_length=2048)
    platform: str = Field(..., min_length=2, max_length=64)
    geo_country: str = Field(..., min_length=2, max_length=8)
    detected_at: datetime
    media_type: MediaType
    claimant_org: str = Field(..., min_length=2, max_length=128)
    event_name: str = Field(..., min_length=2, max_length=256)
    uploader_handle: str = Field(..., max_length=128)
    extracted_fingerprint: str = Field(..., min_length=16, max_length=256)
    extracted_watermark: Optional[str] = Field(default=None, max_length=128)
    screenshot_hash: Optional[str] = Field(default=None, max_length=128)
    confidence_hint: float = Field(..., ge=0.0, le=1.0)

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("geo_country")
    @classmethod
    def normalize_geo(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in ISO3166_SAMPLE:
            return "UNKNOWN"
        return upper

    @field_validator("detected_at")
    @classmethod
    def no_future_timestamp(cls, v: datetime) -> datetime:
        if v > datetime.utcnow().replace(tzinfo=v.tzinfo):
            raise ValueError("detected_at cannot be in the future")
        return v


# ---------------------------------------------------------------------------
# Official asset catalog entry
# ---------------------------------------------------------------------------


class OfficialAsset(BaseModel):
    """
    Represents a rights-managed sports media asset in the catalog.
    """

    asset_id: str
    title: str
    event_name: str
    rights_holder: str
    media_type: MediaType
    canonical_fingerprint: str
    watermark_ids: list[str]
    authorized_uploaders: list[str] = Field(default_factory=list)
    authorized_platforms: list[str]
    authorized_regions: list[str]
    valid_from: datetime
    valid_to: datetime
    priority_level: int = Field(..., ge=1, le=10)


# ---------------------------------------------------------------------------
# Match result from the identify layer
# ---------------------------------------------------------------------------


class MatchResult(BaseModel):
    matched_asset_id: Optional[str] = None
    fingerprint_score: float = 0.0
    watermark_score: float = 0.0
    combined_confidence: float = 0.0
    watermark_detected: bool = False
    match_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rights decision from the policy engine
# ---------------------------------------------------------------------------


class RightsDecision(BaseModel):
    is_authorized: bool
    platform_ok: bool
    uploader_ok: bool = True
    region_ok: bool
    license_valid: bool
    reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Final analysis verdict
# ---------------------------------------------------------------------------


class AnalysisVerdict(BaseModel):
    report_id: str
    verdict: VerdictType
    severity_score: int = Field(..., ge=0, le=100)
    matched_asset_id: Optional[str] = None
    combined_confidence: float = 0.0
    rights_decision: Optional[RightsDecision] = None
    reasoning: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Audit ledger entry
# ---------------------------------------------------------------------------


class LedgerEntry(BaseModel):
    seq: int
    timestamp: datetime
    event_type: EvidenceEvent
    event_data: dict
    prev_hash: str
    entry_hash: str


class LedgerVerifyResult(BaseModel):
    valid: bool
    entry_count: int
    first_broken_seq: Optional[int] = None
    message: str


# ---------------------------------------------------------------------------
# Case store — persists analysis results for the agent layer
# ---------------------------------------------------------------------------


class StoredCase(BaseModel):
    """
    A completed analysis case, stored in memory after POST /reports/analyze.
    The verdict field is the authoritative output of the enforcement pipeline
    and is immutable once written.
    """

    case_id: str
    report_id: str
    platform: str
    geo_country: str
    media_type: str
    event_name: str
    uploader_handle: str
    discovered_url: str
    verdict: VerdictType
    severity_score: int
    matched_asset_id: Optional[str] = None
    combined_confidence: float
    watermark_detected: bool
    is_authorized: Optional[bool] = None
    rights_reasons: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    analyzed_at: datetime


# ---------------------------------------------------------------------------
# Agent summary response model
# ---------------------------------------------------------------------------


class AgentSummary(BaseModel):
    """
    Structured triage summary produced by the agent layer.
    This is advisory output only — it does not alter the stored verdict.
    """

    case_id: str
    verdict: str
    severity_score: int
    matched_asset_id: Optional[str] = None
    urgency_label: str
    summary: str
    key_evidence: list[str]
    recommended_action: str
    draft_takedown_notice: Optional[str] = None
    prior_related_case_count: int = 0
