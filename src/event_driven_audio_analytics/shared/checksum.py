"""Checksum helpers shared across claim-check workflows."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def sha256_bytes(payload: bytes) -> str:
    """Return a prefixed SHA-256 digest for the provided bytes."""

    digest = sha256(payload).hexdigest()
    return f"sha256:{digest}"


def sha256_file(path: str | Path, *, chunk_size: int = 65536) -> str:
    """Return a prefixed SHA-256 digest for a file on disk."""

    file_path = Path(path)
    digest = sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)

    return f"sha256:{digest.hexdigest()}"
