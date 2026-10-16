"""Tiny, dependency-free text/embedding utilities.

The hashed bag-of-tokens embedding is a crude stand-in for a real
text/visual embedding model (CLIP/SigLIP/text-embeddings). It is good
enough to demonstrate semantic retrieval over shared vocabulary, and it
lives behind the EmbedSkill interface so a real model is a drop-in.
"""
from __future__ import annotations

import hashlib
import math
import re

EMBED_DIM = 96

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "with", "for",
    "is", "it", "that", "this", "i", "want", "make", "create", "video",
    "shots", "shot", "secs", "sec", "seconds", "second", "short", "clip",
    "clips", "from", "my", "me", "all", "build", "into",
}


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


def embed_text(text: str, dim: int = EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    return _l2(vec)


def embed_tags(tags: list[str], text: str = "", dim: int = EMBED_DIM) -> list[float]:
    return embed_text(" ".join(tags) + " " + text, dim)


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
