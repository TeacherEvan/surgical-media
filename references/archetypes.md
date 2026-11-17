# Archetype Field Guide

Pick per scene (`archetype`). Blend across scenes freely; the renderer doesn't care. Palettes are canonical — deviate only with a reason.

| | `geometry_rig` | `doc_essay` | `code_report` |
| :--- | :--- | :--- | :--- |
| **Exemplar feel** | Alan Becker — *Animation vs. Geometry* (https://www.youtube.com/watch?v=VEJWE6cpqw0) | Matt Madigan — *AI Is Bigger Than Aliens* (https://www.youtube.com/watch?v=zQmcipkVdW0) | Fireship — *Why Microsoft couldn't fix its own servers* (https://www.youtube.com/watch?v=ytmawkPTP24) |
| **Canvas** | `#050508` (pure void) | `#0A0E17` slate + `#131B2E` grid | `#0D1117` IDE dark |
| **Accent palette** | `#FFFFFF` geometry, `#FF6B00` rig, `#FFD700` gold lock | `#38BDF8` telemetry, `#FFD700` milestones | `#50FA7B` ok, `#FF5555` fail, `#BD93F9`, `#8BE9FD` |
| **Hero elements** | `phi_divider`, `tesseract`, `stick_rig` | `scaling_chart`, `quote_card`, `grid` | `system_architecture`, `code_terminal` |
| **VO rate** | non-verbal — SFX-locked beats | 150–165 WPM | 175–195 WPM |
| **Beat density** | 1 visual state / 2–3 s | 1 visual state / 2.5–3 s | 1 visual state / 1.5–3 s |
| **Signature SFX** | `chime` (φ-interval), `whoosh`, `pop` on lock | `pop` milestones, `confirm` on thesis land | `type_click`, `error_buzz`, camera `trauma` |
| **Camera** | slow ease_out_expo zoom (1.0 → 1.15) | static or micro ease_in_out_cubic drift (≤1.05) | micro push-in + `trauma` shake on the headline failure |

## `geometry_rig` — procedural math & the IK stick figure

The figure is drawn by `rig.py`: a 2-bone analytical IK limb solves shoulder→elbow→hand via the law of cosines to any world-space target, with idle bob and torso lean from scene-local time. Pair with:

- **`phi_divider`** — recursive golden-cut rectangle construction with quarter-circle arcs (Fibonacci-spiral geometry) and a `φ = 1.618034` readout. Between `t=0.42–0.78` the lock brightens; at full lock a `LOCK` glyph blooms. Trigger `chime` on lock.
- **`tesseract`** — 16-vertex 4D hypercube rotated in the XW, YZ and XY Clifford planes, stereographically projected R4→R3 (`s₄ = 1/(2.1 − w)`) then perspective-projected R3→R2. Near edges bloom gold. Pure ornament — the math is real, the physics is theater.
- **Pathing:** put the `stick_rig`'s `reach_to` on the divider's split line so the figure "completes" the golden ratio every scene.

## `doc_essay` — documentary data essay

- **`scaling_chart`** — exponential `y(u) = (e^{ku} − 1)/(e^k − 1)` with glowing playhead, three spring-pop milestone badges and a quadratic odometer (`odometer_from → odometer_to`, e.g. 1× → 500×). `exponent` 3.5–4.5 reads as "compute" instantly.
- **`quote_card`** — translucent slate card (`#111C31` over `#050508` bases), specular border `#2B3A55`, gold glyph. Quotes ≤ 4 wrapped lines or they overflow; the painter clips at 4.
- **Grid stays faint:** `#131B2E` at spacing ≥ 64 px. If the grid competes with the curve, the exponent visualizes nothing.
- **Pacing:** one idea per clause, 8–15 words. Odometer lands *after* the sentence completes — data punctuation, not decoration.

## `code_report` — rapid-fire incident anatomy

- **`system_architecture`** — cubic-bezier edges with two packet dots in flight per route; `cascade_start` + `cascade_step` flip nodes 200 OK → 503 in declaration order; packets redden right before the node dies. Pair the final cascade step with a `trauma` camera event (`shake_amplitude_px` on the camera).
- **`code_terminal`** — macOS traffic lights, gutter line numbers, diff-row tints (`add`/`del`), progressive reveal tied to `ctx.t`, blinking block cursor. Lines reveal in order; the last revealed line gets the cursor.
- Keep the failure chain *legible*: ≤ 4 nodes, one source (`role: "source"`), one failure per node. More than that and you're making a topology diagram, not a story.

## Blending

Reserve `mixed` for legally-needed transitions (2–4 frames of hard cut is fine between archetypes — no crossfades except through motion). A strong default grammar: open on `code_report` tension, resolve on `doc_essay` scale, close on `geometry_rig` inevitability. Never run two archetype hero elements in the same scene.

## Caption Discipline

`kinetic_captions` reads the scene's `words` array (syllable-weighted timestamps from `tts_align.py`). Past words are `#E5E9F0`, the active word pops gold at 1.18×, future words sit at `#39424F`. On 9:16 the strip auto-centers inside the caption safe band; on 16:9 it sits under the stage. Long clauses wrap to the measured width automatically.
