"""
agent/policy.py
Explicit guardrail table for every action the agent layer may attempt.

The enforcement plane (deterministic backend) is the sole authority on verdicts,
rights data, and the audit ledger.  The agent layer is permitted only to read
evidence, explain decisions, and draft external communications.

Any request that falls outside the allowed set is rejected here before it
reaches any business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentAction(str, Enum):
    # Allowed: read-only and drafting
    GET_CASE_EVIDENCE = "get_case_evidence"
    GET_ASSET_DETAILS = "get_asset_details"
    GET_RIGHTS_EXPLANATION = "get_rights_explanation"
    GET_PRIOR_RELATED_CASES = "get_prior_related_cases"
    DRAFT_TAKEDOWN_NOTICE = "draft_takedown_notice"
    SUMMARIZE_CASE = "summarize_case"

    # Blocked: any mutation or enforcement action
    OVERRIDE_VERDICT = "override_verdict"
    DELETE_LEDGER_ENTRY = "delete_ledger_entry"
    MUTATE_RIGHTS_DATA = "mutate_rights_data"
    EXECUTE_TAKEDOWN = "execute_takedown"
    MODIFY_ASSET_CATALOG = "modify_asset_catalog"


_ALLOWED: frozenset[AgentAction] = frozenset(
    {
        AgentAction.GET_CASE_EVIDENCE,
        AgentAction.GET_ASSET_DETAILS,
        AgentAction.GET_RIGHTS_EXPLANATION,
        AgentAction.GET_PRIOR_RELATED_CASES,
        AgentAction.DRAFT_TAKEDOWN_NOTICE,
        AgentAction.SUMMARIZE_CASE,
    }
)

_BLOCK_REASONS: dict[AgentAction, str] = {
    AgentAction.OVERRIDE_VERDICT: (
        "Verdicts are produced by the deterministic enforcement pipeline and are "
        "immutable.  The agent may read and explain verdicts but never alter them."
    ),
    AgentAction.DELETE_LEDGER_ENTRY: (
        "The audit ledger is append-only and hash-linked.  Deletion would break "
        "chain integrity and destroy legal evidence."
    ),
    AgentAction.MUTATE_RIGHTS_DATA: (
        "Rights data comes from authoritative license records.  The agent has no "
        "permission to modify platform, region, or date constraints."
    ),
    AgentAction.EXECUTE_TAKEDOWN: (
        "Actual takedown execution must be performed by an authorized human operator "
        "after reviewing the draft notice produced by this system."
    ),
    AgentAction.MODIFY_ASSET_CATALOG: (
        "The official asset catalog is managed by rights administrators, not the "
        "triage agent."
    ),
}


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    action: AgentAction
    reason: str


def check_policy(action: AgentAction) -> PolicyResult:
    """
    Evaluate whether an agent action is permitted under current policy.

    Args:
        action: The AgentAction the orchestrator wants to perform.

    Returns:
        PolicyResult with allowed=True when the action is safe, or
        allowed=False with an explanation when it is blocked.
    """
    if action in _ALLOWED:
        return PolicyResult(allowed=True, action=action, reason="Action is permitted.")

    reason = _BLOCK_REASONS.get(action, "Action is not in the permitted set.")
    return PolicyResult(allowed=False, action=action, reason=reason)