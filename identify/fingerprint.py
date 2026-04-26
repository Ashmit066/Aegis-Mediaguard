"""
identify/fingerprint.py
Deterministic perceptual hash comparison using Hamming distance on hex strings.
Simulates how a real pHash or content fingerprint library would behave.
"""

from __future__ import annotations

import math


def _hex_to_bits(hex_str: str) -> str:
    """Convert a hex string to a binary bit string."""
    try:
        value = int(hex_str, 16)
        bit_length = len(hex_str) * 4
        return format(value, f"0{bit_length}b")
    except ValueError:
        return ""


def hamming_distance(a: str, b: str) -> int:
    """
    Compute the Hamming distance between two hex strings by comparing their
    binary representations bit-by-bit.

    If the strings differ in length, the shorter one is zero-padded on the left.

    Args:
        a: First hex string.
        b: Second hex string.

    Returns:
        Number of bit positions that differ.
    """
    bits_a = _hex_to_bits(a.lower())
    bits_b = _hex_to_bits(b.lower())

    max_len = max(len(bits_a), len(bits_b))
    bits_a = bits_a.zfill(max_len)
    bits_b = bits_b.zfill(max_len)

    return sum(ca != cb for ca, cb in zip(bits_a, bits_b))


def fingerprint_similarity(extracted: str, canonical: str) -> float:
    """
    Compute a similarity score [0.0, 1.0] between two hex fingerprints.

    Score = 1.0 − (hamming_distance / total_bits)

    Args:
        extracted: Fingerprint pulled from the discovered media.
        canonical: Official fingerprint from the asset catalog.

    Returns:
        Similarity score between 0.0 (completely different) and 1.0 (identical).
    """
    if not extracted or not canonical:
        return 0.0

    bits_a = _hex_to_bits(extracted.lower())
    bits_b = _hex_to_bits(canonical.lower())

    max_len = max(len(bits_a), len(bits_b))
    if max_len == 0:
        return 0.0

    bits_a = bits_a.zfill(max_len)
    bits_b = bits_b.zfill(max_len)

    distance = sum(ca != cb for ca, cb in zip(bits_a, bits_b))
    return round(1.0 - distance / max_len, 4)
