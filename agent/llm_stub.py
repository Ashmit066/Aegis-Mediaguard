"""
agent/llm_stub.py
A deterministic, key-free LLM interface that generates structured triage output
directly from structured evidence — no external API calls required.

The interface is intentionally thin so it can be replaced with a real Claude /
OpenAI / OpenRouter call later by swapping this module.  The caller always
receives the same shape of response regardless of which backend is in use.

Swap guide (when you are ready for a real LLM):
    1. Replace `_call_stub` with a function that POSTs to the Claude Messages API.
    2. Keep the `generate` entry point and its return type identical.
    3. All existing callers continue to work without modification.
"""

from __future__ import annotations

from app.models import VerdictType


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate(prompt_key: str, evidence: dict) -> dict:
    """
    Generate a structured triage response from labelled evidence.

    Args:
        prompt_key: Identifies which generation task is being requested.
                    Currently only "case_summary" is used.
        evidence:   A dict of structured facts produced by the enforcement
                    pipeline (never raw untrusted text from the internet).

    Returns:
        A dict whose keys match the AgentSummary response model fields.
    """
    if prompt_key == "case_summary":
        return _generate_case_summary(evidence)
    raise ValueError(f"Unknown prompt_key: {prompt_key!r}")


# ---------------------------------------------------------------------------
# Internal generation logic
# ---------------------------------------------------------------------------

def _generate_case_summary(ev: dict) -> dict:
    """
    Produce a case summary deterministically from structured evidence fields.

    This function encodes the same reasoning a human analyst would apply:
    - Severity drives urgency.
    - Verdict type drives recommended action.
    - Rights failure reasons inform the summary text.
    - Watermark confirmation strengthens the draft notice.
    """
    verdict: str = ev.get("verdict", "unknown_asset")
    severity: int = ev.get("severity_score", 0)
    asset_title: str = ev.get("asset_title", "Unknown asset")
    platform: str = ev.get("platform", "unknown platform")
    geo: str = ev.get("geo_country", "unknown region")
    uploader: str = ev.get("uploader_handle", "unknown uploader")
    confidence: float = ev.get("combined_confidence", 0.0)
    watermark: bool = ev.get("watermark_detected", False)
    rights_reasons: list[str] = ev.get("rights_reasons", [])
    url: str = ev.get("discovered_url", "")
    event_name: str = ev.get("event_name", "unknown event")
    rights_holder: str = ev.get("rights_holder", "Unknown rights holder")

    # --- Urgency label ---
    if severity >= 85:
        urgency = "CRITICAL"
    elif severity >= 60:
        urgency = "HIGH"
    elif severity >= 35:
        urgency = "MEDIUM"
    else:
        urgency = "LOW"

    # --- Short summary ---
    summary = _build_summary(verdict, asset_title, platform, geo, confidence, severity)

    # --- Key evidence points ---
    evidence_points = _build_evidence_points(
        verdict, confidence, watermark, rights_reasons, platform, geo
    )

    # --- Recommended action ---
    recommended_action = _recommend_action(verdict, severity)

    # --- Draft takedown notice ---
    draft_notice = _draft_takedown(
        verdict, asset_title, url, platform, uploader, rights_holder, event_name,
        watermark, confidence, rights_reasons
    )

    return {
        "summary": summary,
        "key_evidence": evidence_points,
        "urgency_label": urgency,
        "recommended_action": recommended_action,
        "draft_takedown_notice": draft_notice,
    }


def _build_summary(
    verdict: str,
    asset_title: str,
    platform: str,
    geo: str,
    confidence: float,
    severity: int,
) -> str:
    pct = round(confidence * 100)
    if verdict == VerdictType.urgent_live_leak:
        return (
            f"URGENT: A live stream of '{asset_title}' is being distributed without "
            f"authorization on {platform} from region {geo}. Fingerprint confidence "
            f"is {pct}% and severity is {severity}/100. Immediate action required."
        )
    if verdict == VerdictType.suspected_infringement:
        return (
            f"Suspected unauthorized distribution of '{asset_title}' detected on "
            f"{platform} (region: {geo}). Fingerprint match confidence: {pct}%. "
            f"Severity score: {severity}/100."
        )
    if verdict == VerdictType.manual_review:
        return (
            f"Conflicting signals detected for '{asset_title}' on {platform}. "
            f"Human review is recommended before escalation. "
            f"Confidence: {pct}%, severity: {severity}/100."
        )
    if verdict == VerdictType.authorized:
        return (
            f"Distribution of '{asset_title}' on {platform} ({geo}) appears "
            f"authorized. No action required. Confidence: {pct}%."
        )
    if verdict == VerdictType.unknown_asset:
        return (
            f"The discovered media on {platform} ({geo}) could not be matched to any "
            f"cataloged asset. Fingerprint confidence below threshold. "
            f"Severity: {severity}/100."
        )
    return f"Analysis complete for detected media on {platform}. Verdict: {verdict}."


def _build_evidence_points(
    verdict: str,
    confidence: float,
    watermark: bool,
    rights_reasons: list[str],
    platform: str,
    geo: str,
) -> list[str]:
    points: list[str] = []
    pct = round(confidence * 100)

    if confidence > 0:
        strength = "strong" if confidence >= 0.8 else "moderate"
        points.append(f"Fingerprint match: {strength} ({pct}% confidence).")
    else:
        points.append("No fingerprint match found in the official catalog.")

    if watermark:
        points.append("Official watermark ID confirmed in the media — high-fidelity identity signal.")

    for reason in rights_reasons:
        if "NOT authorized" in reason or "AFTER" in reason or "BEFORE" in reason:
            points.append(f"Rights violation: {reason}")

    if verdict == VerdictType.urgent_live_leak:
        points.append("Media type is live stream — unauthorized live distribution is highest priority.")

    if verdict == VerdictType.unknown_asset:
        points.append("Asset identity unconfirmed — monitor for repeat patterns from this source.")

    return points


def _recommend_action(verdict: str, severity: int) -> str:
    if verdict == VerdictType.urgent_live_leak:
        return (
            "Escalate immediately to the rights holder and platform trust & safety team. "
            "Issue takedown notice within the hour. Log all evidence before proceeding."
        )
    if verdict == VerdictType.suspected_infringement:
        return (
            "Issue a formal DMCA takedown notice to the platform. "
            "Preserve screenshot and fingerprint evidence. "
            "Notify the rights holder within 24 hours."
        )
    if verdict == VerdictType.manual_review:
        return (
            "Assign to a human analyst for review. Do not issue a takedown notice "
            "until the conflict between platform authorization and other signals is resolved."
        )
    if verdict == VerdictType.authorized:
        return "No action required. File for record-keeping."
    if verdict == VerdictType.unknown_asset:
        return (
            "Flag the source URL for monitoring. If the same uploader reappears with "
            "a matched fingerprint, escalate at that time."
        )
    return "Review the evidence and consult the rights holder."


def _draft_takedown(
    verdict: str,
    asset_title: str,
    url: str,
    platform: str,
    uploader: str,
    rights_holder: str,
    event_name: str,
    watermark: bool,
    confidence: float,
    rights_reasons: list[str],
) -> str | None:
    """Return a draft takedown notice for actionable verdicts; None otherwise."""
    if verdict not in (
        VerdictType.urgent_live_leak,
        VerdictType.suspected_infringement,
    ):
        return None

    wm_line = (
        "\nAdditionally, our system detected an official embedded watermark in the "
        "infringing content, which provides conclusive evidence of unauthorized copying."
        if watermark
        else ""
    )

    violations = "\n".join(f"  - {r}" for r in rights_reasons if "NOT authorized" in r or "AFTER" in r)
    violations_block = f"\nSpecific violations identified:\n{violations}" if violations else ""

    return (
        f"DRAFT TAKEDOWN NOTICE\n"
        f"{'=' * 60}\n"
        f"To: {platform.capitalize()} Trust & Safety / Content Policy Team\n"
        f"Re: Unauthorized distribution of copyrighted sports media\n\n"
        f"Dear {platform.capitalize()} Content Policy Team,\n\n"
        f"{rights_holder} is the exclusive rights holder for the official sports "
        f"media asset titled '{asset_title}', associated with the event '{event_name}'.\n\n"
        f"We have detected what appears to be unauthorized distribution of this "
        f"copyrighted material at the following URL:\n\n"
        f"  {url}\n\n"
        f"Uploader handle: {uploader}\n"
        f"Fingerprint match confidence: {round(confidence * 100)}%"
        f"{wm_line}"
        f"{violations_block}\n\n"
        f"We request that you:\n"
        f"  1. Immediately remove or disable access to the content at the above URL.\n"
        f"  2. Preserve all associated logs for potential legal proceedings.\n"
        f"  3. Notify us of the action taken within 48 hours.\n\n"
        f"This notice is generated by the Aegis MediaGuard rights intelligence system "
        f"and requires human review and authorization before formal submission.\n\n"
        f"[DRAFT — NOT YET AUTHORIZED FOR SUBMISSION]\n"
        f"{'=' * 60}"
    )