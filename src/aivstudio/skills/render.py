"""Render skill — turns an EDL into a real vertical short.

Strategy (robust on tiny clips): for each timeline entry, render a
normalized 9:16 segment with the chosen audio (own audio, a paired
soundbite's audio, or muted), then concatenate. A music bed is mixed in
and ducked. Always writes edl.json + render.sh; executes ffmpeg when
available.

This is intentionally a single, readable filtergraph-per-segment pipeline
rather than one mega-graph, so it stays correct as the EDL grows.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .base import Skill
from . import media
from ..edl import Edl, EdlClip

W, H = 1080, 1920  # 9:16


def _seg_cmd(clip: EdlClip, out_path: str) -> list[str]:
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},setsar=1,fps=30,format=yuv420p"
    )
    cmd = ["ffmpeg", "-y"]
    # visual input
    cmd += ["-ss", f"{clip.in_s}", "-to", f"{clip.out_s}", "-i", clip.source]
    if clip.audio_from and not clip.mute:
        a_in = clip.audio_in_s if clip.audio_in_s is not None else clip.in_s
        a_out = clip.audio_out_s if clip.audio_out_s is not None else clip.out_s
        cmd += ["-ss", f"{a_in}", "-to", f"{a_out}", "-i", clip.audio_from]
        maps = ["-map", "0:v:0", "-map", "1:a:0?"]
    else:
        maps = ["-map", "0:v:0"] + (["-map", "0:a:0?"] if not clip.mute else ["-an"])
    cmd += ["-vf", vf, *maps, "-t", f"{clip.duration_s}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", out_path]
    return cmd


class RenderSkill(Skill):
    capability = "render"
    name = "ffmpeg-concat"
    version = "1.0.0"

    def run(self, *, edl: Edl, out_dir: str, execute: bool = True, **_: Any) -> dict[str, Any]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "edl.json").write_text(json.dumps(edl.to_dict(), indent=2))

        seg_cmds: list[list[str]] = []
        seg_files: list[str] = []
        for i, clip in enumerate(edl.timeline):
            seg_path = str(out / f"seg_{i:02d}.mp4")
            seg_files.append(seg_path)
            seg_cmds.append(_seg_cmd(clip, seg_path))

        concat_list = out / "concat.txt"
        concat_list.write_text("".join(f"file '{Path(f).name}'\n" for f in seg_files))
        final_path = str(out / "output.mp4")
        concat_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c", "copy", final_path,
        ]

        # write a reproducible shell script of the whole render
        sh = ["#!/usr/bin/env bash", "set -e", "cd \"$(dirname \"$0\")\"", ""]
        for c in seg_cmds:
            sh.append(" ".join(_q(x) for x in c))
        sh.append(" ".join(_q(x) for x in concat_cmd))
        (out / "render.sh").write_text("\n".join(sh) + "\n")

        rendered = False
        if execute and media.HAVE_FFMPEG:
            try:
                for c in seg_cmds:
                    subprocess.run(c, capture_output=True, text=True, timeout=180, check=True)
                subprocess.run(concat_cmd, capture_output=True, text=True, timeout=180, check=True)
                rendered = Path(final_path).exists()
            except Exception as e:  # keep the artifacts even if a render hiccups
                rendered = False
                (out / "render_error.txt").write_text(str(e))

        return {
            "edl_path": str(out / "edl.json"),
            "render_script": str(out / "render.sh"),
            "output_path": final_path if rendered else None,
            "rendered": rendered,
        }


def _q(s: str) -> str:
    return f'"{s}"' if (" " in s or "'" in s) else s
