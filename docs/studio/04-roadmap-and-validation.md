# Roadmap & Validation-First Build Plan

The other three docs describe the finished system. This one is about
sequencing — what to build first, and what to settle before building,
so effort is spent against evidence rather than assumptions.

## The core risk

The biggest risk is not technical. It is building an elaborate agentic
system before proving the one thing everything depends on: that the AI
produces edits worth publishing. Agents, blackboard, registry, memory,
dashboard, retraining are the *scaling* answer; none is the *validation*
answer. You can prove or kill the value proposition with hosted APIs and
a notebook.

This repo is the Phase-0/Phase-1 spine made real: the whole pipeline runs
end-to-end with mock perception so edit-logic quality can be judged now,
and every capability is an adapter so real models swap in one at a time.

## Settle before building

1. Prove the core manually. Run real clips (including asymmetric bike
   cases) through analysis, do role classification + soundbite/B-roll
   pairing, assemble with FFmpeg. Question: is the output postable? This
   repo's `examples/run_demo.py` is that harness, with mock perception
   standing in for hosted analysis.
2. Define "good" with an eval set. Hand-pick highlights and a few of your
   own edits as ground truth; score AI picks against them. Triple duty:
   measures progress, gates retraining, solves cold-start taste.
3. Lock open decisions: the wedge genre to nail first, orchestration
   runtime, render path, which capabilities start hosted.
4. Spike the scary unknowns: pleasant-ambient vs bad-noise discrimination,
   subject-tracking reframe on fast motion, beat-sync, reference style
   fidelity. Throwaway tests before architectural commitment.
5. Handle the blocking items: media storage + privacy, music licensing,
   stance on analyzing copyrighted references, moderation, and real
   unit-cost math for a realistic library size.
6. Instrument feedback from v1. Log every accept/reject/trim tied to the
   decision that produced it; the learning loop is only as good as this
   plumbing, which is cheap early and painful to retrofit.

## Phasing (resequenced around risk)

- Phase 0 — Validation (this repo). Notebook/CLI + mock or hosted APIs +
  FFmpeg + eval set. Output: real shorts and a go/no-go on edit quality.
- Phase 1 — Thin MVP. One genre, hosted skills, minimal UI, real users.
  Smallest thing that delivers the "wow": dump clips → ask → good cut.
- Phase 2 — The engine. Introduce the full agentic architecture and
  analyze-once memory, now informed by real usage on where the seams go.
- Phase 3 — The studio. Live dashboard, conversational re-edit,
  reference style-matching, incremental ingest, retraining, self-host
  cost swaps.

## How the code maps to the phases

| Concern | Where in this repo |
|---|---|
| Analyze-once + incremental | `memory/ingest.py`, `memory/fingerprint.py` |
| Query without re-analysis | `memory/index.py`, `retrieval.py` |
| Role classification + pairing | `agents/director.py` |
| Critics + revise loop | `agents/critics.py`, `orchestrator.py` |
| Skill adapters (swap seam) | `skills/`, `config/providers.json` |
| EDL → render | `edl.py`, `skills/render.py` |
| Live dashboard feed | `events.py`, `dashboard/index.html` |
| Conversational entry | `session.py`, `cli.py` |
| Eval gate (to add) | `tests/` + a golden set you provide |

## First real swaps (when validation passes)

Replace mock skills in cost order, re-validating against the eval set
after each: scene detection → transcription → embeddings → visual
quality → speech. The orchestrator and agents do not change.
