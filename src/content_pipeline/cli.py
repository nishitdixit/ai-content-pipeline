"""Command line: `acp <command>`. Run `acp -h` for the list.

Writer (scripts):  doctor, themes, plan-week, script, suggest-ideas, compare, notion-setup
Studio (video):    ingest, edit, reedit, status, reference, styles
Pipeline:          demo   (script -> footage -> edit, offline, with a dashboard)
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from datetime import date, datetime
from pathlib import Path

from content_pipeline import __version__
from content_pipeline.bridge import edit_request, read_script
from content_pipeline.config import Paths, env, profile_paths
from content_pipeline.events import EventBus, JsonlRecorder, console_printer
from content_pipeline.llm import PROVIDERS, LLMError, available_providers, get_provider
from content_pipeline.studio.config import list_styles, load_providers
from content_pipeline.studio.memory.ingest import ingest_dir
from content_pipeline.studio.memory.store import RecordStore
from content_pipeline.studio.reference import extract_style_spec
from content_pipeline.studio.session import Session
from content_pipeline.studio.skills import default_registry
from content_pipeline.writer import notion_sync
from content_pipeline.writer.channel import Channel, load_channel
from content_pipeline.writer.plan import next_monday, plan_week, suggest_ideas, write_script
from content_pipeline.writer.prompts import build_system_prompt
from content_pipeline.writer.render import existing_script, render_markdown
from content_pipeline.writer.scriptgen import generate_script
from content_pipeline.writer.themes import ThemeBank

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard" / "index.html"


def _date(value: str) -> date:
    return date.fromisoformat(value)


# --- shared plumbing ---------------------------------------------------------

class Run:
    """One CLI invocation: profile, channel, and an event bus (console + optional JSONL)."""

    def __init__(self, args) -> None:
        self.args = args
        self.paths: Paths = profile_paths(getattr(args, "profile", None))
        self._channel: Channel | None = None
        self.bus = EventBus()
        self.bus.subscribe(console_printer(quiet=True))  # writer commands print their own lines
        self.recorder = JsonlRecorder(args.events) if getattr(args, "events", None) else None
        if self.recorder:
            self.bus.subscribe(self.recorder)

    @property
    def channel(self) -> Channel:
        if self._channel is None:
            self._channel = load_channel(self.paths)
        return self._channel

    def system_prompt(self) -> str:
        return build_system_prompt(self.paths, self.channel)

    def provider(self, name: str | None = None):
        return get_provider(name, on_usage=lambda u: self.bus.emit("llm.usage", **u))

    def notion(self, enabled: bool):
        if not enabled or not notion_sync.is_configured():
            return None
        return notion_sync.NotionMirror()

    def close(self) -> None:
        if self.recorder:
            self.recorder.close()


def _emit_outcomes(bus: EventBus, outcomes) -> None:
    for o in outcomes:
        if o.status == "written":
            bus.emit("agent.done", agent="ScriptWriter",
                     result=f"{o.day} {o.result.pillar}: {o.result.draft.working_title} "
                            f"({o.result.draft.word_count()} words, {len(o.result.warnings)} to review)")
        elif o.status == "failed":
            bus.emit("critic.flag", agent="ScriptWriter", issue=f"{o.day}: {o.note}")


# --- writer commands -----------------------------------------------------------

def cmd_doctor(run: Run) -> int:
    paths, ok = run.paths, True
    print(f"Profile:        {paths.root}")
    for label, p in [("Channel", paths.channel_file), ("Prompt", paths.prompt), ("Voice guide", paths.voice_guide),
                     ("Theme bank", paths.theme_bank), ("Script template", paths.script_template)]:
        exists = p.exists()
        ok &= exists
        print(f"{label + ':':<16}{'ok' if exists else 'MISSING'}  {p.name}")
    if not ok:
        return 1
    ch = run.channel
    print(f"Channel:        {ch.name} ({len(ch.pillars)} pillars, {ch.words_target} words, {ch.duration_s}s)")
    providers = available_providers()
    print(f"LLM keys:       {', '.join(providers) or 'none (use --provider mock, or set ANTHROPIC_API_KEY / GROQ_API_KEY)'}")
    if providers:
        print(f"Default writer: {get_provider().name}")
    if notion_sync.is_configured():
        print("Notion:         configured")
    elif env("NOTION_API_KEY"):
        print("Notion:         key set, but no database yet (run: acp notion-setup --parent-page <id>)")
    else:
        print("Notion:         off (scripts are saved as local files only)")
    skills = default_registry(load_providers(), verbose=False)
    print(f"Studio skills:  {', '.join(skills.active())}")
    print(f"Edit styles:    {', '.join(list_styles())}")
    print(f"ffmpeg:         {'found' if shutil.which('ffmpeg') else 'not found (EDL and render.sh only, no final encode)'}")
    bank = ThemeBank(paths.theme_bank)
    print(f"Unused ideas:   {', '.join(f'{p} {len(bank.unused(p))}' for p in ch.pillars)}")
    return 0


def cmd_themes(run: Run) -> int:
    bank = ThemeBank(run.paths.theme_bank)
    for code, pillar in run.channel.pillars.items():
        if run.args.pillar and code != run.args.pillar:
            continue
        unused = bank.unused(code)
        per_week = run.channel.weekly_rotation.count(code) or 1
        print(f"\n{pillar.label}: {len(unused)} unused (~{len(unused) // per_week} weeks at {per_week}/week)")
        for t in unused:
            print(f"  #{t.id:<3} {t.idea}" + (f"  [{t.source}]" if t.source else ""))
    return 0


def cmd_plan_week(run: Run) -> int:
    args = run.args
    start = args.start or next_monday(date.today())
    provider = None if args.dry_run else run.provider(args.provider)
    notion = None if args.dry_run else run.notion(not args.no_notion)
    print(f"Planning {args.days} days from {start} "
          f"({'dry run' if args.dry_run else f'writer: {provider.name}'}"
          f"{', Notion on' if notion else ''})\n")
    run.bus.emit("stage.enter", stage="script")
    outcomes = plan_week(run.paths, run.channel, provider, run.system_prompt(), start,
                         days=args.days, force=args.force, dry_run=args.dry_run, notion=notion)
    _emit_outcomes(run.bus, outcomes)
    written = [o for o in outcomes if o.status == "written"]
    failed = [o for o in outcomes if o.status == "failed"]
    print(f"\nDone: {len(written)} written, {len(failed)} failed, "
          f"{sum(o.status == 'skipped' for o in outcomes)} skipped.")
    for o in written:
        print(f"  {o.path.relative_to(run.paths.root)}")
    if written:
        print("\nNext: review each script out loud, verify the quotes, and set the status to Approved.")
    return 1 if failed else 0


def cmd_script(run: Run) -> int:
    args, paths, ch = run.args, run.paths, run.channel
    bank = ThemeBank(paths.theme_bank)
    day = args.date or date.today()
    theme = None
    if args.theme_id is not None:
        theme = bank.by_id(args.theme_id)
        if theme is None:
            print(f"No theme #{args.theme_id} in the theme bank.")
            return 1
        pillar, idea, source = theme.pillar, theme.idea, theme.source
    else:
        pillar, idea, source = args.pillar or ch.pillar_for(day), args.idea, args.source
    existing = existing_script(paths.scripts_dir, day)
    if existing and not args.force:
        print(f"{existing.name} already exists for {day}. Use --force to replace it.")
        return 1

    provider = run.provider(args.provider)
    print(f"Writing {day} {pillar} with {provider.name}: {idea}")
    run.bus.emit("stage.enter", stage="script")
    result = generate_script(
        provider, run.system_prompt(), ch, day=day, pillar=pillar, idea=idea, source=source,
        series=ch.series_for(pillar, source), theme_id=theme.id if theme else None,
    )
    path = write_script(paths, result, replace=existing, notion=run.notion(not args.no_notion))
    if theme:
        bank.mark_used(theme, day.isoformat())
        bank.save()
    run.bus.emit("agent.done", agent="ScriptWriter", result=f"{result.draft.working_title} ({result.draft.word_count()} words)")
    for w in result.warnings:
        print(f"  - {w}")
    print(f"Saved {path}")
    return 0


def cmd_suggest_ideas(run: Run) -> int:
    args = run.args
    bank = ThemeBank(run.paths.theme_bank)
    added = suggest_ideas(run.channel, run.provider(args.provider), run.system_prompt(), bank, args.pillar, args.count)
    bank.save()
    print(f"Added {len(added)} {args.pillar} ideas to {run.paths.theme_bank.name}:")
    for t in added:
        print(f"  #{t.id} {t.idea}" + (f"  [{t.source}]" if t.source else ""))
    print("Edit or delete any you don't like; the file is the source of truth.")
    return 0


def cmd_compare(run: Run) -> int:
    """Blind test: the same ideas written by Claude and by Groq, labelled A/B at random."""
    if set(available_providers()) != {"claude", "groq"}:
        print("compare needs both ANTHROPIC_API_KEY and GROQ_API_KEY.")
        return 1
    ch = run.channel
    bank = ThemeBank(run.paths.theme_bank)
    themes = []
    for code in ch.weekly_rotation:
        candidates = [t for t in bank.unused(code) if t not in themes]
        if candidates:
            themes.append(candidates[0])
        if len(themes) == run.args.n:
            break
    system = run.system_prompt()
    providers = {"claude": run.provider("claude"), "groq": run.provider("groq")}
    out = run.paths.compare_dir / datetime.now().strftime("%Y%m%d-%H%M")
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    day = next_monday(date.today())
    for i, theme in enumerate(themes, 1):
        labels = random.sample(["A", "B"], 2)
        key[f"sample-{i:02d}"] = dict(zip(labels, providers))
        for label, provider in zip(labels, providers.values()):
            print(f"sample {i} {label}: {theme.idea}")
            result = generate_script(provider, system, ch, day=day, pillar=theme.pillar, idea=theme.idea,
                                     source=theme.source, series=ch.series_for(theme.pillar, theme.source))
            text = render_markdown(result).replace(f"provider: {provider.name}", "provider: hidden")
            (out / f"sample-{i:02d}-{label}.md").write_text(text, encoding="utf-8")
    (out / "answer-key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"\nWrote {len(themes)} pairs to {out}.")
    print("Read each pair out loud, note which sounds more like you, then open answer-key.json.")
    return 0


def cmd_notion_setup(run: Run) -> int:
    database_id = notion_sync.create_content_database(notion_sync.client(), run.args.parent_page, run.channel)
    print(f"Created the '{run.channel.name} — Content' database: {database_id}")
    print(f"Add this line to .env:\nNOTION_CONTENT_DB_ID={database_id}")
    return 0


# --- studio commands -----------------------------------------------------------

def _studio_bus(project: Path, name: str, quiet: bool) -> tuple[EventBus, JsonlRecorder]:
    bus = EventBus()
    bus.subscribe(console_printer(quiet))
    rec = JsonlRecorder(str(project / name))
    bus.subscribe(rec)
    return bus, rec


def cmd_ingest(run: Run) -> int:
    args = run.args
    store = RecordStore(args.project)
    bus, rec = _studio_bus(Path(args.project), "ingest_events.jsonl", args.quiet)
    res = ingest_dir(args.media_dir, store, default_registry(load_providers()), bus, force=args.force)
    rec.close()
    print(json.dumps({"ingest": res, "library": store.counts()}, indent=2))
    return 0


def cmd_edit(run: Run) -> int:
    args = run.args
    if bool(args.brief) == bool(args.script):
        print("Give either a brief or --script <file>.")
        return 1
    if args.script:
        brief, overrides, style = edit_request(read_script(args.script), run.channel)
        s = Session(args.project, style=args.style or style, quiet=args.quiet)
        res = s.generate(brief, execute=not args.no_render, overrides=overrides)
    else:
        s = Session(args.project, style=args.style, quiet=args.quiet)
        res = s.generate(args.brief, execute=not args.no_render)
    _summary(res)
    return 0


def cmd_reedit(run: Run) -> int:
    args = run.args
    s = Session(args.project, style=args.style, quiet=args.quiet)
    # re-edit needs a prior request; re-derive from the instruction as a fresh brief if none
    s.generate(args.instruction, execute=False)
    _summary(s.re_edit(args.instruction, execute=not args.no_render))
    return 0


def cmd_status(run: Run) -> int:
    store = RecordStore(run.args.project)
    print(json.dumps({"library": store.counts(),
                      "assets": [{"name": a.source_name, "status": a.status, "dur": a.duration_s}
                                 for a in store.assets]}, indent=2))
    return 0


def cmd_reference(run: Run) -> int:
    args = run.args
    store = RecordStore(args.project)
    bus = EventBus()
    bus.subscribe(console_printer(args.quiet))
    ingest_dir(Path(args.ref_file).parent, store, default_registry(load_providers()), bus)
    a = max(store.assets, key=lambda a: a.analyzed_at or "")
    print(json.dumps({"style_spec": extract_style_spec(a, store.segments)}, indent=2))
    return 0


def cmd_styles(run: Run) -> int:
    for name in list_styles():
        print(name)
    return 0


def _summary(res: dict) -> None:
    edl = res["edl"]
    print("\n--- EDL ---")
    print(f"variant: {edl['variant_label']} | {edl['shot_count']} shots | {edl['total_duration_s']}s")
    for i, c in enumerate(edl["timeline"], 1):
        pair = f"  audio<-{Path(c['audio_from']).name}" if c.get("audio_from") else ""
        cap = f"  caption: {c['caption_text']!r}" if c.get("captions") else ""
        print(f"  {i:>2}. [{c['role']:<9}] {Path(c['source']).name:<26} {c['duration_s']}s{pair}{cap}")
        print(f"       reason: {c['reason']}")
    r = res["render"]
    print(f"\noutput: {r.get('output_path') or '(EDL + render script only) ' + r.get('render_script', '')}")
    if res.get("flags"):
        print("flags:", res["flags"])


# --- the whole pipeline ---------------------------------------------------------

def cmd_demo(run: Run) -> int:
    """Script -> footage -> edit, end to end, in a scratch workspace. Offline by default."""
    from content_pipeline.studio import sample_media

    args = run.args
    work = Path(args.workspace).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    # work on a copy so the demo never touches the real theme bank or scripts
    profile = work / "profile"
    shutil.copytree(run.paths.root, profile, ignore=shutil.ignore_patterns("scripts", "compare"))
    paths = Paths(profile)
    channel = load_channel(paths)

    bus = EventBus()
    bus.subscribe(console_printer(args.quiet))
    rec = JsonlRecorder(str(work / "events.jsonl"))
    bus.subscribe(rec)
    provider = get_provider(args.provider, on_usage=lambda u: bus.emit("llm.usage", **u))

    try:
        print("\n########## 1. WRITE: plan one day and write its script ##########")
        bus.emit("stage.enter", stage="script")
        day = next_monday(date.today())
        outcomes = plan_week(paths, channel, provider, build_system_prompt(paths, channel), day, days=1,
                             log=lambda m: None if args.quiet else print("  " + m))
        _emit_outcomes(bus, outcomes)
        written = [o for o in outcomes if o.status == "written"]
        if not written:
            print("No script was written; stopping.")
            return 1
        script = written[0].path

        print("\n########## 2. SHOOT: synthesize sample footage ##########")
        media = work / "media"
        sample_media.make(str(media))

        print("\n########## 3. INGEST: analyze once into media memory ##########")
        store = RecordStore(work / "project")
        res = ingest_dir(media, store, default_registry(load_providers(), verbose=False), bus)
        print(f"  ingest: {res} | library: {store.counts()}")

        print("\n########## 4. EDIT: the script becomes the brief ##########")
        brief, overrides, style = edit_request(read_script(script), channel)
        session = Session(str(work / "project"), style=style, quiet=args.quiet, bus=bus)
        result = session.generate(brief, execute=True, overrides=overrides)
        _summary(result)
    finally:
        rec.close()

    events = (work / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    dashboard = work / "dashboard.html"
    dashboard.write_text(embed_events(DASHBOARD.read_text(encoding="utf-8"), events), encoding="utf-8")
    print(f"\nDONE in {work}")
    print(f"  script     {script.relative_to(work)}")
    print("  edl        project/renders/latest/edl.json")
    print(f"  events     events.jsonl ({len(events)} events)")
    print(f"  dashboard  open {dashboard}")
    return 0


def embed_events(html: str, events: list[str]) -> str:
    """Swap the dashboard's embedded sample run for a real one, so the file opens offline."""
    start, end = html.index("/*EVENTS*/"), html.index("/*END_EVENTS*/")
    return html[:start] + "/*EVENTS*/[\n" + ",\n".join(events) + "\n]" + html[end:]


# --- parser ------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", help="channel profile name or folder (default: $ACP_PROFILE or thahrav)")
    common.add_argument("--quiet", action="store_true")
    common.add_argument("--events", help="also record this run's events to a JSONL file")

    parser = argparse.ArgumentParser(prog="acp", description="AI content pipeline: scripts in your voice, edited into shorts.")
    parser.add_argument("--version", action="version", version=f"acp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name: str, help: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help, parents=[common])

    add("doctor", "check setup: profile files, keys, skills, ffmpeg, ideas left")

    p = add("themes", "list unused ideas per pillar")
    p.add_argument("--pillar")

    p = add("plan-week", "write a week of scripts (default: next Monday to Sunday)")
    p.add_argument("--start", type=_date, help="first day, YYYY-MM-DD")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--provider", choices=["auto", *PROVIDERS])
    p.add_argument("--force", action="store_true", help="rewrite days that already have a script")
    p.add_argument("--dry-run", action="store_true", help="show which ideas would be used, without calling the LLM")
    p.add_argument("--no-notion", action="store_true")

    p = add("script", "write one script")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--theme-id", type=int, help="an idea number from the theme bank")
    src.add_argument("--idea", help="a free-text idea")
    p.add_argument("--pillar", help="with --idea; default is the day's pillar")
    p.add_argument("--source", help="with --idea: a source to verify")
    p.add_argument("--date", type=_date, help="post date, YYYY-MM-DD (default today)")
    p.add_argument("--provider", choices=["auto", *PROVIDERS])
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-notion", action="store_true")

    p = add("suggest-ideas", "add new LLM-suggested ideas to the theme bank")
    p.add_argument("--pillar", required=True)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--provider", choices=["auto", *PROVIDERS])

    p = add("compare", "blind test: Claude vs Groq on the same ideas")
    p.add_argument("--n", type=int, default=5, help="number of ideas (max 7)")

    p = add("notion-setup", "create the Notion Content database")
    p.add_argument("--parent-page", required=True, help="ID of a Notion page shared with your integration")

    p = add("ingest", "analyze a media folder once into a project's memory (incremental)")
    p.add_argument("media_dir")
    p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true", help="re-analyze clips that are already known")

    p = add("edit", "plan and render a short from memory, from a brief or a script")
    p.add_argument("project")
    p.add_argument("brief", nargs="?", help='e.g. "motivational short, 10 shots in 30s"')
    p.add_argument("--script", help="a script written by `acp script` / `acp plan-week`")
    p.add_argument("--style", help="edit style from config/styles (default: from the brief or the channel)")
    p.add_argument("--no-render", action="store_true")

    p = add("reedit", "re-plan the last edit with an instruction")
    p.add_argument("project")
    p.add_argument("instruction", help='e.g. "make the opening punchier"')
    p.add_argument("--style")
    p.add_argument("--no-render", action="store_true")

    p = add("status", "show a project's media library")
    p.add_argument("project")

    p = add("reference", "extract a style spec from a reference video")
    p.add_argument("project")
    p.add_argument("ref_file")

    add("styles", "list edit styles")

    p = add("demo", "run the whole pipeline offline: write a script, synthesize footage, ingest, edit")
    p.add_argument("--workspace", default="demo_run")
    p.add_argument("--provider", choices=["auto", *PROVIDERS], default="mock")
    return parser


COMMANDS = {
    "doctor": cmd_doctor, "themes": cmd_themes, "plan-week": cmd_plan_week, "script": cmd_script,
    "suggest-ideas": cmd_suggest_ideas, "compare": cmd_compare, "notion-setup": cmd_notion_setup,
    "ingest": cmd_ingest, "edit": cmd_edit, "reedit": cmd_reedit, "status": cmd_status,
    "reference": cmd_reference, "styles": cmd_styles, "demo": cmd_demo,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run = Run(args)
    try:
        return COMMANDS[args.command](run)
    except (LLMError, ValueError, RuntimeError) as e:
        print(f"Error: {e}")
        return 1
    finally:
        run.close()
