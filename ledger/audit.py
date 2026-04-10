"""
ledger/audit.py
Append-only, SHA-256 hash-linked audit ledger for tamper-evident evidence storage.
Suitable for compliance and legal review of the full analysis chain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models import EvidenceEvent, LedgerEntry, LedgerVerifyResult

_LEDGER: list[LedgerEntry] = []
# Parallel list of the exact timestamp strings used when each entry was hashed
_LEDGER_TS_STRINGS: list[str] = []
_GENESIS_HASH = "0" * 64


def _compute_hash(seq: int, timestamp: str, event_type: str, event_data: dict, prev_hash: str) -> str:
    """Deterministically hash one ledger entry."""
    payload = json.dumps(
        {
            "seq": seq,
            "timestamp": timestamp,
            "event_type": event_type,
            "event_data": event_data,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def append_event(event_type: EvidenceEvent, event_data: dict[str, Any]) -> LedgerEntry:
    """
    Append a new evidence event to the ledger.

    Each entry stores:
    - Its sequential position
    - The current UTC timestamp
    - The event type and payload
    - The hash of the previous entry (chain link)
    - Its own SHA-256 hash

    Args:
        event_type: One of the defined EvidenceEvent enum values.
        event_data: Arbitrary dict carrying event-specific details.

    Returns:
        The newly created LedgerEntry.
    """
    seq = len(_LEDGER)
    now = datetime.now(timezone.utc)
    timestamp_str = now.isoformat()
    prev_hash = _LEDGER[-1].entry_hash if _LEDGER else _GENESIS_HASH

    entry_hash = _compute_hash(seq, timestamp_str, event_type.value, event_data, prev_hash)

    entry = LedgerEntry(
        seq=seq,
        timestamp=now,
        event_type=event_type,
        event_data=event_data,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    _LEDGER.append(entry)
    _LEDGER_TS_STRINGS.append(timestamp_str)
    return entry


def get_ledger() -> list[LedgerEntry]:
    """Return a copy of the full ledger."""
    return list(_LEDGER)


def verify_chain() -> LedgerVerifyResult:
    """
    Walk the ledger and confirm that every entry's prev_hash matches
    the previous entry's stored hash, and that each hash is reproducible.

    Returns:
        LedgerVerifyResult indicating validity and any broken link position.
    """
    if not _LEDGER:
        return LedgerVerifyResult(valid=True, entry_count=0, message="Ledger is empty.")

    expected_prev = _GENESIS_HASH

    for entry, ts_str in zip(_LEDGER, _LEDGER_TS_STRINGS):
        if entry.prev_hash != expected_prev:
            return LedgerVerifyResult(
                valid=False,
                entry_count=len(_LEDGER),
                first_broken_seq=entry.seq,
                message=f"Chain broken at seq {entry.seq}: "
                        f"expected prev_hash {expected_prev[:16]}… "
                        f"but found {entry.prev_hash[:16]}…",
            )

        # Recompute this entry's hash using the original timestamp string
        recomputed = _compute_hash(
            entry.seq,
            ts_str,
            entry.event_type.value,
            entry.event_data,
            entry.prev_hash,
        )
        if recomputed != entry.entry_hash:
            return LedgerVerifyResult(
                valid=False,
                entry_count=len(_LEDGER),
                first_broken_seq=entry.seq,
                message=f"Hash mismatch at seq {entry.seq}: entry data may have been tampered with.",
            )

        expected_prev = entry.entry_hash

    return LedgerVerifyResult(
        valid=True,
        entry_count=len(_LEDGER),
        message=f"All {len(_LEDGER)} entries verified. Chain is intact.",
    )
