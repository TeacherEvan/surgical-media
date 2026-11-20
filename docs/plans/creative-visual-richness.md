# Enhancement: Creative Visual Richness — why videos look flat, and how to lift the ceiling

**Status:** drafted · **Proposed for:** v1.5.0
**Problem:** videos rendered by agents through the current skill are bland — dark void, gold/cyan defaults, canned canvases. The user suspects guard rails (the fixed element catalog + canonical palettes) hold back creativity. This review confirms it; the plan below raises the ceiling without touching any QC invariant.

## Review findings (code-level, why output is bland)

1. **The element catalog *is* the only creative menu.** `KNOWN_ELEMENTS` (`scripts/storyboard.py`) = 13 types: background/grid/hud_badge/scaling_chart/phi_divider/tesseract/system_architecture/code_terminal/quote_card/kinetic_captions/stick_rig/image/svg. Any new visual idea = "write a painter + register in RENDERERS + KNOWN_ELEMENTS + tests" — a real cost, so agents fall back to the canned set, hence the "same video" symptom.
2. **Archetypes = 3 + mixed, palettes canonical.** `references/archetypes.md`: "Palettes are canonical — deviate only with a reason." Every video shares the same dark void + gold + teal identity.
3. **Camera = zoom/pan/shake only.** No orbit, no static, no lens; spatial scenes can't "turn".
4. **Motion is conservative.** Pop = scale 0.6→1.0 on text; tesseract 2 planes spin; scaling chart eases up. Most of a 2–3 s beat is a static frame — matches the "dead frames" symptom.
5. **No "personality" painters.** No particles, waves/equalizers, heartbeats, trails, typewriters, animated leader lines.
6. **Beat rule "≤3.0 s — split longer clauses"** pushes agents toward static slides rather than stacked motion+sound+caption layers.
7. Even `svg` (the strongest creative tool) isn't promoted as the main primitive — and agents don't know the palette library.

## Plan (v1.5.0)

### 1. New built-in painters — `scripts/elements/visual.py` (new module), 6 painters

| Painter | Look / motion | Params (samples) |
| :--- | :--- | :--- |
| `orb_pulse` | Hero heartbeat: pulsing gold orb + soft halo, slow bob | `cx/cy/radius/color/alpha/pulse_hz/glow_radius` |
| `dot_field` | Floating particle swarm on golden spiral, bloom glows, drift | `n/radius/color/speed/jitter/glow_alpha` |
| `orbit_ring` | Dot ring spinning around a center at constant angular speed | `radius/n/spin_hz/size/color` |
| `equalizer` | Audio-style pulse bars (equalizer on music scenes) | `n/peak/bar_width/bar_gap/color/beat_hz` |
| `typewriter_text` | Progressive glyph reveal + blinking block cursor | `text/size/family/color/accent/speed/start/hold` |
| `leader_arrow` | Animated leader to a point/box (walkthrough scenes) | `points/speed/radius/color/wrap` |

Register in `RENDERERS` + `KNOWN_ELEMENTS`. All deterministic (no RNG — use `ctx.t`, `ctx.seed`, `ctx.local_time`).

### 2. Camera expansion — `camera.py`, `render_engine.build_camera`, schema

`camera.mode`: `"zoom"` (default), `"orbit"`, `"static"`.

- **orbit**: `pivot_x/pivot_y` (normalized [0,1] of canvas), `orbit_radius_start/end` (design px), `azimuth_start_deg/end_deg`, `elevation_deg`, `orbit_easing`. Center = pivot + radius(t)·(cos az(t), sin az(t)).
- **static**: zoom frozen (Zoom = zoom_start), keeps shake.
- Schema: `mode` enum + orbit params on the camera object; validator (`storyboard.py` camera checks — verify against current code) must accept/reject accordingly.

### 3. Docs — the real guard-rail reduction

- **`references/storyboard-guide.md`**: new **"Visual Grammar"** section (hero motion; layers = caption + motion + sound; no dead frames; beat recipe); **"Recipe Cards"** (4–6 concrete scene templates with painter stacks); new painter catalog entries; orbit camera doc.
- **`references/archetypes.md`**: add **"Creative Personas"** — per-archetype palette alternates + one personality overlay idea per archetype; relax "palettes are canonical" to "the three palettes are the default set — pick or compose".
- **`SKILL.md`**: visual quality checklist + new painters in the catalog; **bump version to 1.5.0**.
- **`README.md` + `pyproject.toml` + `install_surgical_media.sh` + `CHANGELOG.md` + `docs/project-plan.md`**: version sync + status row (verification contract).

### 4. Tests

- Extend `tests/test_elements.py::PAINTER_ELEMENTS` + `test_painter_actually_paints_pixels` list with new painters (no-crash + paint over timeline).
- New `tests/test_visual_creativity.py`: dot_field moves over time, typewriter reveals glyphs, leader_arrow advances, equalizer changes, orb_pulse radius oscillates, orbit_ring rotates (pixel-diff assertions).
- `tests/test_camera.py`: orbit advances and wraps; static ≈ zoom.

### 5. Gates (all green before merge)

`ruff check --no-cache scripts/ tests/`, `ruff format --check --no-cache scripts/ tests/`, `python3 -m mypy scripts/` (strict), `python3 -m pytest tests/ -q` (count grows: 329 → ~335+), `check-jsonschema --check-metaschema schemas/*.schema.json`, example boards still validate, thumbnails smoke + draft render QC ok:true.

## Non-goals

- No AI image generation (invariant: open-licensed imagery only).
- No changes to `geometry_rig`/`doc_essay`/`code_report` fundamentals; `mixed` stays.
- No per-scene micro-positioning API beyond existing painter params.
