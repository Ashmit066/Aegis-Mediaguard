"""
workers/sandbox.py
Runs CPU-intensive matching and watermark verification in-process.

NOTE (Hackathon Mode): The ProcessPoolExecutor sandbox is bypassed because
spinning up a new child process on every FastAPI request causes a deadlock
in WSL/Windows environments.  match_report() is called directly instead.
The sandbox architecture is preserved for reference and production upgrade.
"""

from __future__ import annotations

from app.models import IncomingReport, MatchResult
from identify.matcher import match_report


def _worker_match(report_dict: dict) -> dict:
    """
    Top-level function that would execute inside the worker process.
    Must be picklable (module-level, no lambdas).

    Reconstructs the IncomingReport from its dict representation to
    avoid cross-process object sharing issues.

    Args:
        report_dict: A dict produced by IncomingReport.model_dump().

    Returns:
        A dict produced by MatchResult.model_dump().
    """
    report = IncomingReport.model_validate(report_dict)
    result = match_report(report)
    return result.model_dump()


def run_match_in_sandbox(report: IncomingReport) -> MatchResult:
    """
    Submit a fingerprint-matching job and return the result.

    In production this would use ProcessPoolExecutor for isolation.
    For the hackathon demo, match_report is called directly to avoid
    the WSL/Windows deadlock caused by spawning child processes inside
    a uvicorn worker thread.

    Args:
        report: Validated, normalized IncomingReport.

    Returns:
        MatchResult from the matching layer.
    """
    return match_report(report)
