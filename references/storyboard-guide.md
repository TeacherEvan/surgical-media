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

## Visual Grammar — how scenes come alive

Rich videos are **stacked layers**: a hero motion, a payload (caption/diagram/quote), an emphasis beat, and a sound. The default look is fine, but the biggest quality lever for agents is motion — most of today's flat output is because nothing moves after the pop.

**Layer stack per scene (pick 1–3 of these):**

1. **Hero motion** — one moving visual: `orb_pulse` heartbeat, `orbit_ring` spin, `typewriter_text` reveal, `equalizer` bars, camera `orbit`/`static`, `dot_field` drift, `leader_arrow` walkthrough. Under-used: many agents only move text.
2. **Payload** — story on top (`hud_badge`, `caption`, `quote_card`, `scaling_chart`, `system_architecture`, …).
3. **Emphasis** — pops timed to words (`pop` springs, scale-pop) or milestones.
4. **Sound** — `sfx_events` on beats (`pop`, `whoosh`, `chime`, `error_buzz`…).

**Rules of thumb:**

- **No dead frames.** Idle is OK as the *start* of a beat, but by ~60–70% of a beat something should move (the hero motion, a pop, a stroke-draw). If every element is static at the same moment, the frame is dead — split the beat.
- **One hero per scene.** Two spinners + a pulse at full size = visual mud. Stack **personality** painters around the hero: `dot_field` faintness behind, `kinetic_captions` on top.
- **Camera is motion too.** `zoom` (default) is safe but motionless; when the script benefits, use `orbit` (a turn around the subject) or `static` (frozen). A slow `ease_out_expo` zoom-in is a classic tension beat — put it in on a hook scene, then `static` for the deep beats.
- **Motion leads, payload follows.** Pops/reveals at the start of a beat, the caption/quotes after — the eye sees motion first.
- **Payload sizing rule.** `kinetic_captions` alone is a text slide; prefer scenes where motion carries the weight (orbit, typewriter, pulse) and captions are the footnote.

### Scene Recipe Cards (starting palettes)

| Scene type | Elements (stacking order) | Typical motion |
| :--- | :--- | :--- |
| **Data reveal** | `background` → `scaling_chart` → `grid` → `kinetic_captions` | playhead sweep; odo meter after sentence |
| **Character moment** | `background` → `orb_pulse` → `dot_field` → `typewriter_text` → `kinetic_captions` | pulse breathing + gentle text reveal |
| **Tour / walkthrough** | `background` → `leader_arrow` → `orbit_ring` → `hud_badge` → `kinetic_captions` | arrow walks the path; ring spins |
| **Impact beat** | `background` → `orb_pulse` (big) → `hud_badge` → `kinetic_captions` + `trauma` sfx | pulse + zoom push-in + shake |
| **Network tour** | `system_architecture` → `dot_field` | packets fly; dots drift on the floor |

### Scene visual quality checklist (one per board, read before writing scenes)

- **One hero per scene** — pick exactly one moving hero (`orb_pulse`, `orbit_ring`, `typewriter_text`, `equalizer`, camera `orbit`/`static`, …). A scene with only captions looks like a text slide.
- **No dead frames** — the hero moves on a beat, captions land after motion, pops happen early in a beat.
- **Payload on top** — captions/quotes/diagrams overlay the motion, never compete with it.
- **Copy a recipe card** from the table above (`data reveal`, `character moment`, `tour`, `impact beat`) instead of composing from scratch — same grammar, ship-tested combos.
- **Palette** — canonical archetype palette or an alternate persona overlay from `references/archetypes.md`; pick once per video, not per scene.

### Camera

Modes (`camera.mode`):

- **`zoom`** (default) — `zoom_start → zoom_end` through `easing`; world offsets get zoomed around `pan_x/pan_y`. Zoom clamped `[1.0, 10.0]`.
- **`orbit`** — the center orbits around `pivot_x/pivot_y` (normalized) from `azimuth_start_deg → azimuth_end_deg` by `orbit_radius_start/end` design px; `orbit_easing` (defaults to the camera `easing`); `elevation_deg` for a rising/lowering arc. Use it when the subject has "a place to be around" — the ring becomes the composition's center.
- **`static`** — zoom frozen at `zoom_start`; shake still applies. Good for deep-think/reading scenes.

Screen = `(world − center(t)) · zoom + viewport_center + shake`. `shake_amplitude_px` enables a deterministic trauma shake (quadratic decay) — trigger it with `{"sfx": "trauma"}` events; no other event shakes the camera.

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

### `svg` — `{ "type": "svg", "svg": "<svg viewBox='0 0 200 200'>…</svg>", "box": [x0, y0, x1, y1], "reveal": "draw", "glow": true }`
Vector art, custom icons, diagrams, callouts, and animated line drawings. Accepts either inline `svg` markup or an external `src` path (relative to the storyboard file). Supports `fit` (`contain` default | `cover` | `stretch`), `reveal` (`none` | `fade` | `draw` progressive stroke animation | `pop` spring-pop), `glow` (feeds strokes/shapes into the Gaussian bloom pyramid), `tint` (hex color override), `opacity`, `rotation_deg` / `rotation_end_deg`, `scale_start` / `scale_end`, `stroke_scale`, and `render_mode` (`auto` | `browser` | `raster` | `vector`). For static SVGs (`reveal != "draw"`, no `glow`/`tint`), automatically upgrades to `resvg`/`rsvg-convert` or headless Chromium (`scripts/threejs/svg_raster.mjs`) for full **SVG 2.0** fidelity (linear/radial gradients, `<filter>` drop-shadows/blurs, `<style>`, `<mask>`, `fill-rule="evenodd"`, cached RGBA with pop/fade/rotation/scale); always falls back cleanly to the offline pure-Python stdlib vector engine. Rejects unsafe `DOCTYPE`/`ENTITY` declarations and strips `<script>`.

### `orb_pulse` — `{ "type": "orb_pulse", "cx": 640, "cy": 350, "radius": 90, "color": "#FFD700", "pulse_hz": 1.1, "bob_amp": 8 }`
Pulsing hero orb + soft glow halo; breath (`pulse_hz`) and optional slow vertical bob. Use as the scene's single hero. Compact palettes: gold+cyan, gold+white, teal+white.

### `dot_field` — `{ "type": "dot_field", "n": 28, "radius": 6, "color": "#38BDF8", "speed": 0.95, "jitter": 8, "bob_amp": 0.9 }`
Floating particle swarm on a golden spiral — persistent Life behind other content. Small per-dot blooms; 30–60 px wide field, 50–80% opacity feel.

### `orbit_ring` — `{ "type": "orbit_ring", "cx": 640, "cy": 360, "radius": 150, "n": 9, "size": 7, "spin_hz": 0.45, "color": "#38BDF8", "pulse_hz": 0.9 }`
Dots spinning on a circle — shows rotation/time. Size/spacing controls the reading scale; sparkle with a second element of different color for extra life.

### `equalizer` — `{ "type": "equalizer", "n": 12, "bar_width": 10, "bar_top": 500, "peak": 230, "color": "#FFD700", "beat_hz": 1.35 }`
Audio-style bars that pulse by a phase — good on music/impact scenes. Give the bars a slightly different hue than the hero orb for multi-color character.

### `typewriter_text` — `{ "type": "typewriter_text", "text": "The frontier…", "size": 30, "x": 640, "y": 450, "speed": 18, "accent": "#38BDF8", "color": "#E5E9F0", "cursor": true }`
Progressive glyph reveal with a blinking block cursor — tells stories through pacing (hook at `speed` 12–22 on socials). Place mid-scene; it ends with the text fully revealed.

### `leader_arrow` — `{ "type": "leader_arrow", "points": [[640, 660], [200, 240], [820, 300]], "speed": 3.0, "radius": 10, "width": 6, "color": "#8BE9FD" }`
Animated leader walking a polyline (arc-speed `speed` px/s, can `wrap`) — walkthrough/tour scenes. Fade it or set `speed` to 0 when the tour ends.

### `kinetic_captions` — `{ "type": "kinetic_captions", "accent": "#FFD700", "size": 22 }`
Reads the scene's `words` array; word-by-word karaoke in the caption band. `accent` (current word) and `size` optional.

## Scene backends (optional — `scene_spec` + `backend`)

A scene with `scene_spec` replaces the `elements[]` requirement and routes to a parametric 3D backend. `backend`: `auto` (default; routes on category/keywords), `blender_hybrid`, `blender_3d`, `threejs_hybrid`, `threejs_3d`, `canvas_2d`, `manim_math` (accepted, lints a warning, renders as canvas_2d). Paint order: 3D pass or pre-baked Blender/Three.js plate → HUD (`blender_hybrid` / `threejs_hybrid` only) → `elements[]` (if any) on top → fades.

```jsonc
{ "scene_id": "cowos_stack", "archetype": "mixed", "duration_sec": 1.5,
  "backend": "threejs_hybrid",            // or auto / blender_hybrid / blender_3d / threejs_3d
  "scene_spec": {
    "category": "exploded_hardware_3d",   // or orbital_or_field_3d, organic_serpent_3d, network_topology_3d
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

Rendering paths:
- **Three.js WebGL Studio (`threejs_hybrid` / `threejs_3d`):** when Node ≥ 22, Chromium/Chrome, and local `scripts/threejs/node_modules/three/` are present (`cd scripts/threejs && npm install`; verify via `python3 scripts/threejs_bridge.py --check`), `scripts/threejs/runner.mjs` bakes PBR WebGL frames + `anchor_tracks.json` offline over native CDP with `RoomEnvironment` IBL reflections, `EffectComposer` + `UnrealBloomPass` HDR bloom (tunable via `params.bloom`, `bloom_strength`, `bloom_radius`, `bloom_threshold`, `exposure`), `params.camera_target`, and Z-up camera parity (including instant single-frame WebGL `--thumbnails` via `--frame-t`). Supports `exploded_hardware_3d`, `orbital_or_field_3d`, `organic_serpent_3d`, `network_topology_3d`, `external_asset_3d` (loads local `.glb`/`.gltf` via `params.asset_path` + `GLTFLoader` OR extrudes 2D `.svg` files / `params.svg_markup` into bevelled 3D PBR metallic meshes via `SVGLoader` + `ExtrudeGeometry`), AND **bespoke per-project Three.js scenes** via `params.threejs_script` (relative `.mjs` exporting `async function buildScene({ THREE, scene, camera, spec, renderer, GLTFLoader, SVGLoader, extrudeSvgTo3D }) => (tNorm) => dynamicAnchors` with full `three` and `three/addons/*` import map!). Any failure falls back cleanly to software 3D.
- **Blender (`blender_hybrid` / `blender_3d`):** with Blender ≥ 3.6 on PATH, each scene is pre-baked into the work dir (`blender -b -P scripts/blender_runner.py -- --spec …`, PNG sequence + `anchor_tracks.json`; failure → warn + software fallback, render continues).
- **Software 3D (canonical fallback + `--thumbnails`):** `scripts/software_3d_projection.py` renders a 4×4-perspective painter's-algorithm pass with stdlib math and returns the same normalized `(u, v, z_depth)` anchor contract.

HUD cards (`blender_hybrid` / `threejs_hybrid`) are placed by `scripts/layout_solver.py` (AABB min-axis separation; locked HUD header + center-stage repulsor; 24 px canvas clamp) and painted by `scripts/hybrid_compositor.py` (reticles, 45° elbow leaders, glass cards, spring-pop reveal). Runtime-computed tracks with `visible: false` are skipped (board `anchors_3d` cannot set `visible`). `camera_3d.mode` supports `orbit` (default), `dolly`, `crane`, and `static`; `lighting_preset` supports `cyber_studio_volumetric` / `clean_product_softbox`; camera defaults are shared across all three 3D renderers. Full examples: `examples/hybrid_3d_storyboard.json` and `examples/threejs_3d_storyboard.json`.

## `sfx_events`

`pop` · `whoosh` · `chime` · `confirm` · `type_click` · `error_buzz` — synthesized offline, mixed at scene offset, ducked pad, −1 dBFS ceiling, loudnorm −14 LUFS on mux.
`trauma` — camera-only; no audio. `intensity` scales SFX or shake (0.1–1.0).

## Genre painters

Two new painter families cover comedy and political news (registered in `RENDERERS` + `KNOWN_ELEMENTS`; deterministic — pure functions of `ElementContext`).

**Horse Tenny genre** (`scripts/elements/ui_mockups.py`, element types):
- `phone_frame` — device silhouette with notch and corner chrome.
- `swipe_card` — stacked dating-app cards; top card pops with a scene-time wobble. `cards: [{accent, label}]`.
- `social_post` — feed card: avatar + name, body lines, heart + comments + share.
- `chat_bubble` — message bubbles with tails; per-bubble `delay` for slide-in entry.
- `app_toast` — bottom pill that slides in after a time delay.

**Political news genre** (`scripts/elements/maps.py`):
- `map` — stylized world-map clusters (Europe/Africa/Asia/Australia/Americas), regions override via `regions: [{x,y,w,h,color,label}]` (normalized within box).
- `map_callout` — labeled hot-spot bubble with arrow tail.
- `map_arrow` — animated route leader (reuses `leader_arrow`).

Reference boards: `examples/ref_horse_tinder.json` (swipe_card, phone_frame, typewriter_text), `examples/ref_geopolitics_explainer.json` (map, map_callout, map_arrow, source_tag), `examples/ref_true_story_noir.json`, `examples/ref_tech_explainer.json` — all at 100/100 on `style_lint`.

## Monetization & retention gates

Three built-in, mostly-advisory tools. For ads revenue the losers are: **0% CTR thumbnails**, **synthetic-looking physics-driven stock fills**, and **non-commercial stock in paid videos** — guards against all three.

- `scripts/monetization_gate.py` — `monetization_gate.py --board storyboard.json --manifest assets/manifest.json --script script.json`. Runs: commercial-license firewall (`LICENSE_ALLOWLIST` = cc0/pdm/by/by-sa/ai-generated; hard-blocks by-nc*, by-nd*, pd, missing/unknown — assets with allowlisted licenses still need `attribution`), asset file existence, adversarial narration scan (fabricated quotes, defamation, election/medical misinformation → ERROR), `retention_static_hold` (ERROR when >3.0 s @9:16 / >6.0 s @16:9 without motion/SFX — add a camera move, typewriter, pulse, or SFX). ERRORs fail the export when wired into `verify_output.py` (`--manifest`/`--script`); run manually to audit beforehand.
- `scripts/thumbnail_gen.py` — `thumbnail_gen.py --storyboard storyboard.json --out publish/thumbnail.jpg`. Renders scene thumbnails, scores by contrast (≥4.5:1 proxy) and 168×94 legibility (non-white fraction ≥ 0.45), writes the best JPEG < 2 MB. Human-review the pick (subject/face fill, 2-4 word hook) — it's a heuristic.
- `scripts/tool_probe.py` — `tool_probe.py --out capabilities.json` (host: GPU, Blender, Three.js/Chromium, local STT/TTS modules, API keys by *presence* only). The "use all available tools" decision input: hosts can auto-select render/voice tiers from what's actually there.

## Validation & failure modes

`scripts/storyboard.py board.json` prints one line per violation with the owning scene — fix and re-run; `render_engine.py` refuses to start on any violation. Most common: `sfx_events[].t_sec` beyond `duration_sec` (trim the event or extend the beat), and `zoom_*` outside `[1.0, 10.0]`.

## Art direction and platform practice

Boards may carry two optional top-level blocks: `style` (art direction) and `platform` (creator practice). Both are validated by `scripts/storyboard.py` and resolved by `scripts/style.py` / `scripts/platform_presets.py`; the same blocks existed in the validators since v1.5.0 and are now described by `schemas/storyboard.schema.json` + the new `schemas/style.schema.json`.

### Style bible (`style` block) + presets

`scripts/style.py`: `{"style": {"preset": "soft_clay", "palette": {"accent": "#A65A38"}}}` — preset file from `assets/styles/<name>.json`; inline keys override the preset (palette merges per-role, other sections per-key). Six presets ship: `soft_clay`, `punchy_pop`, `newsroom_clean`, `noir_restraint`, `risograph`, `tech_blueprint` — e.g. `soft_clay` = clay material, Kamo palette, calm drift. Everywhere a colour string appears in the board, `"@role"` (e.g. `"@accent"`) is replaced by the resolved palette hex (`apply_style` — deterministic, so painters, SVG, quote cards and the 3D bridge all see plain hex; 3D scenes also get `style_light` in their `scene_spec`).

### Platform layer (`platform` block)

`scripts/platform_presets.py` presets: `shorts_tiktok_reels` (9:16, sticker captions, hook 3s, beat 3s, loop), `youtube_long` (16:9, editorial captions, hook/beat 8s), `square` (1:1). `apply_platform` fills `kinetic_captions` defaults — sticker (big, heavy-stroked, no pill, word pop) or editorial (serif, soft translucent card, fade) — on top of the caption zone (`canvas.layout_zones["captions"]`), so burns sit in the safe-zone band, not on platform chrome.

### Motion feels + composition

`style.motion.feel` = `punchy` | `calm`: punchy = faster zooms, heavier easing, spring pops; calm = slow drift, exponential ease-out. Composition: `scripts/composition.py` (thirds + negative-space anchors); `style_lint.py` flags repeated centred heroes.

### Grade

`style.grade` (grain / vignette / halation / warmth) → `scripts/grade.py` post-pass per board (deterministic, seeded grain tiles, half-res cache).

### Lint + review tools

`style_lint.py` (advisory, report mode by default; `--strict` exits 1): `off_palette` (>3 saturated hues away from the style palette), `hue_sprawl`, `glow_overuse`, `centered_hero` (3+ dead-centre scenes), `default_font` (no `style.type`/`font_family`), `flat_motion`, `single_easing`, `no_hook` (platform preset: no text/captions/words on frame 0), `long_hold`, `aspect_mismatch`, `unsourced_claim` (`newsroom_clean`: quote/scaling_chart without `source_tag`/attribution; image without `attribution`). Score out of 100. `contact_sheet.py` builds one labelled tile per scene (`thumbs/` from `render_engine.py --storyboard … --thumbnails DIR`) for fast human review. `publish_kit.py board.json -o publish_kit.md --manifest assets/manifest.json --thumbnails DIR` drafts the long-form output (title/description, chapters, credits from the manifest, AI-disclosure lines, thumbnail pick by luminance contrast).

### Topic → preset → board table

| Topic | Style preset | Platform preset | Reference board |
| :--- | :--- | :--- | :--- |
| Comedy / lifestyle / memes | `punchy_pop` | `shorts_tiktok_reels` | `examples/ref_horse_tinder.json` |
| True story / documentary | `noir_restraint` | `shorts_tiktok_reels` | `examples/ref_true_story_noir.json` |
| Essay / wellness / poetry | `soft_clay` | `youtube_long` | `examples/ref_soft_clay_poem.json` |
| Tech / code / science | `tech_blueprint` | `shorts_tiktok_reels` | `examples/ref_tech_explainer.json` |
| Politics / explainers | `newsroom_clean` | `youtube_long` | `examples/ref_geopolitics_explainer.json` |

Policy links (current wordings — verify before publishing): the publish_kit.md embeds them (`https://support.google.com/youtube/…`, TikTok AI-content labels).

**Scope note:** political and sensitive subjects must be neutral, sourced explainers; the pipeline will not generate persuasive or deceptive political content (fake quotes, fabricated footage). Boards are hand-auditable — `style_lint.py` scores them, you judge the look with contact sheets.
