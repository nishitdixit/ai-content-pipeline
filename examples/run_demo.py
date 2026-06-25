"""End-to-end demo. Run from the repo root:

    PYTHONPATH=src python examples/run_demo.py

It will:
  1. synthesize sample clips,
  2. ingest them (analyze once) into a project memory,
  3. add one more clip and re-ingest (only the new one is analyzed),
  4. generate a motivational short (10 shots / 30s) from memory,
  5. re-edit it ("punchier opening"),
and print the EDL + write renders/<...>/output.mp4 and events.jsonl.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))            # for `scripts`
sys.path.insert(0, str(_ROOT / "src"))    # for `aivstudio`

from aivstudio.memory.store import RecordStore
from aivstudio.memory.ingest import ingest_dir
from aivstudio.skills import default_registry
from aivstudio.config import load_providers
from aivstudio.events import EventBus, console_printer, JsonlRecorder
from aivstudio.session import Session

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "sample_media"
PROJECT = ROOT / "demo_project"


def _bus(path: Path):
    bus = EventBus(); bus.subscribe(console_printer())
    rec = JsonlRecorder(str(path)); bus.subscribe(rec)
    return bus, rec


def main() -> None:
    if PROJECT.exists():
        shutil.rmtree(PROJECT)

    # 1) sample media
    import scripts.make_sample_media as gen  # noqa
    gen.make(str(MEDIA))

    skills = default_registry(load_providers())
    store = RecordStore(PROJECT)

    # 2) ingest all but one clip (simulate a first dump)
    held_out = MEDIA / "finish_hero_peak.mp4"
    staged = MEDIA.parent / "_staged"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir()
    for p in sorted(MEDIA.glob("*.mp4")):
        if p.name != held_out.name:
            shutil.copy(p, staged / p.name)

    print("\n########## INGEST PASS 1 ##########")
    bus, rec = _bus(PROJECT / "ingest_events.jsonl")
    r1 = ingest_dir(staged, store, skills, bus); rec.close()
    print("pass1:", r1, "| library:", store.counts())

    # 3) add the held-out clip and re-ingest -> only the new one analyzes
    shutil.copy(held_out, staged / held_out.name)
    print("\n########## INGEST PASS 2 (incremental) ##########")
    bus, rec = _bus(PROJECT / "ingest_events.jsonl")
    r2 = ingest_dir(staged, store, skills, bus); rec.close()
    print("pass2:", r2, "| library:", store.counts())
    assert r2["new"] == 1 and r2["skipped"] == r1["new"], "incremental diff failed"

    # 4) generate a motivational short from memory (no re-analysis)
    print("\n########## GENERATE ##########")
    sess = Session(str(PROJECT), profile_name="motivational")
    res = sess.generate("Make a motivational short — 10 shots in 30s, build to a peak.")
    _print_edl("generate", res)

    # 5) re-edit
    print("\n########## RE-EDIT: punchier opening ##########")
    res2 = sess.re_edit("make the opening punchier")
    _print_edl("re-edit", res2)

    print("\nDONE. Artifacts under", PROJECT)
    print("  - events.jsonl  (feed the dashboard)")
    print("  - renders/latest/output.mp4")


def _print_edl(tag: str, res: dict) -> None:
    edl = res["edl"]
    print(f"[{tag}] {edl['variant_label']}: {edl['shot_count']} shots / {edl['total_duration_s']}s")
    for i, c in enumerate(edl["timeline"], 1):
        pair = f"  audio<-{Path(c['audio_from']).name}" if c.get("audio_from") else ""
        print(f"  {i:>2}. [{c['role']:<9}] {Path(c['source']).name:<26} {c['duration_s']}s{pair}")
    r = res["render"]
    print("  render:", r.get("output_path") or ("script: " + str(r.get("render_script"))))
    if res.get("pairings"):
        print("  pairings:", res["pairings"])


if __name__ == "__main__":
    main()
