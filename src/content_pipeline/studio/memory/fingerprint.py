"""Fingerprinting — the one primitive behind dedup AND incremental ingest.

content_hash  : identity of a file's bytes. Same clip dumped twice -> stored once.
perceptual_hash: cheap visual signature so near-duplicates can be flagged.

The diff against the registry of known content hashes is what makes
"I added more clips later" analyze only the genuinely new ones.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return "sha256:" + h.hexdigest()


def perceptual_hash(path: str | Path, samples: int = 16) -> str:
    """A cheap, dependency-free stand-in for a real video pHash.

    Samples bytes evenly across the file and hashes the coarse profile.
    Swap with a frame-based DCT pHash when you want true near-dup detection.
    """
    data = Path(path).read_bytes()
    if not data:
        return "phash:0"
    n = len(data)
    step = max(1, n // samples)
    profile = bytes(data[i] for i in range(0, n, step))
    return "phash:" + hashlib.md5(profile).hexdigest()[:16]
