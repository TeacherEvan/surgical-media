# Style → execution matrix & locked timeline contract

This is the bridge from the seven requested styles to concrete renderer settings. It is the
"style-and-architecture" layer of the priority pipeline: every row maps to code that already
ships in this repository (`scripts/style.py`, `assets/styles/`, `scripts/platform_presets.py`,
`scripts/elements/`, `scripts/grade.py`).

## 1. Style → execution matrix

| Style | Archetype / preset | Cut cadence | Captions | Camera / motion | Grade | Intro → Outro |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Comedic** | `geometry_rig` + `ui_mockups`; `punchy_pop` | 0.8–1.5 s, pattern-interrupt every 3rd beat | sticker, 2-line max, punch word highlighted | `spring_pop`, `trauma` shake on the gag | warm, high sat, light grain | freeze-frame hook → callback punchline |
| **Serious** | `doc_essay` + `maps`; `newsroom_clean` | 2.5–4 s | editorial, source tag lower-third | slow dolly (`ease_in_out_cubic`), no shake | desaturated slate, crisp | cold-open stat → decisive summary + CTA |
| **Formal** | `doc_essay`; `newsroom_clean` | 3–5 s | editorial, no sticker | near-static drift; `linear` forbidden | neutral, vignette 0.1 | titled cold-open → compact source credit roll |
| **Catchy** | `code_report`; `tech_blueprint` | 0.6–1.2 s | sticker + kinetic word pops | `ease_out_expo` whip pans | neon accents, halation | kinetic topic stamp → seamless loop to Frame 1 |
| **Poetic** | `doc_essay` + `orb_pulse`/`orbit_ring`; `soft_clay` | 3–6 s, held beats intentional | sparse editorial, ≤6 words | slow `ease_in_out_sine` drift | soft warm, grain 0.2 | evocative image + one line → lingering frame, slow fade |
| **Artistic** | `mixed` + `svg` reveal draw + `scene_spec`; `risograph` | 1.8–3 s | stylized display type | orbit/rotation, SAT-pinned HUD | duotone, high halation | vector line-drawing reveal → motif resolves |
| **All of the above** | per-scene archetype switch; one dominant preset | arc: 0–3 s catchy → comedic → serious/formal evidence → catchy data → poetic/artistic payoff | sticker hook → editorial body → sparse close | escalate then settle | single `style` block + per-scene `grade` overrides | fused hook (short) or 3–10 s cold-open (long) → style-matched payoff |

Implementation notes:

- `archetype` is validated against `geometry_rig | doc_essay | code_report | mixed`.
- `style.preset` is one of `soft_clay | punchy_pop | newsroom_clean | noir_restraint |
  risograph | tech_blueprint` (files in `assets/styles/`). Comedy → `punchy_pop`,
  documentary → `noir_restraint`, essay → `soft_clay`, tech → `tech_blueprint`,
  politics/news → `newsroom_clean`.
- `platform.preset` is `shorts_tiktok_reels | youtube_long | square`; a 4:5 Facebook Feed
  master uses `square` budgets with `format.width/height = 1440x1800`.
- Never use `linear` motion (Hard Invariant 3). Pick the ease named in the table, or any
  easing from `scripts/easings.py` except `linear`.
- `scripts/style_lint.py` scores boards 0–100; target ≥90 before render.

## 2. The locked timeline — one source of truth

**`storyboard.json` is the timeline.** Do not introduce a second hand-edited `timeline.json`.
An external adapter may *derive* one from `storyboard.json`, but retiming is never allowed.

Fields that lock every engine to the same frame grid:

| Field | Owner | Why it is load-bearing |
| :--- | :--- | :--- |
| `meta.seed` + `format.width/height/fps` | storyboard | deterministic pixels, CFR, bt709 |
| `scenes[].start_sec` / `duration_sec` | `tts_align.py` | audio-first frame counts; never guessed |
| `scenes[].words[]` | `tts_align.py` | measured WordBoundary or syllable-weighted beats |
| `scenes[].sfx_events[]` | storyboard | frame-accurate sound, scene-relative `t_sec` |
| `scenes[].vo_wav` | `tts_align.py` | the VO stem each span is cut against |
| `audio` | storyboard | pad / duck depth / sample rate |
| `style`, `platform` | storyboard | palette/type/grade, safe zone, hook and beat budgets |

Build order is fixed: research brief → script.json → `tts_normalizer.py` → `tts_align.py`
→ storyboard.json → `storyboard.py` validation → renders → `qc_gate.py`. All engines read the
same board; Three.js/Blender/Pillow passes must agree on FPS and color space or they will
drift on merge.

## 3. Originality gate (run before scripting — 5 points)

YouTube's post-2026-10 Shorts enforcement throttles repurposed clips with thin narration.
All five must be true:

1. The hook states an original angle or question in the first 3 seconds.
2. The script contains the creator's own synthesis, comparison, or commentary.
3. Sources are attributed primary/secondary material — not reposted viral clips.
4. The visual structure is custom (SVG line art, parametric 3D, novel composition), not a
   recycled template.
5. Captions and transitions are authored for this video, not bulk-reused across uploads.

Record a one-line pass note in `CREDITS.md`.

## 4. Engine selection

| Scene need | First choice | Fallback |
| :--- | :--- | :--- |
| Kinetic typography, data cards, callouts | Pillow + `elements/` (or external Revideo/Motion Canvas, MIT) | `code_report` archetype |
| Mathematical / statistical animation | external Manim CE | `scene_spec` backend `manim_math` (warns → renders 2D) |
| Photoreal 3D hero, lighting, physics | `blender_runner.py` (bpy headless) | `software_3d_projection.py` |
| WebGL shaders, PBR, kinetic camera | `threejs_bridge.py` + `scripts/threejs/` | stdlib 4×4 projection |
| Real-person photos, credits, thumbnails | `media_harvester.py` + `image` element + `thumbnail_gen.py` | `fetch_assets.py` + manual board edit |
| Final composite, mastering, QC | `render_engine.py` + `verify_output.py` + `qc_gate.py` | — |

Remotion is deliberately not bundled: its license changes with team size and batch use
(see `specs-licensing-compliance.md`). Revideo/Motion Canvas are the permissive equivalent
when a React/TS motion stack is genuinely needed.

## 5. Handoff contract

Every completed production hands off: `final.mp4`, `CREDITS.md`, `credits.json`,
`qc_report.json`, the red-overlay audit PNGs, and the disclosure flags required by the
platform. `publish_kit.py` can generate the description, chapters, and AI-disclosure text
from these artifacts.
