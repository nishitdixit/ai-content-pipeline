# Agentic Video Editor — Architecture Spec

Companion to the build playbook. This is the design for a fully pluggable, retrainable, multi-agent system that handles asymmetric footage (great visuals + bad audio, or vice-versa) and the messy edge cases of short-form content for Reels / Shorts / TikTok.

---

## 0. The problem that forces this design

A naive editor computes one blended "best-ness" score per segment. That throws away exactly the clips that matter most:

- A bike POV clip with stunning visuals but only traffic/wind noise scores ~9 on visual, ~2 on audio → blended ~5 → **discarded**, when it should be muted B-roll under music.
- A clip with a great spoken line but shaky/ugly footage scores ~2 on visual, ~9 on speech → blended ~5 → **discarded**, when its audio should be kept and the visuals covered.

The fix is structural: **score each modality independently and never collapse them too early.** Then classify each segment by the *role* it can play, and let a director combine roles — pairing the soundbite's audio with the B-roll's visuals into one segment that is strong on both axes. This is how human editors work, and it's why the system must be agentic (independent specialists + a director) rather than a single scoring function.

---

## 1. Three levels of abstraction

The flexibility you want (add/remove/retrain anything) comes from separating *acting* from *reasoning* from *running*.

### Skill — a single capability behind a contract
- Does exactly one thing; stateless.
- Has a typed input/output contract, a version, a model/impl reference, an eval set, and a training pipeline.
- Swappable: hosted ↔ self-hosted, vendor A ↔ vendor B, model v3 ↔ v4 — without touching callers.
- Examples: `transcribe`, `detect_scenes`, `score_visual_quality`, `score_audio_quality`, `detect_faces`, `track_subject`, `detect_beats`, `select_music`, `reframe_vertical`, `burn_captions`, `stabilize`, `loudness_normalize`, `speed_ramp`, `moderate_content`.

```json
{
  "skill": "score_visual_quality",
  "version": "1.4.0",
  "input": { "segment_ref": "string", "frames_fps": "number" },
  "output": { "visual_quality": "0..1", "tags": "string[]", "sharpness": "0..1", "aesthetic": "0..1" },
  "impl": { "provider": "local", "model": "siglip-ft-bike-v2", "device": "gpu" },
  "eval_set": "evals/visual_quality_golden_v3",
  "retrainable": true
}
```

### Agent — a reasoning unit with a role
- Has a goal, reads/writes the blackboard, and *selects and sequences skills* to do its job.
- Can be LLM-driven (reasons in language, good for the director and critics) or a learned policy / lightweight model (good for fast scorers).
- Examples: `VisualScoutAgent`, `AudioDirectorAgent`, `SpeechAgent`, `MotionAgent`, `AestheticAgent`, `NarrativeDirectorAgent` (the director), `PlatformCritic`, `CutQualityCritic`, `EngagementPredictor`.

```json
{
  "agent": "AudioDirectorAgent",
  "role": "Judge audio per segment and decide treatment.",
  "reads": ["transcript", "audio_quality", "beats", "loudness"],
  "writes": ["audio_role", "audio_treatment"],
  "skills": ["score_audio_quality", "detect_beats", "loudness_normalize", "denoise"],
  "policy": "llm",
  "eval_set": "evals/audio_decisions_golden_v1"
}
```

### Orchestrator — the runtime + registry + memory
- **Registry**: where agents and skills are registered/unregistered. Add an agent = register it; it immediately participates. Remove = unregister; the loop skips it.
- **Scheduler**: runs the control loop (Section 6), parallelizing perception, sequencing planning.
- **Memory**: project memory (this video's blackboard + EDL history), creator memory (learned taste/style), platform memory (what performed).

---

## 2. The blackboard (shared timeline state)

A single object all agents annotate. This is what makes agents loosely coupled: perception agents *add* annotations independently, so a new agent is purely additive.

```json
{
  "project_id": "ride_2026_06",
  "profile": "bike_vlog",
  "segments": [
    {
      "id": "s_014",
      "source": "gopro_clip2.mp4",
      "in": 132.4, "out": 141.0,
      "scores": {
        "visual_quality": 0.91, "aesthetic": 0.88, "motion": 0.74,
        "audio_quality": 0.21, "speech_value": 0.05, "novelty": 0.7,
        "emotion": 0.3, "stability": 0.6
      },
      "tags": ["coastline", "sunset", "no_speech", "wind_noise"],
      "roles": ["b_roll", "hero_visual"],
      "treatments": { "audio": "mute_add_music", "reframe": "track_subject" },
      "flags": ["wind_buffeting"],
      "feedback": null
    }
  ],
  "pairings": [ { "audio_from": "s_031", "visuals_from": "s_014" } ],
  "edl_history": []
}
```

Note `scores` keeps every modality separate, `roles` is a *list* (a clip can be both hero-visual and B-roll), and `pairings` records the soundbite↔B-roll combinations the director made.

---

## 3. The agent roster (and how to extend it)

| Layer | Agent | Reads | Writes / Does |
|---|---|---|---|
| Perception | `VisualScoutAgent` | frames | visual_quality, aesthetic, tags |
| Perception | `MotionAgent` | frames | motion, action peaks, shake/stability |
| Perception | `AudioDirectorAgent` | audio | audio_quality, noise type, loudness, beats |
| Perception | `SpeechAgent` | transcript | speech_value, quotability, Q&A structure |
| Perception | `FaceEmotionAgent` | frames | faces, eyelines, emotion |
| Perception | `ContextAgent` | all | scene/topic, novelty, dedupe |
| Planning | `NarrativeDirectorAgent` | blackboard | role classification, pairings, EDL, multiple variants |
| Production | `ReframerAgent` | EDL + tracks | vertical reframe, safe-zone compliance |
| Production | `AudioMixAgent` | EDL | mute/duck, music bed, beat-aligned cuts |
| Production | `CaptionAgent` | transcript | styled captions, on-screen hooks |
| Production | `FXAgent` | EDL | speed ramps, stabilization, transitions, grade |
| Critique | `CutQualityCritic` | render | flag jump cuts, audio pops, jarring boundaries |
| Critique | `PlatformCritic` | render | length, hook timing, aspect, safe zones, loop |
| Critique | `EngagementPredictor` | render | predicted retention / scroll-stop score |

**To add a capability** (e.g. a `LandscapeBeautyAgent` tuned for your bike vistas): write the agent, declare what it reads/writes, register it. It starts annotating the blackboard; the director picks up the new signal automatically if its prompt/policy references it.

---

## 4. Role classification — the core logic

The director's first job: turn independent scores into roles. This is where asymmetric signals get rescued.

```python
def classify_roles(seg, thresholds):
    v = seg.scores.visual_quality
    a = max(seg.scores.audio_quality, seg.scores.speech_value)
    roles = []
    if v >= thresholds.high and a >= thresholds.high:
        roles.append("hero")                         # use as-is
    if v >= thresholds.high and a < thresholds.mid:
        roles.append("b_roll")                       # mute, music bed, canvas
    if seg.scores.speech_value >= thresholds.high and v < thresholds.mid:
        roles.append("soundbite")                    # keep words, cover visuals
    if v < thresholds.mid and a < thresholds.mid:
        roles.append("discard_or_glue")              # only for continuity/breath
    if seg.scores.motion_peak:
        roles.append("speed_ramp_candidate")         # slow-mo the apex
    return roles
```

Then it pairs and assembles:

```python
def pair_and_assemble(segments):
    soundbites = [s for s in segments if "soundbite" in s.roles]
    broll      = [s for s in segments if "b_roll" in s.roles]
    timeline = []
    for sb in rank_by_value(soundbites):
        cover = best_matching_broll(sb, broll)       # match by topic/energy/length
        timeline.append(layer(audio=sb, visuals=cover, music="ducked"))
    for hero in rank_by_value(heroes(segments)):
        timeline.append(hero)
    return tighten_for_platform(sequence_for_arc(timeline))
```

`best_matching_broll` is itself a skill you can retrain — it learns which visuals best cover which kind of talk (matching topic, energy, and shot length).

---

## 5. Edge-case catalog → owning agent → action

The cases to cover for short, engaging content. Each maps to an agent/skill so it's buildable, not just a list.

| # | Edge case | Detected by | Action |
|---|---|---|---|
| 1 | Great visuals, only traffic/ambient (bike POV) | VisualScout + AudioDirector | Role `b_roll`: mute, music bed, beat-synced cuts |
| 2 | Great spoken line, ugly/shaky visuals | Speech + Visual + Motion | Role `soundbite`: keep audio, cover with B-roll, captions |
| 3 | Both weak | all perception | `discard`, unless needed as glue/breath |
| 4 | Both strong | all perception | `hero`: use as-is, candidate opener |
| 5 | Clip ramps up slowly (dead opening) | MotionAgent | Trim to the action; drop the slow head |
| 6 | No hook in first 1–1.5s | Director + EngagementPredictor | Front-load the most arresting frame/line, even out of order |
| 7 | Rider moves across frame on vertical crop | ReframerAgent (track_subject) | Subject-tracking reframe, not static center crop |
| 8 | Key content sits under platform UI (bottom captions, right buttons) | PlatformCritic (safe zones) | Reframe to keep subject in safe area |
| 9 | Wind buffeting / mic distortion vs pleasant ambient | AudioDirectorAgent | Distinguish noise type: denoise/duck/mute the bad, keep the vibe |
| 10 | Filler words / long pauses / dead air | SpeechAgent + AudioMix | Remove, tighten pace |
| 11 | Action apex (jump, trick, near-miss) | MotionAgent (peaks) | Speed ramp / slow-mo the apex; optional freeze |
| 12 | Music available but cuts miss the beat | AudioMixAgent (detect_beats) | Align cut points to transients |
| 13 | Shaky helmet-cam | MotionAgent (stability) | Stabilize; if too shaky, demote or shorten |
| 14 | Several distinct good moments in one long clip | ContextAgent + Director | Produce multiple shorts, not one |
| 15 | Repetitive / near-duplicate shots | ContextAgent (dedupe) | Keep best, enforce variety |
| 16 | Low-res / over-compressed segment | VisualScout (sharpness) | Avoid as hero; optional upscale; flag |
| 17 | Face small/off-center on vertical crop | FaceEmotionAgent + Reframer | Keep face in frame + safe zone |
| 18 | Loudness imbalance across clips | AudioDirector (loudness_normalize) | Normalize to platform target (e.g. ~-14 LUFS) |
| 19 | Short-form benefits from seamless loop | PlatformCritic (loopability) | Pick start/end frames that match |
| 20 | Speech in noisy environment | AudioDirector (denoise) + Caption | Enhance voice; captions compensate |
| 21 | No speech at all (pure vibe ride) | ContextAgent (`no_speech`) | Switch to music-led template + on-screen text storytelling |
| 22 | Explicit / unsafe / brand-risk content | ContextAgent (moderate_content) | Exclude / flag |
| 23 | Copyrighted music in source or added | AudioMix (licensing check) | Flag; restrict to licensed library |
| 24 | Punchline/emotional beat buried mid-clip | Director (narrative arc) | Build setup → payoff even in 20s |
| 25 | Jarring jump cut between mismatched shots | CutQualityCritic | Insert transition or reorder; revise EDL |
| 26 | Over-cut (frantic) or under-cut (drags) | PlatformCritic (pace) | Adjust cut density to platform norm |
| 27 | 16:9 source → 9:16 with info at edges | Reframer | Smart reframe; blurred-fill fallback only if needed |
| 28 | Captions overlap the subject | CaptionAgent | Reposition captions to a clear zone |

Adding case #29 later is just another critic rule or perception signal — no rewrite.

---

## 6. The control loop

```
register agents + skills (from config)
└─ PERCEIVE   run all perception agents in parallel → annotate blackboard
└─ CLASSIFY   director assigns roles per segment, records pairings
└─ PLAN       director emits N EDL variants (e.g. hook-driven / narrative / montage)
└─ PRODUCE    production skills render each variant (reframe, mix, caption, FX)
└─ CRITIQUE   critics score each render; flag cut/platform/engagement issues
└─ REVISE     director patches the EDL on flags; re-render (cap ~3 passes)
└─ PRESENT    show variants with per-cut reasons; capture user feedback
```

Perception is parallel and additive (cheap to add agents). Planning and revision are sequential and director-led (needs control). Critics gate quality before the user ever sees it.

---

## 7. Retraining & flexibility mechanics

What makes "retrain one agent without breaking the rest" actually safe:

- **Contracts as firewalls.** Every skill/agent has a typed I/O contract. Retraining changes the model inside; as long as outputs satisfy the contract, callers are unaffected.
- **Per-component eval gate.** Each has its own golden eval set. A new version must beat the incumbent on that set before it can be promoted.
- **Shadow + A/B.** Run the new version in shadow (scores logged, not used) or A/B on a slice of traffic; promote only on a win.
- **Feedback → labels with credit assignment.** Every user action (accept, reject, trim, reorder, regenerate, swap-B-roll) is logged *against the specific agent decisions that produced it*. A rejected soundbite-pairing trains `best_matching_broll`; a re-cropped clip trains the reframer. This is your moat — it personalizes to each creator's taste and compounds over time.
- **Versioned registry.** Agents/skills are pinned by version per project, so retraining never silently changes an in-flight edit; you opt a project into new versions.
- **Profiles as data.** Per-genre scoring weights (bike_vlog, podcast, gameplay…) are config + learned weights, not code. The user picking a footage type loads a profile; their feedback tunes that profile's weights.

---

## 8. Platform awareness (Reels / Shorts / TikTok)

`PlatformCritic` enforces per-target rules as data, so adding a platform is a config row:

```json
{
  "tiktok": { "aspect": "9:16", "max_s": 180, "ideal_s": [21, 34],
              "hook_window_s": 1.0, "safe_zone": { "bottom_pct": 18, "right_pct": 12 },
              "captions": "required", "loop_bonus": true, "loudness_lufs": -14 },
  "reels":  { "aspect": "9:16", "max_s": 90,  "ideal_s": [15, 30], "hook_window_s": 1.5, "captions": "required" },
  "shorts": { "aspect": "9:16", "max_s": 60,  "ideal_s": [15, 40], "hook_window_s": 1.0, "captions": "required" }
}
```

The same edit is re-targeted per platform by swapping this profile — different length, hook timing, and safe-zone constraints, same underlying selection.

---

## 9. How this maps onto hosted-now / self-host-later

Skills *are* the swap mechanism from the playbook. Because each skill hides its impl behind a contract, you start with hosted impls and replace them one at a time — visual scoring, transcription, embeddings — by registering a new impl version. The agents, director, blackboard, and critics never change. The architecture is the migration plan.

---

## Build order

1. Blackboard + registry + 3 perception skills (visual/audio/speech scoring) wired to the loop.
2. Director with role classification + soundbite/B-roll pairing → EDL. **This validates the bike case end-to-end.**
3. Production skills: reframe (subject-track), caption, audio mix (mute/duck + music + beat-sync).
4. Critics: cut-quality + platform. Add the self-eval revise pass.
5. Feedback logging with credit assignment → first retrain of the pairing + reframe skills.
6. Multi-variant proposals + conversational editing. Then begin self-host swaps in cost order.
