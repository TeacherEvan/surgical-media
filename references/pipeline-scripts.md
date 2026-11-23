# Pipeline scripts — CLI index

Full, runnable code lives in `scripts/` (this repository is a local skill, not Gemini Chat,
so raw `.py` files are fine). This page is the quick reference for the three "studio pro"
utilities merged into the priority pipeline. All are stdlib-only; OpenCV/NumPy are optional
accelerators, never required.

## -1. `scripts/spec_refresh.py` — executable spec refresh (Step 2)

```bash
python3 scripts/spec_refresh.py --check [--fetch] --out spec_report.json
```

- `--check` compares the dated baseline in `references/specs-licensing-compliance.md` against
  16 embedded facts (platform caps, both safe rectangles, audio targets, policy dates, license
  matrix). Exit 3 = drift; fix the doc and re-date it before rendering.
- `--fetch` adds advisory HTTPS marker probes to YouTube Help and Remotion pricing. Network
  failure is recorded (`offline: true`) but never fatal.

## 0. `scripts/pipeline_preflight.py` — executable intake + structure gate

```bash
python3 scripts/pipeline_preflight.py --time 60 --style comedic --platform tiktok \
    --intake-out intake.json
python3 scripts/pipeline_preflight.py --board storyboard.json --intake intake.json \
    --brief investigation.json --json preflight.json
```

- Intake mode resolves Time/Style/Platform into a locked contract: format, style preset,
  archetype, cut cadence, intro window (0.5–3 s short-form / 3–10 s long-form), outro
  contract (CTA + credits + loop), platform duration cap, and the 7-style tonal arc.
- Board mode fails (exit 3) on schema errors, format/style/platform mismatch, missing
  topic-matched intro, outro without CTA or credits, over-cap duration, or fewer than 3
  sourced claim-ID facts in the research brief. This makes Steps 1, 6 and the originality
  gate executable rather than advisory.

## 0.5. `scripts/style_apply.py` — generation-side style matrix

```bash
python3 scripts/style_apply.py --intake intake.json --board storyboard.json \
    --out storyboard.styled.json --report style_changes.json
```

Writes the 7-style contract into a timed board: style/platform presets, caption style and
hook/beat budgets, per-scene archetypes (hybrid tonal-arc rotation for "all of the above"),
the retention-safe intro window with word/SFX timestamps rescaled, and outro scaffolding
(`source_tag` + explicit `[CTA: …]` placeholder). It never invents factual claims, is
idempotent, and reports every change for review. Follow with `pipeline_preflight.py`.

## 1. `scripts/tts_normalizer.py` — spoken-text normalization

Local TTS models misread raw dates, years, currencies, acronyms and hashtags (Kokoro scores
poorly on numeric dates). Normalize **before** voicing.

```bash
python3 scripts/tts_normalizer.py --input script.json --output script.spoken.json \
    --report normalization.json
python3 scripts/tts_normalizer.py --text 'Meta raised $3.2B on 2026-11-21 #AI' --emit-text
```

- Rewrites `narration` (and `text`) fields in beat/script JSON; preserves every other key.
- Converts: ISO/US dates → spoken month + day + year; `$3.2B` → "three point two billion
  dollars"; `2026` → "twenty twenty six"; `#AI` → "hash A I"; `%` → "percent".
- `--report` writes a field-by-field change log so the script can be reviewed, not trusted
  blindly. Always skim the report for proper nouns before rendering.

## 1.5. `scripts/fetch_assets.py` + `scripts/asset_wire.py` — image-first board assembly

Downloading is not enough: a manifest left on disk produces exactly the "3D slop +
captions" failure this wave fixes. Always wire it into the board.

```bash
# One query per beat — explicit visual.query wins, otherwise derived from narration
python3 scripts/fetch_scene_assets.py --input script.spoken.json --out-dir assets \
    --subject "emperor penguin" --count 3     # --dry-run prints the query plan
python3 scripts/tts_align.py --input script.spoken.json --output storyboard.json \
    --aspect 9:16 --subject "emperor penguin" --assets-manifest assets/manifest.json \
    --brief investigation.json
# standalone boards:
python3 scripts/asset_wire.py --board storyboard.json --manifest assets/manifest.json \
    --out storyboard.wired.json --report wire_report.json
```

- `fetch_scene_assets.py` derives a distinct query for each scene and calls `fetch_assets.py`
  per query into a single shared manifest; duplicate queries collapse. This is what stops
  a whole video reusing the same three plates. A beat that returns nothing retries once with
  the broad board subject so it gets a different relevant plate, not the hero image again.
- Openverse free-text results must share a content token with their query — otherwise a
  "freezing emperor penguin ocean" query can yield an unrelated parade photo. Commons and
  iNaturalist are taxonomy-grounded and trusted despite Latin-binomial titles.
- `fetch_assets.py` searches Openverse + Commons + iNaturalist (allowlist `by|by-sa|cc0|pdm`),
  verifies decodability with Pillow, merges manifests, emits per-image `attribution`, and
  stamps each plate with its originating `query` (Commons titles are often Latin binomials —
  that provenance is the keyword bridge for `asset_wire` scoring).
- `asset_wire.py` scores each plate against the scene's narration + `visual.query` + board
  subject; best unused plate wins, then round-robin reuse. Filler elements marked
  `placeholder: true` are stripped (background stays as a load-failure fallback).
- 9:16 plates default to `fit: backdrop_blur` (whole landscape photo, blurred bleed behind),
  landscape/square to `cover`; `kb_zoom: 1.08`, `fade_in_sec: 0.6`, credit at `attribution_y≈1060`
  (above `y_anchor≈0.6` captions) clamped inside the safe x-box with ellipsis for long strings.
- Explicit `visual.image` pins a plate; `visual.kind: svg|3d|procedural` opts out of auto-
  imagery. Scenes with authored imagery (photo/SVG/map/mockup/3D `scene_spec`) are never overwritten.
- `--brief investigation.json` lets `visual_anchors[].primitive` steer per-scene plate choice
  and adds `visual_assets` to the plate pool (manifest wins on duplicate filenames).
- `pipeline_preflight.py:subject_imagery` requires imagery in ≥60% of scenes, rejects
  filler-only beats, and fails when brief `visual_assets` are fetched but never shown.
  `style_lint.py --manifest` adds `low_visual_coverage` alongside the other anti-slop rules.

## 2. `scripts/media_harvester.py` — authentic portraits + subtle credits

```bash
python3 scripts/media_harvester.py --query "Ada Lovelace" --people "Ada Lovelace" \
    --out-dir assets --aspect 9:16 --count 3 --safe-mode organic \
    --focus 0.5,0.35 --source all
```

- Queries Wikimedia Commons / Wikipedia REST for **real-person** photographs, ≥1080 px short
  edge when available; allowlist `by | by-sa | cc0 | pdm` (no `by-nc*`, `by-nd*`).
- Face-centered crop: OpenCV Haar detection when `cv2` is importable, otherwise a pure-Pillow
  YCbCr skin-tone centroid, then an explicit `--focus x,y` anchor (0.5/0.35). `credits.json`
  records which anchor was used; no hard NumPy/OpenCV dependency.
- Burns a discreet credit badge (`Photo: Author / Source`, 70% white, dark stroke) strictly
  inside the chosen safe box, and writes `assets/manifest.json`, `credits.json`, and
  `CREDITS.md` with URLs, licenses, timestamps and AI-disclosure notes.
- Reuse the output directly in `image` elements via `attribution` + `attribution_y`.

## 3. `scripts/qc_gate.py` — hard pre-delivery gate

```bash
python3 scripts/qc_gate.py --video final.mp4 --format 9:16 --preset strict \
    --frames-dir qc_frames --credits CREDITS.md --json qc_report.json
```

- ffprobe: exact resolution/aspect, CFR fps, `h264` + `yuv420p` + bt709, AAC 48 kHz,
  duration and file size against platform caps.
- ebur128: integrated −14.0 ±1.0 LUFS, true peak ≤ −1.0 dBTP.
- silencedetect: flags unintentional dead air > 0.6 s.
- Draws **two** translucent red UI masks (organic + strict) onto Frame 1, midpoint and
  outro PNGs in `--frames-dir` for manual inspection; checks that `CREDITS.md` exists and
  lists every harvested asset.
- `--expect-width/--expect-height` override the format's canonical dimensions for smaller
  smoke renders (CI uses 1280x720 for the 16:9 demo). Default dimensions stay strict.
- Exit 0 = pass, 3 = fail. Failure means fix the board/audio, never weaken the gate.

## 4. `scripts/tool_probe.py` & `scripts/job_cli.py` — host probe & brief-gated jobs

```bash
python3 scripts/tool_probe.py --out capabilities.json
python3 scripts/job_cli.py validate-brief brief.json
python3 scripts/job_cli.py plan <job_id> --brief brief.json
```

- `tool_probe.py` emits presence-only host capabilities (Blender, Three.js, GPU, local/cloud TTS, research keys) without leaking secret values.
- `job_cli.py validate-brief` / `plan --brief` validates `investigation_brief.json` against `schemas/investigation_brief.schema.json` and attaches its SHA-256 + `claim_ids` to `agent_request.json`.
