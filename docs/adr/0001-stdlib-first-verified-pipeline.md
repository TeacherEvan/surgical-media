# ADR 0001 — Stdlib-First, QC-Gated Pipeline (No Manim, No MoviePy, No NumPy)

**Status:** Accepted (2026-11-18)
**Context:** The original concept document (`Concept/surgical-media-concecpt.txt`) described a two-phase evolution of a Gemini-chat skill: a v1 with fixed flaws (post-raster crop/stretch camera, flat strokes, hardcoded safe zones, VO ignored in the mixer, uniform-index word timing), and a v2 "10-file bundle" whose ZIP was claimed but never verified. The family audit (2026-11-15) flags claim-heavy skills whose stated architecture does not exist as tested code. Three questions needed deciding before this skill could ship as `surgical-media`:

1. **Rendering substrate:** Manim CE gives cinematic math animation but pulls in cairo/LaTeX/scipy; MoviePy wraps ffmpeg but re-encodes through temp frame files by default. Both raise the install floor far above "Pillow + ffmpeg present".
2. **Numerics:** NumPy accelerates per-sample audio loops but is not guaranteed present on target hosts (this machine's system Python 3.15 lacks it).
3. **Verification:** The concept claimed ffprobe QC without shipping an assertion script.

**Decision:**
- Render with **Pillow only** at 2x supersampling + LANCZOS downsample; no GPU, no LaTeX, no cairo.
- Audio synthesis and mixing are **pure stdlib** (`wave`, `math`, `array`, `random` with fixed seed). NumPy is explicitly rejected — the per-sample Python loops cost ~1–2 s per 15 s of audio, which is noise next to Pillow rasterization.
- **edge-tts is optional.** `--offline` (WPM-estimated, syllable-weighted) is a first-class path, so renders and tests never require network.
- **QC is mandatory by default.** `render_engine.py` runs `verify_output.verify_mp4` after encoding; drift >150 ms or a missing stream/pix_fmt exits 3. `--no-verify` exists for bisection only.
- **Claims = code.** Every capability advertised in SKILL.md maps to `scripts/` + `tests/` (68 tests, including rendering and QC-ing a real MP4 offline).

**Consequences:**
- (+) `pip install Pillow` + ffmpeg is the entire install story; the skill runs anywhere Python does, including CPU-only containers and CI.
- (+) Deterministic: identical storyboard ⇒ identical frames (seeded noise, no wall-clock dependence) and identical audio (fixed seeds).
- (−) No physics simulation, no GPU particle effects, no LaTeX-typeset math. Documentary-grade math animation (exact integral curves, proper TeX) remains out of scope; `phi_divider` and `tesseract` are vector constructions, not symbolic engines.
- (−) 60 fps full-HD renders cost real CPU. Mitigation: `--quality draft` (veryfast preset, crf 26), 30 fps default, and the safe-zone precomputation keep iteration loops seconds-per-frame on modest hardware.


## Postscript (2026-11-18, v1.1 perf pass)

Profiling the v1.0.0 render showed `Canvas.final()` at ~320 ms/frame (72% of wall time). Root causes and fixes, all landed with the 72-test suite green; the 73rd (custom odometer units), 74th (short-VO-stem envelope guard) and 75th–78th (measured WordBoundary karaoke timing; attribution auto-fit; caption re-tokenize fix) followed:

- Per-pixel `Image.point(lambda)` halo scaling → `Image.blend(black, wide, 0.6)` (C-level).
- Dual Gaussian bloom pyramid → computed at half resolution (bloom is low-frequency by construction).
- Integer 2x downsample LANCZOS → `BOX` (the exact SSAA average kernel).
- RGBA→RGB buffer conversion eliminated — buffers are RGB end-to-end (ImageDraw cannot alpha-blend anyway; translucency is pre-blended into opaque tones).
- Per-point camera easing evaluation in `_tp`/`_tw`/`text` → frame-baked affine state (`set_frame` computes `zoom_at`, center, shake offset once).
- `ImageFont.truetype` cache (`_FONT_CACHE`) and `parse_color` memo (`_COLOR_CACHE`).
- Peak limiter scans in `audio_dsp` collapsed into the fill loops.

Export path dropped ~320 → ~108 ms/frame (≈3×); the 14.4 s / 432-frame demo render fell from ~165 s to ~70 s on a 4-core CPU. Also added: `--estimate` (cost preview), `--thumbnails DIR` (one representative PNG per scene for agent self-inspection), and `lint_storyboard` non-fatal warnings (unknown element types, out-of-canvas boxes, missing `vo_wav`).
