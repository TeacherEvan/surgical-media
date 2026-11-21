# ADR 0006 — Merge the social-media-studio-pro update into surgical-media

**Status:** Accepted (2026-11-21) · **Source:** "UPDATE: Conversation with Gemini" (priority
social-video pipeline) merged into this repository at v3.0.0.

## Context

A second skill (`social-media-studio-pro`, later a 5-file Markdown package) was proposed to
cover collaborative social-video production: mandatory intake questions, live spec refresh,
authentic photos of real people with subtle attribution, proactive tooling pitches, an
audio-first multi-engine contract, topic-matched intro/outro, and a hard QC gate. That package
described capabilities mostly as prose and embedded Markdown "templates"; this repository
already implements most of them as tested code (39 scripts, 713 tests, 12 local gates).

Shipping both would create two overlapping video skills with divergent guidance. The update
also contained genuinely new capabilities absent here: face-centered reframing, measured
ebur128 loudness and dead-air QC, dual 9:16 safe-zone audit overlays, TTS text normalization,
a 7-style execution matrix, and a commercial licensing matrix.

## Decision

1. **One skill, not two.** `surgical-media` v3.0.0 is the single priority pipeline for all
   future surgical-media content generation. No sibling `social-media-studio-pro` skill is
   created or installed.
2. **Orchestration from the update, implementation from this repo.** `SKILL.md` becomes the
   7-step orchestrator; every step points to a real script or reference here. Prose never
   claims capability without code + tests ("Claims = code").
3. **Cherry-pick the missing utilities as real scripts**, not Markdown templates:
   `spec_refresh.py`, `pipeline_preflight.py`, `style_apply.py`, `tts_normalizer.py`,
   `media_harvester.py`, `qc_gate.py`. They reuse existing helpers (`fetch_assets`, `canvas`,
   `verify_output`, `storyboard`, `style`) instead of duplicating them. Spec refresh is
   auditable; `style_apply.py` writes the 7-style matrix into boards and `pipeline_preflight.py`
   verifies it. Intake, style, intro/outro and originality are executable checks, not prose.
4. **Keep the stdlib-first invariant.** OpenCV is an optional face-detection accelerator with
   a deterministic anchor fallback; no NumPy dependency. `storyboard.json` stays the single
   locked timeline — no second hand-edited `timeline.json`.
5. **Two safe-zone masks, not one.** Organic `(60,180)-(930,1540)` and strict ad-safe
   `(65,288)-(888,1248)` at 1080x1920; the renderer's historical `(84,220)-(w-150,h-440)`
   remains the 2D default but is audited against both masks before delivery.
6. **Time-sensitive facts are dated and re-checked.** Platform caps, 2026 Shorts Content ID /
   originality rules, C2PA/AI disclosure and model licenses live in
   `references/specs-licensing-compliance.md` with a mandatory live refresh in Step 2.
7. **Optional engines stay optional.** Remotion, Revideo, Manim CE, WhisperX and local TTS
   weights are proposed in Step 4 with licensing checks; Three.js and Blender remain
   capability-probed with stdlib fallback.

## Consequences

- `SKILL.md` stays ≤120 lines; the heavier material moves to four new reference files.
- `install_surgical_media.sh` ships the new scripts, references, `examples/jobs/` and
  `requirements*.txt`, and purges stale root-level `scripts/*.py` (the old `elements.py`).
- The installed skill at `~/.hermes/skills/creative/surgical-media` must be refreshed with
  the installer before it reflects v3.0.0 — editing the repo alone does not activate it.
- Deferred by design: Remotion/Revideo runtime, Manim implementation, WhisperX alignment
  replacing measured edge-tts boundaries, and hosted publishing adapters.
