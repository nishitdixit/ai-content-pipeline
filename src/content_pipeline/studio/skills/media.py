"""Thin ffmpeg/ffprobe helpers.

Everything degrades gracefully when ffmpeg is absent so the pipeline still
runs (with synthetic signals). When ffmpeg is present, ingest computes a
few *real* cheap signals (duration, loudness, scene cuts) so "analyze
once" genuinely measures the media.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
HAVE_FFPROBE = shutil.which("ffprobe") is not None


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def sidecar_duration(path: str | Path) -> float:
    """Duration from a `<file>.meta.json` sidecar (written for synthetic clips when ffmpeg is absent)."""
    meta = Path(f"{path}.meta.json")
    try:
        return float(json.loads(meta.read_text())["duration_s"])
    except (OSError, ValueError, KeyError):
        return 0.0


def probe_duration(path: str | Path) -> float:
    if not HAVE_FFPROBE:
        return sidecar_duration(path)
    cp = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ])
    try:
        return float(json.loads(cp.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def mean_volume_db(path: str | Path) -> float | None:
    """Mean audio volume in dBFS via volumedetect (closer to 0 = louder)."""
    if not HAVE_FFMPEG:
        return None
    cp = _run([
        "ffmpeg", "-i", str(path), "-af", "volumedetect",
        "-f", "null", "-",
    ])
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", cp.stderr)
    return float(m.group(1)) if m else None


def scene_cut_times(path: str | Path, threshold: float = 0.3) -> list[float]:
    """Timestamps of scene changes (real shot boundaries)."""
    if not HAVE_FFMPEG:
        return []
    cp = _run([
        "ffmpeg", "-i", str(path),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ])
    return sorted({float(m) for m in re.findall(r"pts_time:(\d+(?:\.\d+)?)", cp.stderr)})


def make_proxy(src: str | Path, dst: str | Path) -> bool:
    """Normalize to a standard working proxy. Returns True on success."""
    if not HAVE_FFMPEG:
        return False
    cp = _run([
        "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-c:a", "aac", "-b:a", "128k", str(dst),
    ])
    return cp.returncode == 0 and Path(dst).exists()
