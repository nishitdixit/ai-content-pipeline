"""Command line: `thahrav <command>`. Run `thahrav -h` for the list."""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime

from thahrav import notion_sync
from thahrav.config import Paths, env, hindi_verb_form, project_paths
from thahrav.llm import LLMError, available_providers, get_provider
from thahrav.pillars import PILLARS, WEEKLY_ROTATION, pillar_for, series_for
from thahrav.plan import next_monday, plan_week, suggest_ideas, write_script
from thahrav.prompts import build_system_prompt
from thahrav.render import existing_script, render_markdown
from thahrav.scriptgen import generate_script
from thahrav.themes import ThemeBank


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _system_prompt(paths: Paths) -> str:
    return build_system_prompt(paths, hindi_verb_form())


def _notion(enabled: bool):
    if not enabled or not notion_sync.is_configured():
        return None
    return notion_sync.NotionMirror()


def cmd_doctor(args, paths: Paths) -> int:
    ok = True
    print(f"Project root:   {paths.root}")
    for label, p in [("Voice guide", paths.voice_guide), ("Theme bank", paths.theme_bank), ("Script template", paths.script_template)]:
        exists = p.exists()
        ok &= exists
        print(f"{label + ':':<16}{'ok' if exists else 'MISSING'}  {p.relative_to(paths.root)}")
    providers = available_providers()
    print(f"LLM keys:       {', '.join(providers) or 'NONE (set ANTHROPIC_API_KEY or GROQ_API_KEY)'}")
    ok &= bool(providers)
    if providers:
        print(f"Default writer: {get_provider().name}")
    print(f"Hindi verbs:    {hindi_verb_form()}")
    if notion_sync.is_configured():
        print("Notion:         configured")
    elif env("NOTION_API_KEY"):
        print("Notion:         key set, but no database yet (run: thahrav notion-setup --parent-page <id>)")
    else:
        print("Notion:         off (scripts are saved as local files only)")
    if paths.theme_bank.exists():
        bank = ThemeBank(paths.theme_bank)
        counts = ", ".join(f"{p} {len(bank.unused(p))}" for p in PILLARS)
        print(f"Unused ideas:   {counts}")
    return 0 if ok else 1


def cmd_themes(args, paths: Paths) -> int:
    bank = ThemeBank(paths.theme_bank)
    for code, pillar in PILLARS.items():
        if args.pillar and code != args.pillar:
            continue
        unused = bank.unused(code)
        per_week = WEEKLY_ROTATION.count(code)
        print(f"\n{code} {pillar.name}: {len(unused)} unused (~{len(unused) // per_week} weeks at {per_week}/week)")
        for t in unused:
            print(f"  #{t.id:<3} {t.idea}" + (f"  [{t.source}]" if t.source else ""))
    return 0


def cmd_plan_week(args, paths: Paths) -> int:
    start = args.start or next_monday(date.today())
    provider = None if args.dry_run else get_provider(args.provider)
    notion = None if args.dry_run else _notion(not args.no_notion)
    print(f"Planning {args.days} days from {start} "
          f"({'dry run' if args.dry_run else f'writer: {provider.name}'}"
          f"{', Notion on' if notion else ''})\n")
    outcomes = plan_week(
        paths, provider, _system_prompt(paths), start,
        days=args.days, force=args.force, dry_run=args.dry_run, notion=notion,
    )
    written = [o for o in outcomes if o.status == "written"]
    failed = [o for o in outcomes if o.status == "failed"]
    print(f"\nDone: {len(written)} written, {len(failed)} failed, "
          f"{sum(o.status == 'skipped' for o in outcomes)} skipped.")
    for o in written:
        print(f"  {o.path.relative_to(paths.root)}")
    if written:
        print("\nNext: review each script out loud, verify the quotes, and set the status to Approved.")
    return 1 if failed else 0


def cmd_script(args, paths: Paths) -> int:
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
        pillar, idea, source = args.pillar or pillar_for(day), args.idea, args.source
    existing = existing_script(paths.scripts_dir, day)
    if existing and not args.force:
        print(f"{existing.name} already exists for {day}. Use --force to replace it.")
        return 1

    provider = get_provider(args.provider)
    print(f"Writing {day} {pillar} with {provider.name}: {idea}")
    result = generate_script(
        provider, _system_prompt(paths), day=day, pillar=pillar, idea=idea, source=source,
        series=series_for(pillar, source), theme_id=theme.id if theme else None,
    )
    path = write_script(paths, result, replace=existing, notion=_notion(not args.no_notion))
    if theme:
        bank.mark_used(theme, day.isoformat())
        bank.save()
    for w in result.warnings:
        print(f"  - {w}")
    print(f"Saved {path.relative_to(paths.root)}")
    return 0


def cmd_suggest_ideas(args, paths: Paths) -> int:
    bank = ThemeBank(paths.theme_bank)
    provider = get_provider(args.provider)
    added = suggest_ideas(provider, _system_prompt(paths), bank, args.pillar, args.count)
    bank.save()
    print(f"Added {len(added)} {args.pillar} ideas to {paths.theme_bank.name}:")
    for t in added:
        print(f"  #{t.id} {t.idea}" + (f"  [{t.source}]" if t.source else ""))
    print("Edit or delete any you don't like; the file is the source of truth.")
    return 0


def cmd_compare(args, paths: Paths) -> int:
    """Blind test (roadmap task 1.4): the same ideas written by both providers, labelled A/B at random."""
    if set(available_providers()) != {"claude", "groq"}:
        print("compare needs both ANTHROPIC_API_KEY and GROQ_API_KEY.")
        return 1
    bank = ThemeBank(paths.theme_bank)
    themes = []
    for code in WEEKLY_ROTATION:
        candidates = [t for t in bank.unused(code) if t not in themes]
        if candidates:
            themes.append(candidates[0])
        if len(themes) == args.n:
            break
    system = _system_prompt(paths)
    providers = {"claude": get_provider("claude"), "groq": get_provider("groq")}
    out = paths.compare_dir / datetime.now().strftime("%Y%m%d-%H%M")
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    day = next_monday(date.today())
    for i, theme in enumerate(themes, 1):
        labels = random.sample(["A", "B"], 2)
        key[f"sample-{i:02d}"] = dict(zip(labels, providers))
        for label, provider in zip(labels, providers.values()):
            print(f"sample {i} {label}: {theme.idea}")
            result = generate_script(provider, system, day=day, pillar=theme.pillar, idea=theme.idea,
                                     source=theme.source, series=series_for(theme.pillar, theme.source))
            text = render_markdown(result).replace(f"provider: {provider.name}", "provider: hidden")
            (out / f"sample-{i:02d}-{label}.md").write_text(text, encoding="utf-8")
    (out / "answer-key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"\nWrote {len(themes)} pairs to {out.relative_to(paths.root)}.")
    print("Read each pair out loud, note which sounds more like you, then open answer-key.json.")
    print("Record the result as a decision in docs/10-decisions-and-risks.md.")
    return 0


def cmd_notion_setup(args, paths: Paths) -> int:
    database_id = notion_sync.create_content_database(notion_sync.client(), args.parent_page)
    print(f"Created the 'Thahrav — Content' database: {database_id}")
    print(f"Add this line to engine/.env:\nNOTION_CONTENT_DB_ID={database_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thahrav", description="Thahrav content engine")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check setup: files, keys, Notion, ideas left")

    p = sub.add_parser("themes", help="list unused ideas per pillar")
    p.add_argument("--pillar", choices=list(PILLARS))

    p = sub.add_parser("plan-week", help="write a week of scripts (default: next Monday to Sunday)")
    p.add_argument("--start", type=_date, help="first day, YYYY-MM-DD")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--provider", choices=["auto", "claude", "groq"])
    p.add_argument("--force", action="store_true", help="rewrite days that already have a script")
    p.add_argument("--dry-run", action="store_true", help="show which ideas would be used, without calling the LLM")
    p.add_argument("--no-notion", action="store_true")

    p = sub.add_parser("script", help="write one script")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--theme-id", type=int, help="an idea number from the theme bank")
    src.add_argument("--idea", help="a free-text idea")
    p.add_argument("--pillar", choices=list(PILLARS), help="with --idea; default is the day's pillar")
    p.add_argument("--source", help="with --idea: a source to verify")
    p.add_argument("--date", type=_date, help="post date, YYYY-MM-DD (default today)")
    p.add_argument("--provider", choices=["auto", "claude", "groq"])
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-notion", action="store_true")

    p = sub.add_parser("suggest-ideas", help="add new LLM-suggested ideas to the theme bank")
    p.add_argument("--pillar", choices=list(PILLARS), required=True)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--provider", choices=["auto", "claude", "groq"])

    p = sub.add_parser("compare", help="blind test: Claude vs Groq on the same ideas")
    p.add_argument("--n", type=int, default=5, help="number of ideas (max 7)")

    p = sub.add_parser("notion-setup", help="create the Notion Content database")
    p.add_argument("--parent-page", required=True, help="ID of a Notion page shared with your integration")
    return parser


COMMANDS = {
    "doctor": cmd_doctor,
    "themes": cmd_themes,
    "plan-week": cmd_plan_week,
    "script": cmd_script,
    "suggest-ideas": cmd_suggest_ideas,
    "compare": cmd_compare,
    "notion-setup": cmd_notion_setup,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, project_paths())
    except (LLMError, ValueError, RuntimeError) as e:
        print(f"Error: {e}")
        return 1
