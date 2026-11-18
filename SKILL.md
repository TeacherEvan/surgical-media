---
name: surgical-media
description: "Use when creating, planning, or rendering social video from a topic prompt."
version: 1.0.0
author: "TeacherEvan, Hermes Agent"
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [video, ffmpeg, pillow, procedural-animation, storyboard, social-media, shorts, youtube, explainer, tts, edge-tts, supersampling, yuv420p, loudness, kinetic-typography, archetypes, deterministic]
    requires_tools: [terminal, read_file, write_file, search_files]
    related_skills: [video-production-pipeline, surgical-orchestration, surgical-audit]
---

# Surgical Media (v1.0.0)

Deterministic, verified pipeline for producing high-retention explainer and social videos from a topic prompt: research brief → audio-first timing → storyboard.json → 2x-supersampled Pillow rendering → ffmpeg H.264/AAC master → ffprobe QC gate. Unlike claim-heavy skill prose, **every capability listed here ships as tested code in this repository** (`tests/` — 107 tests including a rendered-and-verified MP4 integration pass and pixel-level visual smoke checks).

## When to Use

- The user wants a complete video, explainer, Short, Reel, or TikTok generated from a topic or URL.
- The user wants procedural animations in the Alan Becker (geometry/stick-figure), Matt Madigan (documentary essay), or Fireship (code report) visual styles.
- The user wants a repeatable script-to-MP4 pipeline with frame-accurate audio sync.
- The user needs social-ready masters verified for yuv420p/faststart/-14 LUFS before upload.

## When Not to Use

- Live-action capture, human editing suites (DaVinci/Premiere), or heavy 3D — this is procedural 2D motion graphics only.
- Video *analysis* of existing files (transcription, summarisation) — use a media-analysis skill.
- Cinemagraphs/loops under 3s with no narration — still fine, but a GIF pipeline is simpler.

## Style Archetypes

Blend per scene via the `archetype` field; see `references/archetypes.md` for the full field guide.

| Archetype | Reference feel | Canvas | Visuals | VO pace |
| :--- | :--- | :--- | :--- | :--- |
| `geometry_rig` | Alan Becker — Animation vs. Geometry | `#050508` void | 2-bone IK stick figure, recursive golden-ratio spiral, rotating 4D tesseract projection, φ lock pulses | non-verbal; SFX-locked |
| `doc_essay` | Matt Madigan — AI Is Bigger Than Aliens | `#0A0E17` slate + grid | exponential scaling curve, spring-pop milestone badges, glass quote cards, odometer telemetry | 150–165 WPM |
| `code_report` | Fireship — tech code reports | `#0D1117` IDE dark | 200 OK → 503 DAG cascade, cubic-bezier packet routing, macOS-style diff terminal, trauma shake | 175–195 WPM, tight beats |

## Procedure

### Stage 1 — Investigate & Extract Visual Anchors (and Fetch Subject Imagery)

Research the subject **as a producer would**: facts **and** footage. Emit a brief conforming to `schemas/investigation_brief.schema.json` with ≥3 verifiable facts (with sources), each mapped to a concrete visual primitive — never a static text slide — and fetch licensed subject imagery before writing any script:

```bash
python3 scripts/fetch_assets.py --query "<subject>" --out-dir assets --count 3
```

`fetch_assets.py` searches Openverse (240k+ CC assets), rejects non-remixable licenses (`by-nc*`, `by-nd*`), verifies each file decodes, and writes `assets/manifest.json` with per-image attribution strings — paste those verbatim into storyboard `image` elements. **A subject video with no image of the subject is a failure**; fetch ≥1 photograph unless the format is deliberately typographic-only. Never hotlink images into a render — download and attribute. Pick the format: `1920x1080@30/60` (16:9), `1080x1920` (9:16), or `1080x1080` (1:1); defaults live in `references/ffmpeg-encoding.md`.

### Stage 2 — Audio-First Timing

Never lock frame counts before audio exists.

```bash
python3 scripts/tts_align.py --input script.json --output storyboard.json \
    --voice en-US-ChristopherNeural --aspect 9:16   # add --offline for no-network runs
```

This voices each beat (edge-tts when reachable, otherwise a WPM estimate), probes exact durations via ffprobe, and writes `storyboard.json` with per-word syllable-weighted timestamps for karaoke captions. Voice stems land in `audio/` next to the board.

### Stage 3 — Storyboard

Edit `storyboard.json` (schema: `schemas/storyboard.schema.json`, checked by `scripts/storyboard.py`). Every scene requires `scene_id`, `archetype`, `duration_sec`, and `elements[]`. Elements render in array order: `background`, `grid`, `scaling_chart`, `phi_divider`, `tesseract`, `system_architecture`, `code_terminal`, `quote_card`, `hud_badge`, `stick_rig`, `kinetic_captions`, `image` (catalog with parameters: `references/storyboard-guide.md`). Keep visual beats ≤3.0 s — split longer clauses into sub-beats.

```bash
python3 scripts/storyboard.py storyboard.json          # validate only
```

### Stage 4 — Iterate, then Render & QC

```bash
python3 scripts/render_engine.py --storyboard storyboard.json --estimate      # frame count + audio cost, no render
python3 scripts/render_engine.py --storyboard storyboard.json --thumbnails /tmp/thumbs   # one PNG per scene, seconds
python3 scripts/render_engine.py --storyboard storyboard.json --output final.mp4 --quality final
python3 scripts/render_engine.py --demo --output demo.mp4                      # bundled 3-archetype showcase (~70s on 4 cores)
```

Inspect thumbnails before spending a full render; the bundled demo takes ~60–90 s (draft) on a 4-core CPU. Every frame is drawn at 2x target resolution (e.g. 2560x1440 → 1280x720) and BOX-averaged down (ideal SSAA kernel; ~3× cheaper than LANCZOS at integer scale); RGB-emissive primitives feed a dual-radius Gaussian bloom pyramid computed at half resolution; raw RGB frames pipe directly into ffmpeg (`libx264 -crf 18 -profile:v high -level 4.2 -pix_fmt yuv420p -movflags +faststart`); audio is synthesized offline (just-intonation pad ducked −12 dB under VO, SFX on a frame-accurate timeline, −1 dBFS ceiling) and loudnorm'd to −14 LUFS. After encoding, `verify_output.py` asserts streams, H.264/yuv420p, fps, resolution and ≤150 ms A/V drift — a failed gate exits 3.

## Hard Invariants

1. **yuv420p or nothing.** RGBA/yuv444p output fails on iOS/Safari/IG/TikTok. The encoder never overrides this.
2. **Audio before frames.** Frame counts derive from measured VO or explicit beat durations — never guessed.
3. **No linear motion.** Camera/UI motion goes through `easings.py` (`ease_out_expo`, `ease_in_out_cubic`, `spring_pop`…). `linear` exists for debugging only.
4. **2x supersample floor.** `SupersampledCanvas(..., scale>=2)` — Pillow has no sub-pixel AA on diagonals/circles.
5. **Safe zones are load-bearing.** 9:16 content lives inside `(84, 220) → (w-150, h-440)`; captions never collide with platform chrome (`canvas.layout_zones`).
6. **Claims match code.** If a feature is not in this repo and green under `pytest`, it does not ship. Manim/moviepy are deliberately out of scope.

## Verification

```bash
python3 -m pytest tests/ -q                                   # 107 tests
python3 scripts/render_engine.py --demo --output /tmp/demo.mp4 # full render + QC
python3 scripts/verify_output.py --input /tmp/demo.mp4 --storyboard examples/tri_archetype_storyboard.json
```

## Gotchas

- `edge-tts` needs network; Airplane mode ⇒ `--offline` (WPM-estimated timing; the online path carries measured edge-tts WordBoundary timestamps).
- 60 fps doubles render cost; use 30 fps for Shorts unless motion demands otherwise.
- `ImageDraw` has no alpha blend — scene fades are RGB `Image.blend`s; translucent panels use pre-blended slate tones, not RGBA overlays.
- Raster subject imagery ships via the `image` element (`src` absolute or relative to the storyboard; `fit` cover|contain; `kb_zoom` Ken Burns; `fade_in_sec`; `attribution` credit line — use it for license/AI-illustration disclosure). Full-bleed hero frames beat chart-only explainers for anything with a living subject.
- Raw video pipe expects `rgb24`, not `rgba` — changing `-pix_fmt` without changing `frame.tobytes()` corrupts every frame.
- `verify_output.py` drifting >150 ms almost always means `duration_sec` vs ffprobe VO mismatch — re-run `tts_align.py`, don't hand-tweak.

## Auxiliary Resources

- `references/archetypes.md` — full archetype field guide (palettes, beat density, SFX vocabulary, exemplar videos)
- `references/storyboard-guide.md` — element catalog, camera semantics, easings, safe zones, word timing
- `scripts/fetch_assets.py` — Openverse fetch: license-filtered (`by`/`by-sa`/`cc0`/`pdm` only), PIL-verified, writes `assets/manifest.json` with ready-to-use attribution strings
- `references/ffmpeg-encoding.md` — encoder/loudness/QC reference, platform targets
- `schemas/{storyboard,script,investigation_brief}.schema.json` — Draft 2020-12 contracts
- `examples/tri_archetype_storyboard.json` — renderable 3-scene showcase (`scripts/build_demo.py` regenerates)
- `scripts/` — `tts_align.py`, `storyboard.py`, `render_engine.py`, `verify_output.py`, `audio_dsp.py`, `camera.py`, `canvas.py`, `elements.py`, `rig.py`, `easings.py`, `build_demo.py`
- `docs/adr/0001-stdlib-first-verified-pipeline.md` — why stdlib+Pillow and no Manim/MoviePy
