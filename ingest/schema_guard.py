"""
ingest/schema_guard.py
Validates incoming telemetry payloads against the strict IncomingReport schema.
Returns either a validated model or a structured error list.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.models import IncomingReport


class SchemaValidationError(Exception):
    """Raised when an incoming payload fails schema validation."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__(f"Schema validation failed with {len(errors)} error(s)")


def validate_report(raw: dict) -> IncomingReport:
    """
    Parse and validate a raw dictionary against IncomingReport.

    Args:
        raw: Arbitrary dictionary from an HTTP request body.

    Returns:
        A fully validated IncomingReport instance.

    Raises:
        SchemaValidationError: If the payload violates the schema in any way.
    """
    try:
        return IncomingReport.model_validate(raw)
    except ValidationError as exc:
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        raise SchemaValidationError(errors) from exc
