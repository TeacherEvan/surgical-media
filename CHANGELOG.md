# Changelog

All notable changes to surgical-media. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project is
pre-1.x and dates before semantic guarantees.

Honest status line used throughout: **no hosted CI.** GitHub Actions was
removed 2026-11-18 (billing-locked; jobs never started). Local gates
(`bash scripts/ci_gates.sh`) are the enforced standard; the GitLab mirror
(`.gitlab-ci.yml`) is configured, not verified.

## [1.2.0] — 2026-11-18

### Added
- `tests/test_elements.py`, `tests/test_render_engine.py` — direct coverage for the
  two largest runtime modules (previously smoke-only): helper math, dispatcher
  behavior, per-painter no-crash across `t ∈ {0, 0.5, 1}`, pixel-presence checks,
  image-painter failure path, Bresenham frame-quantization invariants.
- `tests/test_schemas_contract.py` — the hand-rolled runtime validator and
  `schemas/storyboard.schema.json` must agree on rejection mutations; new
  gate 6/8 in `ci_gates.sh` validates the example storyboard against its schema
  (`check-jsonschema`).
- `tests/test_code_syntax.py` — unit tests for the new code_terminal tokenizer.
- Regex syntax highlighting in the `code_terminal` element (comments / strings /
  numbers / keywords across Python/JS/TS/Rust-ish), rendered in bundled JetBrains Mono.
- `verify_output.py` `audio_not_silent` check — ffmpeg `silencedetect`
  (−50 dB / 0.8 s), 0.75 coverage threshold (`--max-silence-fraction`),
  parser + coverage unit tests and a silent-MP4 integration test.
- Bundled OFL JetBrains Mono v2.304 (`assets/fonts/`, SHA-256 pinned, license
  verbatim); canvas prefers it for mono. The `code_report` archetype is now
  OS-independent.
- `frame_counts()` in `render_engine.py` — cumulative Bresenham quantization;
  multi-scene A/V drift is now provably bounded (7 × 0.35 s @ 30 fps: 74 vs 70 frames).
- Direct `stick_rig` / `system_architecture` painter tests.

### Changed
- `elements.py` (940-line god module) split into `scripts/elements/` package
  (`_shared`, `scenes`, `text`, `dataviz`, `code`, `figures`, `media`);
  public API unchanged via re-exports.
- `fetch_assets.py`: https-only (incl. redirect targets), 50 MB cap on
  Content-Length/streamed bytes; `FetchError` subclasses `OSError`.
- Installer now copies the `scripts/elements/` package (previously
  `scripts/*.py` would have installed a broken skill).
- 199 → 218 tests; all gates pass locally (8/8).

### Removed
- GitHub Actions (`.github/workflows/skill-ci.yml`) — billing-locked; permanently
  red. Verification is local-first; the GitLab mirror remains optional and
  configured-not-verified.

## [1.1.0] — 2026-11-18

- Stage 1 multi-source licensed imagery (`fetch_assets.py`): Openverse +
  Wikimedia Commons (original-res 2048 px) + iNaturalist, one
  `by`/`by-sa`/`cc0`/`pdm` allowlist, `*-nd`/`*-nc` rejected, PIL-verified,
  cross-source deduped, attribution manifest baked into `image` elements.
- Raster `image` element: cover/contain/`backdrop_blur` (social bleed),
  Ken Burns drift, safe-zone `attribution_y` credits.
- Bundled OFL Inter v4.1 (SHA-256 pinned); canvas prefers it.
- Optional `blender_plate.py` (headless Workbench, transparent PNGs:
  `earth` / `iceberg` / `ringed`); never a hard requirement.
- GitLab CI mirror committed (`.gitlab-ci.yml`) + `scripts/ci_gates.sh` as
  the single gate entrypoint.

## [1.0.0] — 2026-11-15

- Initial verified pipeline: investigation brief → audio-first timing →
  storyboard → 2x-supersampled Pillow frames → ffmpeg H.264/AAC → ffprobe QC.
- 132 tests at release; Pillow + stdlib only; no golden images by design.
