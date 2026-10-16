# AI Video Editor — Build Playbook

A practical blueprint for a tool that ingests raw clips, finds the best parts, and proposes what to do with them. Designed for: any footage type (the user picks), built on hosted APIs now, with each piece swappable for a self-hosted model later.

---

## 1. The core architectural principle

Two decisions are load-bearing. Both are cheap now and painful to retrofit, so put them in from day one.

**A. Everything is a swappable capability behind an interface.** Don't call vendor SDKs directly from your business logic. Define a small set of capability interfaces and write thin adapters per provider. When you self-host a piece later, you write a new adapter — nothing upstream changes.

The capabilities you need:

- `Transcriber` — audio to timestamped text
- `SceneSegmenter` — shot/scene boundaries
- `VisualTagger` — objects, actions, on-screen text (OCR), faces
- `Embedder` — vector embeddings for semantic search
- `Scorer` — segment "best-ness" given a goal (can be heuristic + LLM)
- `Renderer` — EDL to video (FFmpeg) or to a timeline file (FCPXML/EDL/AAF)

Interface sketch (TypeScript-flavored pseudocode):

```ts
interface Transcriber {
  transcribe(media: MediaRef): Promise<TranscriptSegment[]>;
}

// Hosted now:
class WhisperApiTranscriber implements Transcriber { /* calls hosted API */ }
// Self-hosted later — same interface, swap in config:
class LocalWhisperTranscriber implements Transcriber { /* runs whisper.cpp on GPU */ }

const transcriber: Transcriber =
  config.providers.transcriber === "local"
    ? new LocalWhisperTranscriber()
    : new WhisperApiTranscriber();
```

Provider choice lives in config, keyed per capability, so you can be hosted for transcription and self-hosted for embeddings simultaneously and migrate one at a time.

**B. Video becomes structured text early, and the AI only ever sees the text.** The single most important realization in this whole space: language models can't watch video. Every capable system converts footage into a compact, timestamped text/JSON description (transcript + scene boundaries + visual tags + on-screen text + engagement signals) and then reasons over *that*. Your intelligence lives in reasoning over text, not in looking at pixels. This is also what makes it affordable — you analyze pixels once, cheaply, then run unlimited cheap text reasoning on top.

The canonical pipeline:

```
Raw clips
  → decode + segment (scene/shot boundaries)
  → multimodal analysis (transcript, visual tags, OCR)
  → STRUCTURED METADATA  ← timestamped JSON, "video as text"  [the pivot]
  → agent reasoning (score, select, sequence)
  → Edit Decision List (EDL)
  → render (FFmpeg / timeline export)
  → finished cut
        ↺ self-eval loop retries on bad cuts/audio pops
```

---

## 2. The stack, layer by layer

Pick the hosted option now; the self-host column is your later swap target. Mix and match freely thanks to the adapter layer.

| Capability | Hosted now (fast to ship) | Self-host later (cost/control) | Notes |
|---|---|---|---|
| Transcription | Hosted Whisper API / Deepgram / AssemblyAI | `whisper.cpp` or `faster-whisper` on GPU | Transcript is your richest signal; get word-level timestamps. |
| Scene/shot detection | Cloud shot detection (AWS Rekognition ~$0.05/min) | `PySceneDetect` (open source, free) | Self-hosting this is trivially cheap — swap early. |
| Visual tagging / OCR / objects | Google Video Intelligence (20k+ objects, frame-level) or Azure Content Understanding (transcription + OCR + shots + custom fields in one) | YOLO11 + EasyOCR + MMAction2 for action recognition | Azure lets you define custom fields a generative model fills per segment — fastest path to rich metadata. |
| Deep video understanding / semantic | TwelveLabs (Marengo for search/embeddings, Pegasus for summaries/highlights up to 2h) | CLIP / SigLIP embeddings, fine-tuned per domain | TwelveLabs is the "smart" option; CLIP/SigLIP self-host gives 85–90% search accuracy (90–95% fine-tuned). |
| Vector store / search | Hosted (Pinecone / managed) or Mixpeek (first 1M vectors free) | pgvector / Qdrant / self-hosted | Stores per-segment embeddings + metadata for retrieval. |
| Reasoning / creative direction | Frontier LLM API (your editor brain) | Open-weight LLM later if cost demands | Cheapest layer per video — it only sees compact text. |
| Rendering | FFmpeg (open source, run it yourself from the start) | Same | Also emit FCPXML/EDL/AAF so pros finish in Resolve/Premiere. |

**Aggregator shortcut:** if you want one key instead of six during the MVP, unified APIs (e.g. Eden AI) front multiple providers (Google, AWS, Azure, TwelveLabs, Clarifai) behind a single REST contract and standardized JSON. Useful to ship in days; you'll outgrow it on cost and want direct adapters.

**Swap order (cheapest wins first):** scene detection → transcription → embeddings → visual tagging → reasoning. Rendering is already yours.

---

## 3. Content-type profiles — how "the user chooses any type" works

You do **not** build separate apps per footage type. You build one engine + a router that loads a *profile* when the user picks their content type. A profile is just config: which signals matter, how they're weighted, which templates apply.

Why this matters: "best part" means different things per genre. A podcast's best moment is a quotable line (transcript-driven); a gameplay highlight is a kill/clutch spike (audio + visual-change + chat-spike driven); a wedding's best moment is emotional and visual (faces + audio swell), and transcript barely matters.

Profile config example:

```json
{
  "profile": "gameplay",
  "scoring_weights": {
    "audio_energy": 0.30,
    "visual_motion": 0.30,
    "on_screen_text": 0.10,
    "transcript_keywords": 0.05,
    "chat_or_reaction_spike": 0.25
  },
  "segment_length": { "min_s": 8, "max_s": 45 },
  "templates": ["vertical_short", "montage"],
  "required_capabilities": ["scene", "visual_tags", "audio"]
}
```

```json
{
  "profile": "podcast",
  "scoring_weights": {
    "transcript_keywords": 0.45,
    "speaker_emphasis": 0.20,
    "audio_energy": 0.15,
    "question_answer_structure": 0.20
  },
  "segment_length": { "min_s": 20, "max_s": 90 },
  "templates": ["talking_head_caption", "quote_card"]
}
```

Ship 3–4 profiles to start (talking-head/podcast, gameplay/stream, cinematic/vlog/event, general). The router maps the user's choice → profile → which capabilities run and how the Scorer weights them. Adding a new genre is a config file, not a new pipeline. Later, let power users tune weights or learn weights from their own published-content performance (the trick that makes commercial tools feel "smart").

**Accuracy reality by type** (so you set expectations and prioritize): structured content — interviews, presentations, gaming, tutorials — reaches ~90%+ at matching human highlight picks. Artistic/cinematic/dialogue-light footage is much weaker and needs heavy human-in-the-loop. Lead with the genres that work; treat cinematic as "assist, don't automate."

---

## 4. The creative-director layer — your actual moat

Tiers 1 and 2 (clipping, captions, reframing, search) are commodities; competitors already do them. Your differentiation is the LLM-as-creative-director: it doesn't just find clips, it proposes *what to do* and explains why, then revises on instruction. Almost nobody ships this well yet.

**4.1 The LLM is the editor.** Feed it the structured metadata + the user's goal, prompt it to act as a video editor, and have it emit a structured plan — not prose. The plan is an **Edit Decision List (EDL)**: the contract between the AI brain and the dumb renderer.

EDL schema example:

```json
{
  "variant_label": "fast hook-driven cut",
  "rationale": "Opens on the strongest claim to stop the scroll, then pays it off.",
  "target": { "platform": "reels", "aspect": "9:16", "duration_s": 30 },
  "timeline": [
    { "clip": "raw_02.mp4", "in": 412.5, "out": 418.0,
      "reason": "punchy claim, high audio emphasis", "captions": true, "reframe": "track_speaker" },
    { "clip": "raw_02.mp4", "in": 60.2, "out": 73.4,
      "reason": "context that proves the claim", "captions": true },
    { "transition": "hard_cut" },
    { "clip": "raw_05.mp4", "in": 1003.0, "out": 1009.5,
      "reason": "visual payoff / reaction" }
  ],
  "audio": { "fade_ms": 30, "music": "optional_low_energy" }
}
```

The renderer executes this mechanically. Note `reason` on every cut — it powers an explainable UI ("here's why I picked this") and is the audit trail that makes the tool trustworthy.

**4.2 Propose multiple strategies, not one answer.** The high-value behavior is offering distinct *creative directions* for the same footage — e.g. a fast hook-driven cut vs. a narrative version vs. a tutorial version — each with reasoning and tradeoffs. This is exactly the "suggest the best things to do with these clips" the product promises, and it's the experience users can't get from one-click clippers.

**4.3 Self-evaluation loop.** After rendering, inspect cut boundaries for visual jumps and audio pops; if a check fails, fix and re-render (cap at ~3 attempts) before showing a preview. Cheap quality insurance that markedly raises perceived polish. Apply small audio fades (~30ms) at every cut by default.

**4.4 Conversational editing.** Because the EDL is structured and the metadata is text, the user can say "make the intro punchier, cut the part where I ramble, add captions" and the LLM re-plans the EDL. This turns editing into a dialogue — a genuinely differentiated UX. Persist session state (the project, prior EDLs, user corrections) so edits are iterative across sessions.

**4.5 The learning loop.** Capture every accept/reject/trim the user makes and feed it back into the Scorer (per-user weight tuning, or fine-tuning later). This is how "best part" stops being generic and starts matching *their* taste — and it compounds into a moat competitors can't copy because it's your users' data.

**Prompt-design notes for the reasoning model:** give it (1) the goal + profile, (2) the segment metadata as compact JSON with timestamps, (3) the EDL schema to fill, (4) explicit instruction to return only valid JSON, (5) a rubric for "best" tied to the profile weights. Combine retrieval (vector search to shortlist candidate segments) with the LLM plan step so you don't blow the context window on long footage.

---

## 5. Cost model & unit economics

The number you're beating: manual tagging/editing runs roughly $50–200 per hour of footage. Your job is to deliver acceptable quality at cents-to-low-dollars per hour.

**Per-layer cost of processing one hour of video:**

| Layer | Hosted now | Self-hosted later | Comment |
|---|---|---|---|
| Scene detection | ~$3/hr (≈$0.05/min, e.g. AWS) | ~free (PySceneDetect) | Swap first — near-zero cost. |
| Transcription | ~$0.25–1.50/hr (varies by vendor) | GPU-amortized cents | Big swing; self-host pays off at volume. |
| Visual tagging/OCR | ~$3–9/hr ($0.05–0.15/min) | ~$0.10–0.50/hr amortized | The dominant hosted cost. |
| Embeddings + vector store | low; first 1M vectors often free | self-host pgvector/Qdrant | Cheap either way at small scale. |
| LLM reasoning | a few cents/video (compact text only) | open-weight later | Cheapest layer — this is the point of "video as text." |
| Rendering (FFmpeg) | your compute | your compute | CPU/GPU time only. |

**Headline:** hosted analysis is roughly **$3–9 per hour of video**; self-hosted is roughly **$0.10–0.50 per hour** once infra is amortized. That ~10–30x gap is exactly why you architect for the swap. The reasoning/LLM layer stays cheap throughout because it only ever processes text — verify current per-token API pricing before modeling, but expect single-digit cents per typical video.

**Unit-economics implications:**

- **Don't reprocess.** Analyze once, cache the metadata + embeddings, then allow unlimited re-edits (which only re-run the cheap reasoning + render). Your marginal cost per *edit* should approach zero; cost is dominated by the one-time *ingest*.
- **Gate the expensive layer.** Run cheap signals (scene cuts, transcript) on everything; only run premium visual understanding on segments that already look promising, or on user request. Hybrid edge/cheap-first, premium-on-flagged is the standard enterprise pattern.
- **Pricing model.** Per-minute-ingested pricing maps cleanly to your dominant cost. A freemium tier is viable on free API allowances (e.g. AWS's 60 free min/month for 12 months) plus self-hosted scene detection.
- **Where margin comes from later.** Swapping visual tagging and transcription to self-hosted converts your biggest variable cost into amortized fixed infra — that's the move that turns a thin-margin wrapper into a real business.

---

## 6. Competitive gaps to exploit

The incumbents (OpusClip, Vizard, Descript, Veed, Runway) are strong at commodity clipping (~0.93 mAP, sub-5s for 10-min clips) but share exploitable weaknesses:

- **They optimize "viral clip from long video," not "edit from raw footage."** Assembling a coherent piece from many unstructured raw clips is far less served. If your "any footage type" router does multi-clip story assembly, that's white space.
- **Thin creative direction.** Most give you clips, not *options with reasoning*. The multi-strategy creative-director experience is largely unbuilt.
- **Generic taste.** They detect universal peaks (laughter, applause) but don't deeply personalize to a creator's style until you feed them performance data. A first-class learning loop is a durable edge.
- **Weak on cinematic/emotional content.** Everyone is weak here; a profile genuinely tuned for vlogs/events/weddings (faces + audio swells + pacing) could own an underserved niche even if it's "assist" not "automate."
- **Frame-sampling blind spots.** ~1 FPS analysis misses single-frame moments (the perfect reaction, the exact swing). Higher-rate sampling on flagged segments, or motion-triggered dense sampling, catches what they miss — a real quality differentiator for sports/gameplay.
- **Closed pipelines.** Many trap you in their UI. Clean export to FCPXML/EDL/AAF for Resolve/Premiere wins the pro/prosumer segment that wants AI assist but finishes in a real NLE.

---

## 7. Phased roadmap

**Phase 0 — Thin vertical slice (weeks).** One hosted understanding API (or an aggregator) → vector store → LLM that takes a goal + profile and returns an EDL → FFmpeg render → preview with per-cut reasons + thumbs up/down. Ship 2 profiles (podcast, gameplay). Goal: prove the loop end-to-end.

**Phase 1 — The differentiator.** Add multi-strategy proposals (2–3 creative directions per request), conversational re-editing, and the self-eval loop. Add the remaining profiles + general mode. This is what makes people pick you over a one-click clipper.

**Phase 2 — Learning loop + cost swap.** Capture user edits → personalize the Scorer. Begin self-host migration in cost order: scene detection → transcription → embeddings → visual tagging. Each swap is an adapter change behind a stable interface; nothing upstream moves.

**Phase 3 — Pro pipeline + scale.** Timeline export (FCPXML/EDL/AAF), team features, dense-sampling for high-motion genres, fine-tuned domain models where accuracy pays. Now you have margin (self-hosted) and a moat (personalization data + creative-direction UX).

---

### The three things that matter most

1. **Adapter layer + content-router from day one** — they make "any type" and "hosted-then-self-hosted" possible without rewrites.
2. **The EDL is the contract** between an LLM that reasons over text and a renderer that executes — design it well and the rest is plumbing.
3. **The creative-director + learning loop is the only durable moat** — clipping is a commodity; *taste, options, and personalization* are not.
