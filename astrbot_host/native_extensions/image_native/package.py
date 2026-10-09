"""Content identity for the native provider and its reused transport files."""
from __future__ import annotations

import hashlib
from pathlib import Path


def package_hash() -> str:
    native = Path(__file__).parent
    paths = sorted(native.glob("*.py"))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8") + b"\x00" + path.read_bytes())
    return digest.hexdigest()
