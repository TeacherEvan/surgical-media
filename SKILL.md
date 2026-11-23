---
name: surgical-media
description: "Use when creating, planning, researching, or rendering social video for YouTube, Facebook or TikTok — including Shorts, Reels, explainers, news, comedy and multi-style hybrids that must show their real subject with attributed licensed photography, plus optional programmatic 2D/3D, TTS and hard QC."
version: 3.2.0
author: "TeacherEvan, Hermes Agent"
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [video, social-media, shorts, reels, tiktok, youtube, research, attribution, photography, image-first, ffmpeg, pillow, threejs, blender, tts, storyboard, safe-zones, licensing, qc]
    requires_tools: [terminal, read_file, write_file, search_files, web_search]
    related_skills: [video-production-pipeline, surgical-investigation, surgical-orchestration, surgical-audit]
---

# Surgical Media (v3.2.0) — Image-First Social Video Pipeline

Deterministic, monetization-safe path from a topic prompt to a verified MP4.
**The subject must be on screen.** Every capability ships as tested code (`tests/`).
## Step 1 — Mandatory intake

Before research or render, confirm three inputs; ask only for what is missing:
- **Time**: 30 s / 60 s / 90 s / 3 min / 10 min.
- **Style**: Comedic, Serious, Formal, Catchy, Poetic, Artistic, or a tonal arc.
- **Platform**: YouTube Long 16:9 / Shorts 9:16, Facebook Feed 4:5 / Reels 9:16, TikTok 9:16, or master + adapted exports.
Resolve the contract: `python3 scripts/pipeline_preflight.py --time 60 --style comedic --platform tiktok --intake-out intake.json`
## Step 2 — Live spec & technique refresh

`python3 scripts/spec_refresh.py --check [--fetch] --out spec_report.json` (exit 3 = drift).
Probe the host with `python3 scripts/tool_probe.py --out capabilities.json`. Never
render against an unverified assumption.
## Step 3 — Research & acquire subject imagery (BEFORE scripting)

Emit a brief against `schemas/investigation_brief.schema.json` (≥3 sourced facts →
visual anchors + `visual_assets`). Fetch licensed subject photographs **before** writing
narration — one query per beat, not one for the whole video:
`python3 scripts/fetch_scene_assets.py --input script.json --out-dir assets --subject "<subject>" --count 3`
(`--dry-run` prints the derived query plan; explicit per-scene `visual.query` wins).
Named real people require authentic photos (Wikimedia/Wikipedia/press rooms), never
AI stand-ins without approval: `scripts/media_harvester.py`. Log outlet/headline/date/URL
per claim; keep `credits.json` + `CREDITS.md` with AI-disclosure flags.
## Step 4 — Write an image-directed beat script

`schemas/script.schema.json` now supports `subject` and per-scene `visual`:
`{"kind":"photo","query":"emperor penguin","fit":"backdrop_blur"}`.
`visual.image` pins a specific plate; `kind: "svg"|"3d"|"procedural"` opts a beat
out of auto-imagery only when the visual itself carries meaning. One `visual.query`
per distinct subject angle — never leave every scene to generic filler.
## Step 5 — Audio-first timing + image wiring

Never lock frames before audio. Then wire the fetched plates into the board:
```
python3 scripts/tts_normalizer.py --input script.json --output script.spoken.json
python3 scripts/tts_align.py --input script.spoken.json --output storyboard.json \
    --voice en-US-ChristopherNeural --aspect 9:16 \
    --subject "<subject>" --assets-manifest assets/manifest.json --brief investigation.json   # --offline if no network
python3 scripts/style_apply.py --intake intake.json --board storyboard.json --out storyboard.styled.json
python3 scripts/storyboard.py storyboard.styled.json
```
`tts_align` strips generic `placeholder: true` filler, inserts full-bleed subject
plates with Ken Burns + manifest attribution, and warns on unplated scenes. Standalone
boards: `python3 scripts/asset_wire.py --board board.json --manifest assets/manifest.json --out board.wired.json`.

**Local voice (default when installed).** `tts_align --engine auto` prefers the
local Kokoro-82M engine over edge-tts — no network, no API key, default voice
`af_heart`. One-time setup: `bash scripts/setup_kokoro.sh` (creates a Python 3.12
venv, downloads the 89 MB quantised ONNX model + voice bank to
`~/.cache/surgical-media/kokoro`). Override with `--engine kokoro --kokoro-voice
af_heart` (or a script-level `kokoro_voice` field). Kokoro's export has no duration
output, so word spans are allocated from the model's own phoneme lengths. Keep
`--engine edge` for the old network path, or `--offline` for WPM estimates.
`storyboard.styled.json` is the single locked timeline. Then estimate → thumbnails → render:
```
python3 scripts/render_engine.py --storyboard storyboard.styled.json --estimate
python3 scripts/render_engine.py --storyboard storyboard.styled.json --thumbnails /tmp/thumbs
python3 scripts/render_engine.py --storyboard storyboard.styled.json --output final.mp4 --quality final
```
## Step 6 — Topic-matched intro & outro

No generic bumper. Short-form: 0.5–3 s hook + kinetic topic stamp readable muted;
close with a callback/loop. Long-form: 3–10 s thematic cold-open; close with payoff,
one CTA and a credit roll from `CREDITS.md`.
## Step 7 — Hard QC gate (image-first is enforced)
```
python3 scripts/pipeline_preflight.py --board storyboard.styled.json --intake intake.json --brief investigation.json
python3 scripts/style_lint.py storyboard.styled.json --manifest assets/manifest.json
python3 scripts/qc_gate.py --video final.mp4 --format 9:16 --preset strict --frames-dir qc_frames --credits CREDITS.md --json qc_report.json
python3 scripts/monetization_gate.py --board storyboard.json --manifest assets/manifest.json --script script.spoken.json
python3 scripts/thumbnail_gen.py --storyboard storyboard.json --out publish/thumbnail.jpg
```
`pipeline_preflight` fails (`subject_imagery`) if <60% of scenes show the subject, if
filler remains without its own visual, or if brief `visual_assets` are never shown.
`style_lint` flags `no_subject_imagery`, `low_visual_coverage`, `placeholder_visual`,
`unused_assets`. Inspect the audit PNGs (Frame 1 / mid / outro) for safe-box compliance.
## Style archetypes

Per-scene `archetype`: `geometry_rig` (fast kinetic gags), `doc_essay` (photo essay +
charts), `code_report` (DAGs/diffs), `mixed`. Archetypes are **overlays on photos**,
not replacements. Field guide: `references/archetypes.md`; matrix: `references/style-and-architecture.md`.
## 3D backends (optional accent only — never the default)

`scene_spec` routes to `threejs_*`/`blender_*`/`canvas_2d` (categories: exploded_hardware_3d,
orbital_or_field_3d, organic_serpent_3d, network_topology_3d, external_asset_3d).
Use one hero 3D beat when it explains structure a photo cannot; never fill a whole
video with procedural geometry. Stdlib `software_3d_projection.py` always works.
## Hard invariants

1. **Subject on screen** — photo/SVG/map/mockup or authored 3D in ≥60% of scenes; no filler-only beats. No default-3D-and-captions videos.
2. **yuv420p or nothing** — RGBA/yuv444p fails iOS/IG/TikTok.
3. **Audio before frames** — counts from measured VO or explicit beats.
4. **No linear motion** (`easings.py`); **2x supersample floor**; **safe zones load-bearing** (organic 9:16 `(84,220)→(w-150,h-440)`; strict ad-safe `x=65..888, y=288..1248`).
5. **Credits travel with plates** — manifest attribution on every `image`; captions/credits stay boxless.
6. **Claims = code** — no NumPy in audio/geometry; Three.js/Blender optional; tests green before ship.
## Verification

`bash scripts/ci_gates.sh` — examples → ruff → format → mypy --strict → pytest →
schema metaschema → thumbnails (2D + **photo** + hybrid 3D + Three.js 3D) → draft
render + ffprobe QC → style_lint (advisory) → jobs → loudness/safe-zone audit. Exit 3 = fail.
## Gotchas

- `edge-tts` needs network → local Kokoro (`--engine auto`/`kokoro`) is preferred when installed; `--offline` uses WPM estimates. Measured WordBoundary beats win on the edge path.
- No word re-splitting: wrap the measured token stream.
- Photos: `image` (cover|contain|backdrop_blur) + `kb_zoom`; `Image.blend` fades. 9:16 default `backdrop_blur`; auto credit at y≈1060 sits **above** captions (`y_anchor≈0.6`) — do not move it to 1150.
- Never stack opaque `quote_card`/dark boxes on a photo; captions and credits are stroked, boxless.
- Clean audio: no synthetic pads or procedural SFX (`pop`/`chime`/…) without a real `wav`; use `trauma` for camera-only shake.
- `meta.visual_intent` (`procedural_showcase`/`style_reference`/`abstract_art`) is the **only** imagery-gate opt-out, for genuine abstract work.
## References

`references/specs-licensing-compliance.md` · `{style-and-architecture,pipeline-scripts,render-templates,storyboard-guide,archetypes,ffmpeg-encoding,job-workflow}.md` · `examples/photo_essay_storyboard.json` (image-first reference).
