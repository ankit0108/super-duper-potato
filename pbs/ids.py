"""Readable, time-sortable IDs."""

from __future__ import annotations

import hashlib
import random

from . import timeutil

_rng = random.Random()


def seed(value: int) -> None:
    """Make IDs deterministic (tests)."""
    _rng.seed(value)


def new_id(prefix: str) -> str:
    t = timeutil.now()
    return f"{prefix}_{t:%Y%m%d%H%M%S}_{_rng.getrandbits(24):06x}"


def stable_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


def short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]
