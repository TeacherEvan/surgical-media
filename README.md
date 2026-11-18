# Surgical Media (`v1.0.0`)

**Deterministic, QC-gated pipeline for turning a topic prompt into a social-ready MP4 — research brief, audio-first timing, storyboard, 2x-supersampled Pillow rendering, ffmpeg H.264/AAC master, ffprobe verification.**

## Quick Start

```bash
# system deps: python>=3.10, ffmpeg + ffprobe on PATH
python3 -m pip install -r requirements.txt          # Pillow ≥ 10
python3 -m pip install -r requirements-tts.txt      # optional: edge-tts voice synthesis

python3 scripts/build_demo.py                       # (re)generate the example board
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs   # seconds — see each scene first
python3 scripts/render_engine.py --demo --output demo_showcase.mp4    # ~70s on 4 cores
```

`demo_showcase.mp4` is a 14.4 s / 1280x720 / 30 fps three-scene showcase (`geometry_rig` → `doc_essay` → `code_report`). The render ends with an ffprobe QC pass; a failed gate exits 3.

Voice an actual script offline or online:

```bash
python3 scripts/tts_align.py --input script.json --output storyboard.json --aspect 9:16
python3 scripts/storyboard.py storyboard.json
python3 scripts/render_engine.py --storyboard storyboard.json --output final.mp4 --quality final
```

## Repository Layout

| Component | Purpose |
| :--- | :--- |
| [`SKILL.md`](SKILL.md) | Agent entrypoint: stages, invariants, quick start, gotchas |
| [`scripts/tts_align.py`](scripts/tts_align.py) | Beat script → timing-locked storyboard (edge-tts + ffprobe, or offline WPM estimate; syllable-weighted word allocation) |
| [`scripts/storyboard.py`](scripts/storyboard.py) | Stdlib storyboard validator & timeline helpers |
| [`scripts/render_engine.py`](scripts/render_engine.py) | Storyboard → MP4. Supersampled frames stream raw into ffmpeg; QC runs inline |
| [`scripts/elements.py`](scripts/elements.py) | Scene painters (charts, diagrams, terminals, cards, captions, stick rig, raster image element) |
| [`scripts/canvas.py`](scripts/canvas.py) | `SupersampledCanvas` (2x SSAA, BOX integer downsample), half-res dual-radius Gaussian bloom, safe zones, HUD/stage/caption partition |
| [`scripts/camera.py`](scripts/camera.py) | `WorldCamera2D` — pre-raster zoom/pan with easing + deterministic trauma shake |
| [`scripts/rig.py`](scripts/rig.py) | Analytical two-bone IK, hollow-head stick-figure renderer |
| [`scripts/audio_dsp.py`](scripts/audio_dsp.py) | Stdlib SFX synth (chime/pop/whoosh/click/buzz), just-intonation pad, sidechain ducking, −1 dBFS ceiling, stereo WAV I/O |
| [`scripts/easings.py`](scripts/easings.py) | `ease_out_expo` / `ease_in_out_cubic` / `spring_pop` / … |
| [`scripts/verify_output.py`](scripts/verify_output.py) | ffprobe assertions (streams, H.264, yuv420p, fps, ≤150 ms A/V drift) |
| [`scripts/fetch_assets.py`](scripts/fetch_assets.py) | Stage 1 subject imagery: Openverse CC-allowlist fetch, PIL-verified, writes `assets/manifest.json` with attribution strings |
| [`scripts/build_demo.py`](scripts/build_demo.py) | Regenerates `examples/tri_archetype_storyboard.json` |
| [`schemas/`](schemas/) | Draft 2020-12 contracts for the investigation brief, beat script, and storyboard |
| [`references/`](references/) | Archetype field guide, storyboard element catalog, ffmpeg/loudness reference |
| [`tests/`](tests/) | `pytest` suite — unit + rendered-MP4 integration (requires ffmpeg) |
| [`docs/adr/`](docs/adr/) | Architecture decision records |

## Verification Gates

```bash
python3 -m pytest tests/ -q       # all green, ffmpeg integration included
ruff check --no-cache scripts/ tests/
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json
check-jsonschema --check-metaschema schemas/*.schema.json
```

Or everything, in one call: `bash scripts/ci_gates.sh`

### CI parity

- GitHub Actions ([`.github/workflows/skill-ci.yml`](.github/workflows/skill-ci.yml)) and GitLab CI ([`.gitlab-ci.yml`](.gitlab-ci.yml)) both run **the same** `scripts/ci_gates.sh` — they cannot drift apart.
- **Status (2026-11-18):** GitHub Actions is blocked — the account is billing-locked, jobs are rejected before they start. The repo is public and honest local gates pass, but remote verification is pending.
- The GitLab mirror starts automatically once a project is imported from this repo: **New project → Import project → Repository by URL** → paste this repo's URL → create. Optionally enable *Settings → Repository → Mirroring* to auto-sync `main`. Until the first pipeline passes, treat the mirror as configured-not-verified.

## Install as a Skill

```bash
./install_surgical_media.sh [target_dir]   # default: ~/.hermes/skills/creative/surgical-media
```

## Design Notes

- **Audio-first or it doesn't render.** Frame counts come from measured VO durations (ffprobe), never estimates baked into a timeline.
- **Nothing ships unverified.** If `tests/` doesn't prove it, the skill doesn't claim it.
- **No numpy dependency.** Audio and geometry are stdlib-only; Pillow is the single rendering dependency. See `docs/adr/0001-stdlib-first-verified-pipeline.md`.
