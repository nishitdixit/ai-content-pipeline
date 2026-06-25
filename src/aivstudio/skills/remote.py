"""Remote-service skill adapters.

These call hosted APIs and slot into the exact same Skill contracts as the
mock perception skills. They use only the standard library (urllib), so
there is nothing extra to pip-install — you just set an API key.

Activation is automatic: if the key env var is set, `default_registry`
prefers the remote impl for that capability; if not, it silently falls
back to the mock impl. So the only step to "go live" is exporting a key.

Currently wired:
  - DeepgramTranscribeSkill   (capability: transcribe)   key: DEEPGRAM_API_KEY

Add more by copying the pattern (e.g. AssemblyAI, TwelveLabs, OpenAI embed).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .base import Skill


def _mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
        ".webm": "video/webm", ".m4a": "audio/mp4", ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }.get(ext, "application/octet-stream")


class DeepgramTranscribeSkill(Skill):
    """Real transcription via Deepgram's pre-recorded API, returning word
    timestamps so ingest can slice a transcript per window.

    Sign up: https://deepgram.com  (free $200 credit). Then:
        export DEEPGRAM_API_KEY="dg_..."
    """
    capability = "transcribe"
    name = "deepgram"
    version = "1.0.0"
    remote = True
    _URL = "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true"

    def available(self) -> bool:
        return bool(os.environ.get("DEEPGRAM_API_KEY"))

    def run(self, *, proxy_path: str, **_: Any) -> dict[str, Any]:
        key = os.environ.get("DEEPGRAM_API_KEY")
        if not key:
            return {"words": [], "transcript": ""}
        try:
            data = Path(proxy_path).read_bytes()
            req = urllib.request.Request(
                self._URL, data=data, method="POST",
                headers={"Authorization": f"Token {key}", "Content-Type": _mime(proxy_path)},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                payload = json.loads(resp.read().decode())
            alt = payload["results"]["channels"][0]["alternatives"][0]
            transcript = (alt.get("transcript") or "").strip()
            words = [{"word": w.get("punctuated_word") or w.get("word", ""),
                      "start": float(w.get("start", 0)), "end": float(w.get("end", 0))}
                     for w in alt.get("words", [])]
        except (urllib.error.URLError, KeyError, IndexError, ValueError, OSError) as e:
            print(f"  [deepgram] transcription failed for {Path(proxy_path).name}: {e}")
            return {"words": [], "transcript": ""}
        return {"words": words, "transcript": transcript}
