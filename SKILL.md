---
name: surgical-media
description: "Use when creating, planning, researching, or rendering social video for YouTube, Facebook or TikTok — including Shorts, Reels, explainers, news, comedy and multi-style hybrids that need real attributed photos, programmatic 2D/3D rendering and hard QC."
version: 3.0.0
author: "TeacherEvan, Hermes Agent"
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [video, social-media, shorts, reels, tiktok, youtube, research, attribution, ffmpeg, pillow, threejs, blender, tts, storyboard, safe-zones, licensing, qc]
    requires_tools: [terminal, read_file, write_file, search_files, web_search]
    related_skills: [video-production-pipeline, surgical-investigation, surgical-orchestration, surgical-audit]
---

# Surgical Media (v3.0.0) — Priority Social Video Pipeline

Deterministic, monetization-safe, research-backed path from a topic prompt to a verified MP4.
**This is the priority pipeline for all future surgical-media content.** Every capability below
ships as tested code (`tests/`); prose never outruns implementation.
## Step 1 — Mandatory intake

Before research or render, confirm three inputs; ask only for what is missing:
- **Time**: target runtime (30 s, 60 s, 90 s, 3 min, 10 min).
- **Style**: Comedic, Serious, Formal, Catchy, Poetic, Artistic, or all of the above (propose a tonal arc for hybrids).
- **Platform**: YouTube Long 16:9 / Shorts 9:16, Facebook Feed 4:5 / Reels 9:16, TikTok 9:16, or master + adapted exports.
Resolve into a locked contract: `python3 scripts/pipeline_preflight.py --time 60 --style comedic --platform tiktok --intake-out intake.json`
## Step 2 — Live spec & technique refresh

Verify the baked spec baseline, then web-search current caps, Content ID / originality /
AI-disclosure rules and library releases:
`python3 scripts/spec_refresh.py --check [--fetch] --out spec_report.json` (exit 3 = drift).
Probe the host with `python3 scripts/tool_probe.py --out capabilities.json`. Update the
reference's date when anything changed; never render against an unverified assumption.
## Step 3 — Research, real people, subtle attribution

Emit a brief against `schemas/investigation_brief.schema.json` (≥3 sourced facts → visual
anchors). Fetch licensed subject imagery **before** writing the script:
`python3 scripts/fetch_assets.py --query "<subject>" --out-dir assets --count 3`.
Named real people require authentic high-res photos (Wikimedia/Wikipedia/press rooms), never AI
stand-ins without approval. For portraits with safe-zone credit badges use
`python3 scripts/media_harvester.py --query "<person>" --people "<person>" --out-dir assets --aspect 9:16`.
Log outlet, headline, date and URL for every claim; keep `credits.json` + `CREDITS.md` with
AI-disclosure flags.
## Step 4 — Collaboration & tooling pitch

After research, **pause and pitch**: flag ambiguity or sensitive claims, propose a sharper hook,
visual metaphor, 3D hero shot or pacing change, and recommend an optional engine (Blender, Three.js,
Revideo, Manim, WhisperX, Kokoro/Qwen3-TTS) with a payoff. Install only after confirmation;
licensing: `references/specs-licensing-compliance.md`.
## Step 5 — Audio-first multi-engine production

Never lock frames before audio. Normalize spoken text, then time the board:
```
python3 scripts/tts_normalizer.py --input script.json --output script.spoken.json --report normalization.json
python3 scripts/tts_align.py --input script.spoken.json --output storyboard.json --voice en-US-ChristopherNeural --aspect 9:16   # --offline if no network
python3 scripts/style_apply.py --intake intake.json --board storyboard.json --out storyboard.styled.json --report style_changes.json
python3 scripts/storyboard.py storyboard.styled.json
```
`storyboard.styled.json` is the single locked timeline (fps, bt709, word spans, SFX); `style_apply.py`
writes the 7-style matrix into it, `pipeline_preflight.py` verifies it. Engines: `references/style-and-architecture.md` §4 —
Pillow/`elements/` for 2D, `blender_runner.py`/`threejs_bridge.py` for 3D (stdlib fallback), external Revideo/Manim only when justified. Then:
```
python3 scripts/render_engine.py --storyboard storyboard.styled.json --estimate
python3 scripts/render_engine.py --storyboard storyboard.styled.json --thumbnails /tmp/thumbs
python3 scripts/render_engine.py --storyboard storyboard.styled.json --output final.mp4 --quality final
```
## Step 6 — Mandatory topic-matched intro & outro

No generic bumper. Short-form: fuse the intro into a 0.5–3 s hook + kinetic topic stamp that
reads with audio muted; close with a callback or loop back to Frame 1. Long-form: 3–10 s
thematic cold-open; close with payoff, one CTA and a compact credit roll from `CREDITS.md`.
## Step 7 — Hard QC gate
```
python3 scripts/pipeline_preflight.py --board storyboard.styled.json --intake intake.json --brief investigation.json
python3 scripts/qc_gate.py --video final.mp4 --format 9:16 --preset strict --frames-dir qc_frames --credits CREDITS.md --json qc_report.json
python3 scripts/monetization_gate.py --board storyboard.json --manifest assets/manifest.json --script script.spoken.json
python3 scripts/thumbnail_gen.py --storyboard storyboard.json --out publish/thumbnail.jpg
```
`qc_gate.py` exit 3 = do not deliver. Inspect the red-overlay PNGs (Frame 1 / mid / outro) for
faces, captions and credits inside the safe box, and confirm every asset is in `CREDITS.md`.
## Style archetypes

Blend per scene via `archetype`: `geometry_rig` (IK stick figure, spiral, tesseract; SFX-locked),
`doc_essay` (charts + glass quote cards; 150–165 WPM), `code_report` (DAG cascade, diff terminal,
trauma shake; 175–195 WPM), `mixed`. Field guide: `references/archetypes.md`; 7-style matrix and
originality gate: `references/style-and-architecture.md`.
## 3D backends (optional)

`scene_spec` routes to `threejs_hybrid|threejs_3d|blender_hybrid|blender_3d|canvas_2d`
(categories: exploded_hardware_3d, orbital_or_field_3d, organic_serpent_3d,
network_topology_3d). Stdlib `software_3d_projection.py` always works; Three.js needs Node ≥22
+ Chromium, Blender ≥3.6 optional. New assets require all three generators + tests + docs.
## Hard invariants

1. **yuv420p or nothing** — RGBA/yuv444p fails iOS/IG/TikTok.
2. **Audio before frames** — counts from measured VO or explicit beats, never guessed.
3. **No linear motion** — use `easings.py`; `linear` is debug-only.
4. **2x supersample floor** — `SupersampledCanvas(scale>=2)`.
5. **Safe zones are load-bearing** — organic `(84,220)→(w-150,h-440)`; strict ad-safe
   `x=65..888, y=288..1248` on 1080x1920 (see `references/specs-licensing-compliance.md`).
6. **Claims = code** — if it is not in `tests/` and green, it does not ship. No NumPy in
   audio/geometry; Three.js/Blender optional.
## Verification

`bash scripts/ci_gates.sh` — storyboard → ruff → format → mypy --strict → full `pytest` →
schema metaschema → example validation → thumbnails → draft render + ffprobe QC → advisory
style_lint. A failed gate exits 3.
## Gotchas

- `edge-tts` needs network → `--offline` uses WPM estimates; measured WordBoundary beats win.
- `ImageDraw` has no alpha blend: pre-blend panels; RGB `Image.blend` for fades. Subject photos
  go through the `image` element (`fit` cover|contain|backdrop_blur, `kb_zoom`, `attribution_y`).
- >150 ms A/V drift means `duration_sec` vs VO mismatch — re-run `tts_align.py`, never hand-tweak.
- Shorts >60 s + commercial music still draws Content ID claims; prefer procedural audio and a
  Private upload pre-check. WebGL must be virtual-clock captured, never screen-recorded.
## References

`references/specs-licensing-compliance.md` (caps/safe zones/licenses) ·
`{style-and-architecture,pipeline-scripts,render-templates,storyboard-guide,archetypes,ffmpeg-encoding,job-workflow}.md` (matrix, CLI, engine map, elements, personas, encoder, jobs).
