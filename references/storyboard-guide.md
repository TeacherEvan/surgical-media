# Storyboard Guide

`storyboard.json` is the single source of truth — validated by `scripts/storyboard.py` and enforced by the JSON Schema at `schemas/storyboard.schema.json`. The render fails fast on any contract breach.

## Top level

```jsonc
{
  "meta":  { "title": "…", "author": "…", "seed": 20261118 },   // seed → deterministic frames
  "format":{ "width": 1920, "height": 1080, "fps": 30 },         // fps ∈ 24/25/30/50/60
  "scenes":[ … ],
  "audio": { "pad": true, "pad_level": 0.055, "duck_depth": 0.72, "sample_rate": 48000 }
}
```

## Scene

```jsonc
{
  "scene_id": "cascade",                 // [a-z0-9_-]+
  "archetype": "code_report",            // geometry_rig | doc_essay | code_report | mixed
  "narration": "The pool did not.",      // optional but recommended
  "start_sec": 9.2,                      // auto-assigned if omitted
  "duration_sec": 5.2,                   // required; derives from VO or beat length
  "vo_wav": "audio/cascade.wav",         // absolute, or relative to the storyboard file
  "fade_in_sec": 0.3, "fade_out_sec": 0.4,
  "camera": { "zoom_start": 1.0, "zoom_end": 1.06, "pan_x": 0.5, "pan_y": 0.46,
              "easing": "ease_in_out_cubic", "shake_amplitude_px": 11.0 },
  "elements": [ … ],                     // paint order = array order
  "words": [ { "word": "The", "start": 0.00, "end": 0.28 }, … ],  // scene-LOCAL seconds
  "sfx_events": [ { "t_sec": 3.0, "sfx": "error_buzz", "intensity": 1.0 } ]
}
```

`start_sec` values are auto-assigned sequentially when omitted. `words` are **scene-relative** (0 = scene start); `sfx_events[].t_sec` too. The mixer offsets both by `start_sec`. When edge-tts is reachable, `words` carry the service's measured WordBoundary timestamps (100 ns ticks); offline runs fall back to a syllable-weighted model fit to the measured scene duration.

### Camera

Screen = `(world − center) · zoom + viewport_center + shake`. `center` derives from normalized `pan_x/pan_y`. Zoom interpolates `zoom_start → zoom_end` through `easing`; zoom is clamped to `[1.0, 10.0]`. `shake_amplitude_px` enables a deterministic trauma shake (quadratic decay) — trigger it with `{"sfx": "trauma"}` events; no other event shakes the camera.

### Easings

`linear` (debug) · `ease_out_expo` (camera zooms, playheads) · `ease_in_out_cubic` (pans) · `ease_in_out_sine` (idle drift) · `ease_out_back` (pop) · `spring_pop` (badges, locks; overshoots).

### Safe zones (design px)

| Aspect | Zone |
| :--- | :--- |
| 16:9 | `(96, 64) → (w−96, h−64)`, stage inset 12.5% |
| 9:16 | `(84, 220) → (w−150, h−440)` — clears Shorts/Reels/TikTok chrome |
| 1:1  | `(80, 80) → (w−80, h−80)` |

HUD band = top ~12–14%, primary stage = next ~66–76%, caption strip = remainder. `kinetic_captions` centers inside the caption band automatically.

## Element catalog

All coordinates are **design-space pixels** (the target width/height — not the 2x supersampled buffer).

### `background` — `{ "type": "background", "color": "#050508" }`
Full-viewport fill. Painted through the camera but oversized ±4×, so shake never reveals void.

### `grid` — `{ "type": "grid", "spacing": 90, "color": "#131B2E" }`
Unit grid lines; spacing in px. Keep color close to canvas (it is geometry, not content).

### `hud_badge` — `{ "type": "hud_badge", "text": "01 · SCALING", "corner": "tl" }`
Corner: `tl` / `tr` / `tc`. Spring-pops in over 0.55 s; gold capsule, monospace.

### `scaling_chart` — `{ "exponent": 4.35, "odometer_from": 1.0, "odometer_to": 500.0, "accent": "#38BDF8", "label": "FRONTIER COMPUTE", "odo_suffix": "×", "odo_decimals": 1, "milestones": [{"u": 0.25, "tag": "10×"}], "box": [x0, y0, x1, y1] }`
Exponential curve with playhead + milestone badges (defaults `10×/100×/500×` at u=0.25/0.5/0.78; override with `milestones`, `[]` disables) + geometric odometer (`from → to`). `odo_suffix` defaults to `×` — set e.g. `" m"`/`" km"`/`" %"` for physical quantities. `box` optional.

### `phi_divider` — `{ "box": [x0, y0, x1, y1] }`
Recursive golden-rectangle construction + quarter-circle arcs; `φ = 1.618034` readout; `LOCK` bloom after `t > 0.78`. Default box `[0.2W, 0.32H, 0.8W, 0.62H]`.

### `tesseract` — `{ "cx": 990, "cy": 200, "size": 78, "phase": 0.4 }`
Rotating 4D hypercube (XW/YZ/XY planes), stereographic R4→R3 + perspective R3→R2. Near edges bloom gold; far edges dim to `#…4A3A00`.

### `system_architecture` — see `examples/tri_archetype_storyboard.json`
```jsonc
{ "type": "system_architecture",
  "nodes": [ { "id": "lb", "label": "L7 LOAD BALANCER", "x": 320, "y": 215, "role": "source" },
             { "id": "ex1", "label": "EXCHANGE-EU-1", "x": 880, "y": 105, "role": "exchange" } ],
  "cascade_start": 1.35, "cascade_step": 0.55 }
```
Cubic-bezier edges, 2 packet dots per route, `200 OK` (green, `#50FA7B`) → `503 TLS POOL` (red, `#FF5555`) in declaration order. First node or `role:"source"` is the origin. Pair the final flip with `{"sfx":"trauma"}`.

### `code_terminal` — `{ "box": [x0, y0, x1, y1], "title": "health.log", "lines": [{"text": "…", "kind": "normal|add|del|comment|accent"}] }`
Diff-row tinting (`add` → green tint/`#7EE787`, `del` → red tint/`#FFA198`, `comment` → `#8B949E`), gutter numbers, progressive line reveal tied to scene `t`, blinking block cursor on the revealed tail.

### `quote_card` — `{ "quote": "…", "attribution": "…", "box": [x0, y0, x1, y1] }`
Gold glyph, ≤ 4 wrapped lines (measured wrap, 4-line clip), slate `#111C31` card with specular `#2B3A55` border.

### `stick_rig` — `{ "x": 640, "y": 672, "height": 300, "reach_to": [640, 345], "reach_side": "right" }`
Hollow-head IK figure (law-of-cosines two-bone solve). `reach_to` is a world-space design point the hand tracks; omit for idle sway. Feet at `y` (ground). Deterministic bob from scene-local time.

### `image` — `{ "type": "image", "src": "assets/hero.png", "box": [0, 220, 720, 840], "fit": "cover", "kb_zoom": 1.10, "fade_in_sec": 0.8, "radius": 24, "attribution": "AI ILLUSTRATION" }`
Raster imagery: cover (fills box, center-crop), contain (letterbox), or backdrop_blur ("social bleed": blurred, dimmed cover-crop behind the fully visible contained plate — ideal for landscape plates on 9:16 canvases; optional `blur`, `dim` (default 0.72), `anchor_y` (0 = top, 0.5 = centered, 1 = bottom), `radius` rounds the plate only). Ken Burns drift (`kb_zoom` 1.0→N over the scene), fade-in from black (`fade_in_sec`). `src` is absolute or relative to the storyboard file. Use `scripts/fetch_assets.py` to acquire licensed plates; its manifest emits ready-to-paste `attribution` strings. Painted screen-fixed (no camera transform — a full-bleed plate must not pan) with LRU caching by resolved path; pair camera pans on vector elements for parallax. `attribution` draws a dim credit line in the box's lower-left; `attribution_y` (optional, design-space px) lifts the credit to an absolute y — use it on 9:16 plates so the credit clears Shorts' bottom chrome (e.g. `1150`) — use it for licenses or AI-illustration disclosure. Draw text/HUD over full-bleed images with `kinetic_captions` last for the caption backdrop.

### `kinetic_captions` — `{ "type": "kinetic_captions", "accent": "#FFD700", "size": 22 }`
Reads the scene's `words` array; word-by-word karaoke in the caption band. `accent` (current word) and `size` optional.

## Scene backends (optional — `scene_spec` + `backend`)

A scene with `scene_spec` replaces the `elements[]` requirement and routes to a parametric 3D backend. `backend`: `auto` (default; routes on category/keywords), `blender_hybrid`, `blender_3d`, `canvas_2d`, `manim_math` (accepted, lints a warning, renders as canvas_2d). Paint order: 3D pass or pre-baked Blender plate → HUD (`blender_hybrid` only) → `elements[]` (if any) on top → fades.

```jsonc
{ "scene_id": "cowos_stack", "archetype": "mixed", "duration_sec": 1.5,
  "backend": "auto",
  "scene_spec": {
    "category": "exploded_hardware_3d",   // or orbital_or_field_3d, organic_serpent_3d (others: rejected at validation)
    "hud_title": "EXPLODED COWOS-STYLE PACKAGE STACK",
    "explode_factor": 1.15,
    "camera_3d": { "mode": "orbit", "focal_length_mm": 50.0, "fstop": 2.8,
                   "radius_start": 7.6, "radius_end": 6.4,
                   "azimuth_start_deg": -38.0, "azimuth_end_deg": 32.0, "elevation_deg": 24.0 },
    "anchors_3d": [ { "anchor_id": "anchor_compute_die", "label": "5nm AI Compute Die",
                      "metric": "4,500 FP8 TFLOPS", "local_pos": [0.55, -0.55, 0.35],
                      "accent_hex": "#FACC15" } ] },
  "sfx_events": [ { "t_sec": 0.05, "sfx": "whoosh", "intensity": 0.6 } ] }
```

Rendering paths: with Blender ≥ 3.6 on PATH, each blender_hybrid/blender_3d scene is pre-baked into the work dir (`blender -b -P scripts/blender_runner.py -- --spec …`, PNG sequence + `anchor_tracks.json`; failure → warn + software fallback, render continues). Otherwise — and always for `--thumbnails` — `scripts/software_3d_projection.py` renders a 4×4-perspective painter’s-algorithm pass with stdlib math and returns the same normalized `(u, v, z_depth)` anchor contract. HUD cards (blender_hybrid) are placed by `scripts/layout_solver.py` (AABB min-axis separation; locked HUD header + center-stage repulsor; 24 px canvas clamp) and painted by `scripts/hybrid_compositor.py` (reticles, 45° elbow leaders, glass cards, spring-pop reveal). Runtime-computed tracks with `visible: false` are skipped (board `anchors_3d` cannot set `visible`). `camera_3d.mode` supports `orbit` only and `lighting_preset` supports `cyber_studio_volumetric` / `clean_product_softbox`; camera defaults are shared between both renderers. Full example: `examples/hybrid_3d_storyboard.json`.

## `sfx_events`

`pop` · `whoosh` · `chime` · `confirm` · `type_click` · `error_buzz` — synthesized offline, mixed at scene offset, ducked pad, −1 dBFS ceiling, loudnorm −14 LUFS on mux.
`trauma` — camera-only; no audio. `intensity` scales SFX or shake (0.1–1.0).

## Validation & failure modes

`scripts/storyboard.py board.json` prints one line per violation with the owning scene — fix and re-run; `render_engine.py` refuses to start on any violation. Most common: `sfx_events[].t_sec` beyond `duration_sec` (trim the event or extend the beat), and `zoom_*` outside `[1.0, 10.0]`.
