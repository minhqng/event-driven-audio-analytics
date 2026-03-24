"""Artifact loading placeholders for processing."""

from __future__ import annotations


def load_segment_artifact(artifact_uri: str, checksum: str) -> bytes:
    """Return an empty payload until artifact loading is implemented."""

    # TODO: implement claim-check artifact loading and checksum verification.
    _ = (artifact_uri, checksum)
    return b""
