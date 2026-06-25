# AI Video Studio

A reference implementation of a **chat-driven, agentic short-form video
editor**: dump media in any format, it analyzes each clip once and
remembers it, then you ask in plain language ("motivational short, 10
shots in 30s, build to a peak") and it retrieves the best parts from
memory, plans an edit, and renders a vertical short — while a live
dashboard shows every agent and stage as it happens.

It is built to the plan in [`docs/`](docs/). The whole pipeline runs
**end-to-end with zero network and zero ML weights** using mock/heuristic
perception adapters, so you can validate edit quality first and swap in
hosted or self-hosted models one capability at a time.

```
media dump ─► fingerprint & diff ─► analyze once ─► memory index
                                                          │
   chat brief ─► retrieve (no re-analysis) ─► director ─► EDL ─► render ─► output.mp4
                         classify roles + pair soundbites↔B-roll
                                   critics ⟲ revise
```

## Why it's structured this way

- **Analyze once, query forever.** A content hash is identity → dedup +
  incremental diff (re-ingesting only analyzes genuinely new clips).
  Every later request is a query over the index, never a re-scan.
- **Never blend the modalities.** Each clip is scored per-axis (visual,
  audio, speech, emotion). The director assigns a *role* — hero, B-roll,
  soundbite — and **pairs** a soundbite's audio over a B-roll's visuals,
  so a great-visuals/bad-audio bike clip and a great-line/ugly clip
  combine into one strong segment instead of both being discarded.
- **Skills are swappable adapters.** `mock → hosted → self-hosted` is a
  config change (`config/providers.json`); agents and the orchestrator
  never change.
- **The dashboard views real state.** Agents emit to an event bus; the
  dashboard replays it. The view is the control surface, not a fake bar.

## Quickstart

Requires Python 3.10+ and (optionally) ffmpeg for real rendering.

```bash
# run the full demo: synth media → ingest → incremental → generate → re-edit → render
python examples/run_demo.py

# or use the CLI on your own footage
PYTHONPATH=src python -m aivstudio.cli ingest   /path/to/media --project ./proj
PYTHONPATH=src python -m aivstudio.cli generate ./proj "motivational short, 10 shots in 30s" --profile motivational
PYTHONPATH=src python -m aivstudio.cli status   ./proj

# tests (core logic: fingerprint, incremental, roles, pairing, retrieval)
PYTHONPATH=src python -m unittest discover -s tests
```

Outputs land under `<project>/renders/latest/`: `edl.json`, `render.sh`,
and `output.mp4` (1080×1920). Run events stream to
`<project>/events.jsonl`.

### Whole-clip memory (windowing)

Long clips are sliced into multiple timestamped segments (every ~4s of any
span over 6s) and **each window is scored independently** — so a clip with a
fun start, a motivating middle, and a sad ending becomes several retrievable
records, not one. Each window gets its own visual/audio/speech/emotion
scores, so the editor can pull the right *moment* from any clip. The
director also spreads shots across different source clips for variety.

### Re-ingesting after you change analysis logic

Ingest is incremental: a clip already analyzed is cached and skipped. If you
change the perception/segmentation logic (or turn on a remote service) and
want existing clips re-analyzed, use `--force`:

```bash
PYTHONPATH=src python -m aivstudio.cli ingest /path/to/clips --project ./proj --force
```

Or set any API key **before** the first ingest so analysis is live from the
start.

## Live dashboard

Open `dashboard/index.html` in a browser. It auto-loads a co-located
`events.jsonl` (or the embedded sample) and replays the run — pipeline
stages lighting up, agent activity, soundbite↔B-roll pairings, and the
render result. Use "load events.jsonl" to point it at a real run's file.

## Repository layout

```
src/aivstudio/
  memory/        ingest (analyze-once + diff), records, store, index, fingerprint
  skills/        Skill interface + registry; mock perception/production/render adapters
  agents/        Agent interface; Director (roles + pairing); critics
  blackboard.py  shared run state
  retrieval.py   brief → ranked candidates from memory
  reference.py   reference video → style spec
  orchestrator.py  retrieve→classify→plan→produce→critique→revise→render
  session.py     parse NL brief, generate, re-edit
  events.py      event bus + JSONL recorder (dashboard feed)
  cli.py / config.py / edl.py / text.py
config/          providers.json (active impls) + genre profiles
dashboard/       single-file live run dashboard
examples/        run_demo.py (full end-to-end)
scripts/         make_sample_media.py
tests/           unit tests for the validated core
docs/            the four planning docs this repo implements
```

## Swapping in real models

Each capability is a `Skill` with a typed contract. To go from mock to
real: implement the same interface (e.g. a `WhisperTranscriber`,
`SiglipVisualQuality`, `TwelveLabsEmbed`), register it, and point
`config/providers.json` at its name. Recommended swap order (cheapest
first): scene detection → transcription → embeddings → visual quality →
speech. See `docs/01-build-playbook.md` for provider options and costs.

## Status

This is a validation-stage scaffold (Phase 0/1 in
`docs/04-roadmap-and-validation.md`), not a production service. The edit
*logic* is real and tested; perception is mock by design so you can
prove quality before paying for analysis. See the roadmap for what to
settle before scaling.
