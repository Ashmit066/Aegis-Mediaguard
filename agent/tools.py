"""
agent/tools.py
Read-only tools that the agent orchestrator may call.

Every function here:
- Reads from the existing enforcement data stores (case store, asset catalog,
  ledger).  It never writes to them.
- Returns plain Python dicts or lists — no side effects.
- Raises ValueError for unknown identifiers so the orchestrator can handle
  them gracefully.

These functions are the only sanctioned data access path for the agent layer.
"""

from __future__ import annotations

from data.mock_assets import get_asset_by_id, get_all_assets


# The case store is imported lazily inside functions to avoid a circular import
# at module load time (api.py imports agent/orchestrator which imports tools).
def _cases() -> dict:
    from app.api import _CASE_STORE  # noqa: PLC0415
    return _CASE_STORE


def get_case_evidence(case_id: str) -> dict:
    """
    Return a flat evidence dict for a stored case, ready for agent consumption.

    Pulls from the deterministic pipeline outputs stored at analysis time.
    Does not re-run any analysis.

    Args:
        case_id: The report_id used when the case was analyzed.

    Returns:
        A flat dict of evidence fields.

    Raises:
        ValueError: If no case with this ID exists.
    """
    case = _cases().get(case_id)
    if case is None:
        raise ValueError(f"Case '{case_id}' not found in case store.")

    verdict = case["verdict"]
    rights = case.get("rights_decision") or {}

    return {
        "case_id": case_id,
        "verdict": verdict.verdict.value,
        "severity_score": verdict.severity_score,
        "combined_confidence": verdict.combined_confidence,
        "matched_asset_id": verdict.matched_asset_id,
        "reasoning": verdict.reasoning,
        "platform": case["report"].platform,
        "geo_country": case["report"].geo_country,
        "uploader_handle": case["report"].uploader_handle,
        "discovered_url": case["report"].discovered_url,
        "event_name": case["report"].event_name,
        "media_type": case["report"].media_type.value,
        "watermark_detected": case["match"].watermark_detected,
        "fingerprint_score": case["match"].fingerprint_score,
        "rights_reasons": rights.reasons if hasattr(rights, "reasons") else [],
        "is_authorized": rights.is_authorized if hasattr(rights, "is_authorized") else None,
        "asset_title": case.get("asset_title", "Unknown"),
        "rights_holder": case.get("rights_holder", "Unknown"),
    }


def get_asset_details(asset_id: str) -> dict:
    """
    Return public catalog details for an official asset.

    Args:
        asset_id: The asset_id from the catalog.

    Returns:
        A dict of asset fields.

    Raises:
        ValueError: If the asset_id is not in the catalog.
    """
    asset = get_asset_by_id(asset_id)
    if asset is None:
        raise ValueError(f"Asset '{asset_id}' not found in catalog.")
    return asset.model_dump(mode="json")


def get_rights_explanation(case_id: str) -> dict:
    """
    Return a structured rights explanation for a case.

    Formats the rights decision reasons from the enforcement pipeline into
    a human-readable breakdown without re-running any logic.

    Args:
        case_id: The report_id of the analyzed case.

    Returns:
        Dict with is_authorized, platform_ok, region_ok, license_valid, reasons.

    Raises:
        ValueError: If the case is not found or has no rights decision.
    """
    case = _cases().get(case_id)
    if case is None:
        raise ValueError(f"Case '{case_id}' not found.")

    rights = case.get("rights_decision")
    if rights is None:
        return {
            "case_id": case_id,
            "explanation": "No rights decision was recorded — the media did not match any cataloged asset.",
            "is_authorized": None,
            "platform_ok": None,
            "region_ok": None,
            "license_valid": None,
            "reasons": [],
        }

    return {
        "case_id": case_id,
        "is_authorized": rights.is_authorized,
        "platform_ok": rights.platform_ok,
        "region_ok": rights.region_ok,
        "license_valid": rights.license_valid,
        "reasons": rights.reasons,
        "explanation": (
            "All rights checks passed." if rights.is_authorized
            else "One or more rights checks failed. See reasons for details."
        ),
    }


def get_prior_related_cases(asset_id: str) -> list[dict]:
    """
    Return a list of prior analyzed cases involving the same asset.

    Useful for the agent to identify repeat infringers or escalating patterns.

    Args:
        asset_id: The asset to search for across stored cases.

    Returns:
        List of dicts with case_id, verdict, platform, severity_score, analyzed_at.
    """
    related = []
    for case_id, case in _cases().items():
        if case["verdict"].matched_asset_id == asset_id:
            related.append(
                {
                    "case_id": case_id,
                    "verdict": case["verdict"].verdict.value,
                    "platform": case["report"].platform,
                    "severity_score": case["verdict"].severity_score,
                    "analyzed_at": case["verdict"].analyzed_at.isoformat(),
                }
            )
    return related


def draft_takedown_notice(case_id: str) -> str | None:
    """
    Generate a draft takedown notice for a case.

    This is a convenience wrapper — it retrieves evidence and delegates to
    the LLM stub's draft generation so the orchestrator can call it as a
    named tool without knowing the evidence assembly details.

    Args:
        case_id: The report_id of the analyzed case.

    Returns:
        A draft notice string, or None if the verdict does not warrant one.

    Raises:
        ValueError: If the case is not found.
    """
    from agent.llm_stub import _draft_takedown  # noqa: PLC0415

    evidence = get_case_evidence(case_id)
    rights = _cases().get(case_id, {}).get("rights_decision")
    rights_reasons = rights.reasons if rights and hasattr(rights, "reasons") else []

    return _draft_takedown(
        verdict=evidence["verdict"],
        asset_title=evidence["asset_title"],
        url=evidence["discovered_url"],
        platform=evidence["platform"],
        uploader=evidence["uploader_handle"],
        rights_holder=evidence["rights_holder"],
        event_name=evidence["event_name"],
        watermark=evidence["watermark_detected"],
        confidence=evidence["combined_confidence"],
        rights_reasons=rights_reasons,
    )