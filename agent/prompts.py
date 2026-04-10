"""
agent/prompts.py
Prompt construction helpers.

When the stub is replaced with a real LLM call, these functions produce the
system and user prompt strings that will be sent to the API.  For now they are
used only to document the intended prompt shape — the stub bypasses them and
works directly from evidence dicts.
"""

from __future__ import annotations


SYSTEM_PROMPT = """\
You are a read-only sports media rights triage assistant embedded inside the
Aegis MediaGuard enforcement system.

Your capabilities are strictly limited to:
- Reading and explaining deterministic analysis results.
- Summarizing evidence gathered by the enforcement pipeline.
- Drafting takedown notices for human review.
- Prioritizing cases by urgency.

You may NOT:
- Override or modify verdicts issued by the enforcement pipeline.
- Alter rights data, license records, or the asset catalog.
- Delete or amend audit ledger entries.
- Execute any enforcement action directly.

Always present your output as structured JSON matching the AgentSummary schema.
Never fabricate evidence; derive everything from the structured inputs provided.
"""


def build_case_summary_prompt(evidence: dict) -> str:
    """
    Build the user-turn prompt for a case summary request.

    In the stub this is unused.  In a real LLM integration, pass this string
    as the `content` field of the user message alongside SYSTEM_PROMPT as the
    system message.

    Args:
        evidence: Structured evidence dict assembled by agent/tools.py.

    Returns:
        A formatted prompt string.
    """
    lines = [
        "Please produce a triage summary for the following case evidence.",
        "",
        f"Verdict (authoritative, do not change): {evidence.get('verdict')}",
        f"Severity score: {evidence.get('severity_score')}/100",
        f"Asset: {evidence.get('asset_title', 'Unknown')}",
        f"Platform: {evidence.get('platform')}",
        f"Region: {evidence.get('geo_country')}",
        f"Uploader: {evidence.get('uploader_handle')}",
        f"Discovered URL: {evidence.get('discovered_url')}",
        f"Fingerprint confidence: {round(evidence.get('combined_confidence', 0) * 100)}%",
        f"Watermark detected: {evidence.get('watermark_detected')}",
        "",
        "Rights decision reasons:",
    ]
    for r in evidence.get("rights_reasons", []):
        lines.append(f"  - {r}")
    lines.extend([
        "",
        "Return a JSON object with keys: summary, key_evidence (list), "
        "urgency_label, recommended_action, draft_takedown_notice (or null).",
    ])
    return "\n".join(lines)