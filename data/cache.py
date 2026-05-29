"""Tiny file-based cache for slow/large fetches (e.g. the corp-code list)."""

from __future__ import annotations

import os
import time

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")


def _path(key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return os.path.join(CACHE_DIR, safe)


def get(key: str, max_age_seconds: float | None = None) -> bytes | None:
    p = _path(key)
    if not os.path.exists(p):
        return None
    if max_age_seconds is not None and (time.time() - os.path.getmtime(p)) > max_age_seconds:
        return None
    with open(p, "rb") as fh:
        return fh.read()


def put(key: str, data: bytes) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_path(key), "wb") as fh:
        fh.write(data)
