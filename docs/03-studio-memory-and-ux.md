# Studio — Memory, Reference Extraction & Conversational UX Plan

The third companion doc. The agentic engine (perception agents, director, skills, critics on a blackboard) is the brain. This is the body the user actually touches: a persistent media memory, a reference-extraction path, a live dashboard, and a chat-driven session model that needs zero coding.

---

## 1. Three new layers

1. **Media memory** — dump anything in any format; it's analyzed once and remembered forever. Later requests are *queries*, not re-scans.
2. **Conversational orchestration** — you describe what you want; the system interrogates requirements, plans, and delegates to agents. No code, no timeline-scrubbing required.
3. **Live Studio** — a dashboard that streams the state of every task/agent/skill so you always see what's happening and can intervene.

---

## 2. Media memory — analyze once, query forever

The governing rule: **analysis is expensive and permanent; retrieval is cheap and instant.** Pay analysis cost once per clip; serve unlimited requests from the index.

### 2.1 Universal ingest
Accept any container/codec. On ingest, normalize: probe with FFprobe, transcode to a working proxy (e.g. H.264 + standardized audio) while keeping the original, extract a keyframe thumbnail track. The rest of the pipeline only ever sees normalized proxies, so "any format" is solved at the door.

### 2.2 Content fingerprinting (dedup + diff)
Hash every file (content hash, e.g. SHA-256) and compute a perceptual hash of the video. The content hash is the asset's identity. This gives you, for free:
- **Dedup** — the same clip dumped twice is stored once.
- **Incremental diff** — when new media arrives, hash it and compare against the registry of known hashes. Only unknown hashes proceed to analysis. This is exactly how "I added more clips later → it analyzes just the new ones" works.

### 2.3 Analyze-once pipeline
New (unknown-hash) assets run through the perception skills once: scene/shot segmentation, transcription, visual quality + aesthetic + shot-type tags, on-screen text (OCR), faces/emotion, motion/action peaks, audio quality + noise type, beats, embeddings. The output is written as durable **memory records** (schemas below), not held in RAM. Re-opening the project never re-analyzes.

### 2.4 The index (what makes retrieval instant)
Three stores over the same records:
- **Vector store** — per-segment embeddings (visual, text, and audio) for semantic search ("uplifting summit moment", "quiet reflective line").
- **Structured metadata store** — scores, tags, shot types, durations, roles, flags — for filtering ("≥0.8 visual, has speech, < 4s, shot_type = wide").
- **Full-text store** — transcripts + OCR text — for keyword/quote search.

A request like *"motivational short, 10 shots, 30s"* becomes: semantic search for motivational beats + filter by duration/quality + rank, all over the index — no clip is re-opened. The director then plans from the returned candidates.

### 2.5 Incremental watcher
A watcher (folder watch or upload hook) fires on new files → fingerprint → diff → enqueue only the unknown ones → analyze → write records → index updates. Status flows to the dashboard ("2 new · analyzing 1/2"). Everything already known is untouched.

### 2.6 Memory record schemas

```json
// Asset record (one per file)
{
  "asset_id": "a_9f3",
  "content_hash": "sha256:…",
  "phash": "…",
  "source_name": "gopro_clip2.mp4",
  "original_path": "store://orig/a_9f3",
  "proxy_path": "store://proxy/a_9f3.mp4",
  "duration_s": 184.0,
  "status": "analyzed",            // queued | analyzing | analyzed | failed
  "analyzed_at": "2026-06-24T…",
  "skill_versions": { "visual": "1.4.0", "audio": "1.1.0", "speech": "2.0.1" }
}
```

```json
// Segment record (many per asset) — the queryable unit
{
  "seg_id": "a_9f3:s_014",
  "asset_id": "a_9f3",
  "in": 132.4, "out": 141.0,
  "scores": { "visual_quality": 0.91, "aesthetic": 0.88, "motion": 0.74,
              "audio_quality": 0.21, "speech_value": 0.05, "emotion": 0.30 },
  "shot_type": "wide_landscape",
  "tags": ["coastline", "sunrise", "no_speech", "wind_noise"],
  "transcript": "",
  "ocr_text": "",
  "roles": ["b_roll", "hero_visual"],
  "embeddings": { "visual": "vec://…", "text": "vec://…" }
}
```

---

## 3. Reference-media extraction → a style spec

When the user uploads a reference video ("make something like this"), it goes through the *same* analyze-once pipeline plus a deeper extraction pass that produces a **style spec** — a structured description of what makes the reference work, which becomes a target the director optimizes toward.

Extracted:
- **Theme / mood** — semantic summary, emotional arc.
- **On-screen text** — every caption/title, its timing, position, and style.
- **Shot grammar** — shot types and their order (e.g. wide → detail → face → wide), average shot length, cut density.
- **Pacing** — cuts per second, build-up curve, where the peak lands.
- **Audio profile** — music vs speech ratio, beat-sync behavior, loudness.
- **Color / look** — palette, grade character.
- **Structure** — hook style, body, payoff/CTA.

```json
{
  "style_spec_id": "ref_motivation_01",
  "duration_s": 28, "shots": 11, "avg_shot_s": 2.5,
  "arc": "slow_build_to_peak",
  "hook": { "type": "text_over_action", "first_line_s": 0.8 },
  "shot_grammar": ["wide", "detail", "face", "wide", "detail", "hero"],
  "text_style": { "position": "lower_third", "case": "sentence", "animation": "word_pop" },
  "audio": { "music": "rising_cinematic", "speech_ratio": 0.4, "beat_synced": true },
  "palette": ["#1b2a4a", "#e8a33d"], "grade": "warm_high_contrast"
}
```

The director then plans against this spec *and* the user's library: it tries to match the shot grammar, pacing, hook style, and text treatment using the user's own footage retrieved from memory. "Make it like this, but from my clips."

---

## 4. Live dashboard — how you see everything

Every agent and skill emits events to a bus (task started/progress/done/failed, with payloads). The Studio subscribes (WebSocket / SSE) and renders live: current pipeline stage, per-agent status, what skill is running on which asset, and the timeline filling in.

```json
// Event stream examples
{ "t": "ingest.progress", "asset": "a_9f3", "pct": 100 }
{ "t": "agent.running", "agent": "VisualScout", "doing": "score_visual_quality", "asset": "a_9f3", "i": 38, "n": 42 }
{ "t": "agent.done", "agent": "SpeechAgent", "result": "3 soundbites ranked" }
{ "t": "stage.enter", "stage": "plan" }
{ "t": "director.pairing", "audio_from": "a_2c1:s_07", "visuals_from": "a_9f3:s_014" }
{ "t": "render.progress", "variant": "hook_driven", "pct": 60 }
{ "t": "critic.flag", "agent": "PlatformCritic", "issue": "hook lands at 1.4s, target <1s" }
```

Because state lives on the blackboard and tasks are explicit, the dashboard is a *view* of real state, not a fake progress bar — and you can click any agent to ask why it did something, or interrupt and redirect.

---

## 5. Conversational session model (no coding)

A session is a structured dialogue the orchestrator drives:

1. **Intent** — you state a goal ("motivational short, 10 shots, 30s, build to a peak"), optionally with a reference upload.
2. **Requirement elicitation** — the orchestrator asks only what it needs (platform? captions? music vibe? any must-include clips?), inferring the rest from the reference/profile. Kept short.
3. **Retrieval + plan** — it queries memory for candidates and drafts 1–N EDL variants with reasons, no re-analysis.
4. **Delegation** — it dispatches production skills; the dashboard goes live.
5. **Review & re-edit** — you watch the preview and speak changes ("punchier opening", "swap the third shot", "lose the rambling part", "more like the reference's ending"). Each instruction re-plans the EDL and re-renders the affected parts only.
6. **Export** — per-platform targets from one edit.

Every turn is natural language; the system translates it into agent/skill delegation. The user never sees JSON unless they want to.

### Intent → delegation mapping (examples)
- "make it punchier" → director increases cut density + trims heads/tails → re-render.
- "add captions" → CaptionAgent runs on all soundbites.
- "this clip's audio is bad, keep the visuals" → re-role segment to `b_roll`, find replacement audio/music.
- "use the two clips I just added" → watcher already indexed them; retrieval includes them.
- "more like the reference" → re-optimize against the style spec (pacing/grammar/text).

---

## 6. How this ties into the engine

- Memory records *are* the blackboard's persistent backing — a project loads its segments from the index instead of recomputing.
- Retrieval feeds the director the candidate set; role classification and pairing (the bike-clip logic) run on retrieved segments.
- Skills behind contracts mean re-analysis with an upgraded skill version is a targeted re-index of affected fields, not a full rescan — and the asset record's `skill_versions` tells you exactly what's stale.

---

## Build order

1. Universal ingest + fingerprint + asset/segment records + the index (vector + metadata + text). Prove dedup and incremental diff with a folder of mixed-format clips.
2. Retrieval API: natural-language + filter query → ranked segments. Prove "10 motivational shots in 30s" returns sensible candidates with no re-analysis.
3. Event bus + live dashboard reading real task state.
4. Conversational session loop (intent → elicit → plan → delegate → review) wired to the director.
5. Reference extraction → style spec → director targeting it.
6. Incremental watcher in production; re-edit loop with partial re-render.
