"""Command-line interface.

  aivstudio ingest   <media_dir> --project <dir>      # analyze-once + incremental
  aivstudio generate <project>   "<brief>"            # retrieve -> plan -> render
  aivstudio reedit   <project>   "<instruction>"
  aivstudio status   <project>
  aivstudio reference <project> <ref_file>            # extract a style spec
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .memory.store import RecordStore
from .memory.ingest import ingest_dir
from .skills import default_registry
from .config import load_providers
from .events import EventBus, console_printer, JsonlRecorder
from .session import Session
from .reference import extract_style_spec


def _ingest(args) -> None:
    store = RecordStore(args.project)
    bus = EventBus(); bus.subscribe(console_printer(args.quiet))
    rec = JsonlRecorder(str(Path(args.project) / "ingest_events.jsonl")); bus.subscribe(rec)
    skills = default_registry(load_providers())
    res = ingest_dir(args.media_dir, store, skills, bus, force=args.force)
    rec.close()
    print(json.dumps({"ingest": res, "library": store.counts()}, indent=2))


def _generate(args) -> None:
    s = Session(args.project, profile_name=args.profile, quiet=args.quiet)
    res = s.generate(args.brief, execute=not args.no_render)
    _summary(res)


def _reedit(args) -> None:
    s = Session(args.project, profile_name=args.profile, quiet=args.quiet)
    # re-edit needs a prior request; re-derive from the instruction as a fresh brief if none
    s.generate(args.instruction, execute=False)
    res = s.re_edit(args.instruction, execute=not args.no_render)
    _summary(res)


def _status(args) -> None:
    store = RecordStore(args.project)
    print(json.dumps({"library": store.counts(),
                      "assets": [{"name": a.source_name, "status": a.status,
                                  "dur": a.duration_s} for a in store.assets]}, indent=2))


def _reference(args) -> None:
    store = RecordStore(args.project)
    bus = EventBus(); bus.subscribe(console_printer(args.quiet))
    skills = default_registry(load_providers())
    res = ingest_dir(Path(args.ref_file).parent, store, skills, bus)
    a = max(store.assets, key=lambda a: a.analyzed_at or "")
    spec = extract_style_spec(a, store.segments)
    print(json.dumps({"style_spec": spec}, indent=2))


def _summary(res: dict) -> None:
    edl = res["edl"]
    print("\n--- EDL ---")
    print(f"variant: {edl['variant_label']} | {edl['shot_count']} shots | {edl['total_duration_s']}s")
    for i, c in enumerate(edl["timeline"], 1):
        pair = f"  audio<-{Path(c['audio_from']).name}" if c.get("audio_from") else ""
        print(f"  {i:>2}. [{c['role']:<9}] {Path(c['source']).name:<22} {c['duration_s']}s{pair}")
        print(f"       reason: {c['reason']}")
    r = res["render"]
    print(f"\noutput: {r.get('output_path') or '(script only) ' + r.get('render_script','')}")
    if res.get("flags"):
        print("flags:", res["flags"])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="aivstudio")
    p.add_argument("--quiet", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ingest"); a.add_argument("media_dir"); a.add_argument("--project", required=True); a.add_argument("--force", action="store_true", help="re-analyze even already-known clips (use after changing analysis logic)"); a.set_defaults(fn=_ingest)
    g = sub.add_parser("generate"); g.add_argument("project"); g.add_argument("brief"); g.add_argument("--profile"); g.add_argument("--no-render", action="store_true"); g.set_defaults(fn=_generate)
    e = sub.add_parser("reedit"); e.add_argument("project"); e.add_argument("instruction"); e.add_argument("--profile"); e.add_argument("--no-render", action="store_true"); e.set_defaults(fn=_reedit)
    st = sub.add_parser("status"); st.add_argument("project"); st.set_defaults(fn=_status)
    rf = sub.add_parser("reference"); rf.add_argument("project"); rf.add_argument("ref_file"); rf.set_defaults(fn=_reference)

    args = p.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
