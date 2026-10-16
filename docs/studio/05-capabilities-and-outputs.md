# What This Workflow Can Do — Capabilities & Output Expectations

A grounded look at what the pipeline produces, what to realistically expect
from each step, and where the honest limits are. Read every claim through
**two lenses**:

- **As-shipped** — mock/heuristic perception, runs offline with no API keys.
  The edit *logic* is real and tested; the perceptual *judgments* are
  simulated (scores derived from filename hints + cheap ffmpeg signals).
- **With real models** — you swap perception skills for hosted/self-hosted
  models (one line in `config/providers.json`). The output's **shape stays
  identical**; only the **quality of selection and tagging improves**.

So: as-shipped proves the machinery end-to-end and produces a real,
correctly-assembled vertical video; real models make the *choices* smart.

---

## 1. What the whole workflow does

Dump media in any format → it's analyzed **once** and remembered → you ask
in plain language → it retrieves the best parts from memory (no
re-analysis), plans an edit, and renders a vertical short — with a live
dashboard of every step and a conversational re-edit loop.

Concretely it can:

- Ingest a folder of clips, normalize them, and build a durable, searchable
  memory — analyzing only **new** files on re-ingest (incremental).
- Take a brief ("motivational short, 10 shots in 30s, build to a peak") and
  return a structured edit plan plus a rendered `output.mp4`.
- Handle **asymmetric clips**: keep a great spoken line's audio over a
  great-visuals clip's footage (the bike case), instead of discarding both.
- Sequence a **build-to-peak arc** with heroes as a staircase and a longer
  finale, place an opening hook, and pair soundbites with covering B-roll.
- Critique its own cut (duration, hook timing, jump-cuts) and revise once.
- Re-edit from a follow-up instruction ("punchier opening") without
  re-analyzing media.
- Extract a **style spec** from a reference video to target its pacing/shot
  grammar with your own footage.
- Stream every agent/stage as events that drive the live dashboard.

---

## 2. What you get out (concrete artifacts)

Every run writes real files under the project directory:

| Artifact | What it is | Where |
|---|---|---|
| `assets.json` | One durable record per source file (hash, proxy, duration, status, skill versions) | `<project>/` |
| `segments.json` | Per-segment memory records: per-modality scores, tags, transcript, roles, embedding | `<project>/` |
| `events.jsonl` | The run's event stream (stages, agents, pairings, render) — feeds the dashboard | `<project>/` |
| `ingest_events.jsonl` | Ingest stream (scan, analyzing, skip, analyzed) | `<project>/` |
| `edl.json` | The **edit decision list** — the full plan: shots, in/out, role, reason, captions, reframe, audio pairing | `<project>/renders/<name>/` |
| `render.sh` | Reproducible ffmpeg script for the whole cut | `<project>/renders/<name>/` |
| `seg_NN.mp4` | Per-shot rendered intermediates (reframed 9:16) | `<project>/renders/<name>/` |
| `output.mp4` | **The finished vertical short** (1080×1920, target duration) | `<project>/renders/<name>/` |

`edl.json` is the most useful artifact to read — it's human-inspectable and
carries a `reason` on every shot (the audit trail behind every choice).

---

## 3. Realistic expectations — the honest version

**As-shipped, you will get:**
- A real `output.mp4` at 1080×1920, at (or within ~15% of) the requested
  duration and shot count, correctly assembled: trimmed segments, 9:16
  reframe, soundbite audio laid over B-roll visuals, muted B-roll, concat,
  per-shot intermediates, and a reproducible `render.sh`.
- A correct **structure**: hook first, hero staircase, hero finale (longest),
  soundbites paired with distinct covering B-roll, no adjacent duplicate
  sources, captions wired on soundbites, critics' flags and a revise pass.
- On the **synthetic demo clips**, the video looks like colored cards with
  tones — because the inputs are synthetic and the perception is mock. The
  *machinery* is what's being demonstrated, not the footage.

**With real models swapped in, you can realistically expect:**
- Selection quality tracking your provider. On structured content
  (talking-head, gameplay, tutorials) highlight selection lands near
  human picks (~85–93% per the build-playbook); on cinematic/mood-driven
  footage it's weaker and needs more human-in-the-loop.
- Real transcripts, real shot/scene boundaries, real visual tags and
  on-screen text, and embeddings that make semantic retrieval ("uplifting
  summit moment") genuinely work.
- A short that, on real footage, is a real publishable first draft — not a
  finished edit you'd never touch, but a strong starting point.

**What it will NOT do (current limits):**
- It is **not a generative video model** — it selects and arranges *your*
  footage; it never invents new frames.
- **No true beat-synced cutting yet** — music is a named bed and ducking
  level, not transient-aligned cuts.
- **Reframe is a crop strategy, not learned subject tracking** — fast-moving
  subjects on vertical crop need a real tracking model swapped in.
- **Captions are wired but burn-in is basic** — styling/animation is minimal.
- **Music is a label, not a licensed track** — you must connect a licensed
  library; nothing is cleared for you.
- **No GUI app** — you drive it via CLI + the conversational session; the
  dashboard is a read-only live view (the design for a full Studio UI is in
  `docs/03-studio-memory-and-ux.md`).
- **Audio "noise vs vibe" discrimination is shallow** — distinguishing
  pleasant ambient from bad wind needs a real audio model.

---

## 4. Capabilities & outputs, step by step

### Step 1 — Ingest & normalize
- **Capability:** probe each file, transcode to a standard 9:16-friendly
  working proxy, keep the original. Any container/codec in.
- **Output:** an `Asset` record (`asset_id`, duration, proxy path, status).
- **Expectation:** robust with ffmpeg present; without ffmpeg it falls back
  to the original file and zero-duration (degraded but won't crash).

### Step 2 — Fingerprint & diff (analyze-once + incremental)
- **Capability:** content hash = identity → dedup; diff new hashes against
  the registry → analyze only genuinely new files.
- **Output:** `new` / `skipped` counts; only new assets proceed.
- **Expectation:** exact and reliable — this is fully real (not mock) and
  unit-tested. Re-ingesting a folder with one added clip analyzes exactly
  that one.

### Step 3 — Perception analysis
- **Capability:** per clip — scene/shot boundaries, visual quality +
  aesthetic + motion + shot type, audio quality + noise type + loudness,
  speech value + transcript, emotion/theme, and an embedding.
- **Output:** `Segment` records with a `scores` dict (every modality
  **kept separate**), `tags`, `transcript`, `embedding`.
- **Expectation:** *as-shipped* these are plausible but simulated (hint
  tokens + real loudness/scene signals). *With real models* (TwelveLabs,
  Whisper, CLIP/SigLIP, Deepgram) these become genuine measurements. The
  record shape is identical either way.

### Step 4 — Memory records + index
- **Capability:** persist records; build vector + metadata + fulltext views.
- **Output:** `segments.json` on disk; an in-memory index for query.
- **Expectation:** fully real. Reopening a project never re-analyzes.

### Step 5 — Retrieval (query without re-analysis)
- **Capability:** turn a brief into a ranked candidate set combining
  semantic similarity + emotion + usability + visual quality.
- **Output:** ranked `Candidate`s with a score breakdown.
- **Expectation:** real ranking logic; *quality* depends on embedding
  quality (crude hashed embeddings as-shipped → strong with a real embedder).
  Themed clips reliably outrank off-theme ones (unit-tested).

### Step 6 — Role classification ("Casting")
- **Capability:** assign each segment roles — hero / B-roll / soundbite /
  discard — from independent per-modality scores.
- **Output:** `roles` on each segment; a role census event.
- **Expectation:** fully real and tested, including the key guarantee that
  an asymmetric clip (great visual / weak audio) is **never discarded**.

### Step 7 — Director planning (pairing + EDL + arc)
- **Capability:** build a build-to-peak timeline — hero staircase, longer
  finale, opening hook, soundbites paired over covering B-roll, no adjacent
  duplicate sources; honor target shots/duration.
- **Output:** a complete `Edl` with per-shot `reason`, captions/reframe
  flags, and audio-pairing fields; `pairings` recorded.
- **Expectation:** fully real and the core differentiator. Structure quality
  is genuine now; *which* clips fill the slots gets smart with real scores.

### Step 8 — Production (reframe, captions, music)
- **Capability:** set per-shot reframe strategy, caption text from
  transcript, music bed + duck level.
- **Output:** EDL fields populated; produce events.
- **Expectation:** directives are real and applied at render; the underlying
  models (subject tracking, caption styling, licensed music) are
  placeholders to swap in.

### Step 9 — Critique + revise
- **Capability:** PlatformCritic (duration, hook, shot count) and
  CutQualityCritic (jump-cuts, too-short shots) flag issues; director
  rescales once to better hit target.
- **Output:** `flags` list; a revised EDL if needed.
- **Expectation:** fully real and working — it genuinely catches jump-cuts
  and off-target durations and re-plans.

### Step 10 — Render (EDL → output.mp4)
- **Capability:** per-shot trim + 9:16 reframe + chosen audio (own / paired
  soundbite / muted), then concat; always writes `edl.json` + `render.sh`.
- **Output:** `output.mp4` (1080×1920), `seg_NN.mp4`, `render.sh`.
- **Expectation:** fully real with ffmpeg. Produces an actual playable
  vertical video at the target duration. Without ffmpeg it still writes the
  EDL + script (no mp4).

### Step 11 — Conversational session (brief → generate → re-edit)
- **Capability:** parse a natural-language brief (shots, duration, genre,
  platform); generate; re-edit from a follow-up ("punchier", "longer",
  "N shots") by adjusting the request and re-planning.
- **Output:** result dict (EDL, render, candidates, pairings, flags).
- **Expectation:** real, simple NLU (keyword/number parsing). A real LLM in
  this slot would handle arbitrary phrasing; today it understands the common
  patterns.

### Step 12 — Reference extraction (style spec)
- **Capability:** analyze a reference video and derive a style spec — shot
  count, avg shot length, arc, shot grammar, dominant theme, speech ratio.
- **Output:** a `style_spec` JSON the director can target.
- **Expectation:** real extraction from real measurements; richness scales
  with the perception models behind it (e.g., true shot-type labels, OCR'd
  on-screen text, color grade) once swapped in.

### Step 13 — Live dashboard
- **Capability:** replay the event stream — stages lighting up, agent
  activity, soundbite↔B-roll pairings, render result.
- **Output:** a single-file `dashboard/index.html` view.
- **Expectation:** real, fed by actual run events. It's a read-only monitor
  today, not the interactive editing IDE (that's the Phase-3 design).

---

## 5. Realistic selection quality by footage type (with real models)

| Footage type | Highlight selection | Notes |
|---|---|---|
| Talking-head / podcast / course | ~90%+ | transcript + speech signals are strong |
| Gameplay / streams / sports | ~85–90% | clear audio/visual engagement peaks |
| Bike POV / vlogs / events | mixed | great for B-roll + paired soundbites; emotional beats are harder |
| Cinematic / mood-driven | weaker | needs human-in-the-loop; assist, don't automate |

These track the provider you choose; treat them as planning estimates, not
guarantees, and validate on your own footage (see
`docs/04-roadmap-and-validation.md`).

---

## 6. One real run, end to end (from the demo)

Brief: *"motivational short, 10 shots in 30s, build to a peak."* Output:

```
build-to-peak: 10 shots / 30.0s   →  output.mp4 (1080×1920)
  1. [b_roll   ] opening hook — strongest visual to stop the scroll
  2. [soundbite] strong spoken line over covering B-roll   audio←(another clip)
  3. [b_roll   ] muted, music bed carries it
  4. [soundbite] strong spoken line over covering B-roll   audio←(another clip)
  5. [hero     ] hero beat — re-lifts momentum on the staircase
  6–9 [b_roll  ] muted B-roll, varied sources
  10.[hero     ] closing summit — strongest hero, longest hold
pairings: 2   flags: none   render: output.mp4 ✓
```

The same project, asked "make the opening punchier," re-plans to ~12 tighter
shots without touching the media again.

---

## 7. Command → output quick reference

| Command | Produces |
|---|---|
| `ingest <media> --project <p>` | `assets.json`, `segments.json`, index, `ingest_events.jsonl` |
| `generate <p> "<brief>"` | `edl.json`, `render.sh`, `output.mp4`, `events.jsonl` |
| `reedit <p> "<instruction>"` | a revised `edl.json` + `output.mp4` |
| `status <p>` | library counts + per-asset status |
| `reference <p> <ref.mp4>` | a `style_spec` JSON |

---

### Bottom line

What you can rely on **today**: a working end-to-end pipeline that remembers
media, retrieves and plans a structured build-to-peak short, handles
asymmetric clips, critiques and re-edits itself, and renders a real vertical
`output.mp4` — all offline, all inspectable. What you **add** to make the
*choices* genuinely good: real perception models in the swap slots. The
machinery is done; the intelligence is a configuration change away.
