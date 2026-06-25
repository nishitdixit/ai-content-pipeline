"""Generate tiny synthetic sample clips for the demo.

Each clip's filename encodes its character (the mock perception skills read
these hint tokens as a stand-in for what real vision/ASR models detect):
  *_wide / *_drone / *_coast   -> strong visual, weak/ambient audio (B-roll)
  *_speech / *_vlog / *_line   -> strong speech, weaker visual (soundbite)
  *_summit / *_hero            -> strong on both (hero)
  *_filler                     -> weak on both (discard)

Clips are 3-4s, vertical-friendly, with a sine tone so audio exists.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CLIPS = [
    ("ride_coast_wide", "c=0x1b4965", 3.0, 220),
    ("sunrise_ridge_drone", "c=0xe8a33d", 3.5, 180),
    ("climb_grind_wide", "c=0x5fa8d3", 3.0, 200),
    ("dream_vista_drone", "c=0x2b6777", 3.0, 190),
    ("rise_speech_line", "c=0x3d2b56", 3.0, 330),
    ("push_vlog_talk", "c=0x4a4063", 3.0, 350),
    ("struggle_speech_quote", "c=0x2c2c34", 3.0, 300),
    ("triumph_summit_hero", "c=0xf4a261", 4.0, 260),
    ("finish_hero_peak", "c=0xe76f51", 3.5, 280),
    ("motivational_rise_wide", "c=0x264653", 3.0, 210),
    ("grind_coast_scenery", "c=0x457b9d", 3.0, 195),
    ("boring_filler_dead", "c=0x6c757d", 2.5, 120),
]


def make(out_dir: str) -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found; cannot synthesize clips", file=sys.stderr)
        return 1
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    for name, color, dur, freq in CLIPS:
        path = out / f"{name}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color={color}:s=720x1280:d={dur}:r=30",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-shortest", str(path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    print(f"wrote {len(CLIPS)} clips to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(make(sys.argv[1] if len(sys.argv) > 1 else "sample_media"))
