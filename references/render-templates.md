# Render templates → shipped implementations

The "studio pro" templates (Blender bpy, Three.js + Playwright, FFmpeg mastering) are real
code here — do not rewrite them per project. Use the mapping below and read the named file
before inventing a new pass. All three backends consume the same `storyboard.json` grid.

## 1. Blender bpy headless → `scripts/blender_runner.py` / `blender_plate.py`

- Per-scene 3D bake: `scene_spec.category` routes to a builder in `blender_runner.py`
  (exploded hardware, orbital/field, organic serpent, network topology).
- EEVEE/Cycles auto-detected; motion blur on; `world_to_camera_view` anchors exported so
  `hybrid_compositor.py` can pin glass HUD cards without collisions.
- Plate-only path: `python3 scripts/blender_plate.py --kind earth --out plate.png` — returns
  exit 2 cleanly when Blender is absent; the stdlib renderer always works.
- Self-contained topic intro/outro: build as a `scene_spec` scene with `hud_title` and
  `camera_3d`, not as an external .blend the viewer must supply.

## 2. Three.js + Playwright virtual clock → `scripts/threejs_bridge.py` + `scripts/threejs/`

- The "step a virtual clock frame-by-frame" pattern is already implemented over **native
  Node CDP** — no `playwright` npm dependency, no real-time screen capture, zero dropped
  frames. `runner.mjs` drives `stage.html`; `scenes.mjs` holds the scene generators.
- Capability probe: `python3 scripts/threejs_bridge.py --check` (Node ≥22, local Chromium,
  `three` under `scripts/threejs/node_modules`). If unavailable, `scene_router.py` falls
  back to `software_3d_projection.py` automatically.
- `svg_raster.mjs` upgrades static SVG to full SVG 2.0 (gradients, filters, `evenodd`)
  when Chromium is available; `elements/svg.py` is the offline stdlib path.
- Custom project scene = a `params.threejs_script` module beside the board; register it
  per project, never by editing the shared `scenes.mjs` in place without tests.

## 3. FFmpeg mastering → `render_engine.py` + `verify_output.py` + `qc_gate.py`

- `render_engine.py` draws every frame at 2x and BOX-downsamples, pipes raw RGB to ffmpeg
  (`libx264 -crf 18 -profile:v high -level 4.2 -pix_fmt yuv420p +faststart`), synthesizes
  the audio bed, and runs an inline ffprobe QC (exits 3 on failure).
- `verify_output.py` asserts streams, codec, pixel format, fps, resolution and ≤150 ms A/V
  drift. `qc_gate.py` adds ebur128 loudness, silencedetect, and the red safe-zone overlays.
- Ken Burns on still photos is done **inside the Pillow painter** (`elements/media.py`,
  `kb_zoom`) at 2x supersampling — never with raw `zoompan` on 1080p integers, which jitters.
- Sidechain ducking lives in `audio_dsp.py`; set `audio.duck_depth` deeper for voice-led 9:16.

## 4. Optional external engines (not bundled)

| Engine | Use when | Constraint |
| :--- | :--- | :--- |
| Revideo / Motion Canvas (MIT) | Data-driven React/TS motion that outgrows Pillow | self-hosted; commercial-safe |
| Remotion | Existing React pipeline, team ≤3, no batch/SaaS | license thresholds apply — see `specs-licensing-compliance.md` |
| Manim CE | Mathematical or statistical derivation animation | external; in-repo `manim_math` backend warns and renders 2D |
| Faster-Whisper / WhisperX | Word-level caption alignment when edge-tts boundaries are unavailable | local models; keep `content_hash` in `credits.json` |
| Kokoro / Qwen3-TTS / Orpheus | Commercial-safe local narration | run `tts_normalizer.py` first; see license matrix |

Installing an optional engine is a Step-4 collaboration decision: propose it with a one-line
payoff, confirm licensing and `tool_probe.py` output, then use it. Never make it a hard
dependency of the deterministic path.

## 5. Master recipe (short-form 9:16)

```bash
python3 scripts/tts_normalizer.py --input script.json --output script.spoken.json
python3 scripts/tts_align.py --input script.spoken.json --output storyboard.json --aspect 9:16
python3 scripts/storyboard.py storyboard.json
python3 scripts/render_engine.py --storyboard storyboard.json --output final.mp4 --quality final
python3 scripts/qc_gate.py --video final.mp4 --format 9:16 --preset strict \
    --frames-dir qc_frames --credits CREDITS.md --json qc_report.json
python3 scripts/monetization_gate.py --board storyboard.json --manifest assets/manifest.json --script script.spoken.json
```

`qc_gate.py` exit 3 = do not deliver. Fix the board, not the gate.
