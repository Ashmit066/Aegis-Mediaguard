"""
workers/sandbox.py
Runs CPU-intensive matching and watermark verification in a separate process
using ProcessPoolExecutor, with configurable timeout protection.

Isolating heavy work from the request thread ensures:
- The FastAPI event loop is never blocked.
- A runaway analysis job can be killed without affecting other requests.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

from app.config import settings
from app.models import IncomingReport, MatchResult
from identify.matcher import match_report


def _worker_match(report_dict: dict) -> dict:
    """
    Top-level function executed inside the worker process.
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
    Submit a fingerprint-matching job to a subprocess and wait for the result,
    raising TimeoutError if it does not complete within the configured limit.

    Args:
        report: Validated, normalized IncomingReport.

    Returns:
        MatchResult from the subprocess.

    Raises:
        TimeoutError: If the worker does not finish in time.
        RuntimeError: If the worker raises an unexpected exception.
    """
    report_dict = report.model_dump(mode="json")

    with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_worker_match, report_dict)
        try:
            result_dict = future.result(timeout=settings.sandbox_timeout_seconds)
            return MatchResult.model_validate(result_dict)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"Matching sandbox timed out after {settings.sandbox_timeout_seconds}s"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Sandbox worker failed: {exc}") from exc
