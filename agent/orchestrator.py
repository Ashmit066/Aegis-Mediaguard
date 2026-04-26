"""
agent/orchestrator.py
Orchestrates the agentic triage flow for a single case.

The orchestrator is intentionally thin:
  1. Check policy before every tool call.
  2. Gather structured evidence via approved tools only.
  3. Delegate text generation to the LLM stub (or real LLM later).
  4. Never touch the enforcement pipeline data directly.

The verdict stored in the case store is treated as immutable throughout.
"""

from __future__ import annotations

from agent.llm_stub import generate
from agent.policy import AgentAction, check_policy
from agent.tools import (
    get_asset_details,
    get_case_evidence,
    get_rights_explanation,
    get_prior_related_cases,
)


class PolicyViolationError(Exception):
    """Raised when the orchestrator attempts a blocked action."""


def _require_allowed(action: AgentAction) -> None:
    """Assert that an action is permitted; raise PolicyViolationError if not."""
    result = check_policy(action)
    if not result.allowed:
        raise PolicyViolationError(
            f"Blocked action '{action.value}': {result.reason}"
        )


def run_case_summary(case_id: str) -> dict:
    """
    Produce a complete agent triage summary for an analyzed case.

    Steps:
    1. Policy check — SUMMARIZE_CASE is allowed.
    2. Gather case evidence via GET_CASE_EVIDENCE tool.
    3. Enrich with asset details if a match exists.
    4. Gather related cases for context.
    5. Pass assembled evidence to the LLM stub for summary generation.
    6. Return the structured summary dict.

    Args:
        case_id: The report_id of the case to summarize.

    Returns:
        Dict matching the AgentSummary response model fields.

    Raises:
        PolicyViolationError: If any attempted action is blocked (defensive).
        ValueError: If the case_id is not found.
    """
    _require_allowed(AgentAction.SUMMARIZE_CASE)
    _require_allowed(AgentAction.GET_CASE_EVIDENCE)

    # Gather core evidence
    evidence = get_case_evidence(case_id)

    # Enrich with asset catalog details when a match exists
    asset_id = evidence.get("matched_asset_id")
    if asset_id:
        _require_allowed(AgentAction.GET_ASSET_DETAILS)
        try:
            asset = get_asset_details(asset_id)
            evidence["asset_title"] = asset.get("title", evidence.get("asset_title", "Unknown"))
            evidence["rights_holder"] = asset.get("rights_holder", evidence.get("rights_holder", "Unknown"))
            evidence["authorized_platforms"] = asset.get("authorized_platforms", [])
            evidence["authorized_regions"] = asset.get("authorized_regions", [])
        except ValueError:
            pass  # asset details unavailable — continue with what we have

    # Enrich rights explanation
    _require_allowed(AgentAction.GET_RIGHTS_EXPLANATION)
    try:
        rights_exp = get_rights_explanation(case_id)
        evidence["rights_explanation"] = rights_exp.get("explanation", "")
        if not evidence.get("rights_reasons"):
            evidence["rights_reasons"] = rights_exp.get("reasons", [])
    except ValueError:
        pass

    # Gather prior related cases for pattern context
    _require_allowed(AgentAction.GET_PRIOR_RELATED_CASES)
    if asset_id:
        prior = get_prior_related_cases(asset_id)
        # Exclude the current case from the related list
        evidence["prior_related_cases"] = [p for p in prior if p["case_id"] != case_id]
    else:
        evidence["prior_related_cases"] = []

    # Delegate text generation to LLM stub
    summary = generate("case_summary", evidence)

    # Attach pass-through metadata so the caller can cross-reference
    summary["case_id"] = case_id
    summary["verdict"] = evidence["verdict"]
    summary["severity_score"] = evidence["severity_score"]
    summary["matched_asset_id"] = asset_id
    summary["prior_related_case_count"] = len(evidence["prior_related_cases"])

    return summary


def attempt_blocked_action(action: AgentAction) -> dict:
    """
    Attempt an action that should be blocked by policy.

    Used in tests and in the API to demonstrate that the guardrail works.
    Returns a structured error dict instead of raising, so the API layer
    can return a clean 403 response.

    Args:
        action: An AgentAction to check.

    Returns:
        Dict with allowed=False and the block reason.
    """
    result = check_policy(action)
    return {
        "allowed": result.allowed,
        "action": result.action.value,
        "reason": result.reason,
    }