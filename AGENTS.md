# AGENTS.md

Agent instructions for working inside the `surgical-media` skill repository. `README.md` is the human manual, `SKILL.md` the agent manifest — this file exists so you don't relearn the traps.

## Repo shape

- `surgical-media` is a Hermes **skill** (deterministic video pipeline: storyboard → MP4), not a published package. **This directory is not under version control** — no `.git`; `.gitignore` and `.github/workflows/skill-ci.yml` are staged for a future repo. Ask before `git init` or committing anything.
- `Concept/` is the input transcript (design history). It is not the contract — code and `tests/` are.
- Runtime deps: **Pillow ≥ 10.1 + ffmpeg/ffprobe on PATH** (`requirements.txt`). `edge-tts` is optional (`requirements-tts.txt`) and **tests never use it** (offline by design). Audio/geometry are stdlib-only — no NumPy (`docs/adr/0001-stdlib-first-verified-pipeline.md`).
- `SKILL.md` must stay ≤ 120 lines (agent manifest: stages/invariants/gotchas). Element catalog and parameter specs live in `references/storyboard-guide.md` — don't duplicate them here or in `SKILL.md`.
- Stage 1 acquires **subject imagery**, not just facts: `scripts/fetch_assets.py --query "<subject>" --out-dir assets --count 3` pulls Openverse CC-allowlisted photos (`by`/`by-sa`/`cc0`/`pdm`; `*-nd`/`*-nc` rejected), PIL-verifies them, and writes `assets/manifest.json` whose `attribution` strings go verbatim into `image` elements. Hotlinking into a render is never acceptable; record the manifest.

## Commands (all run green locally; CI parity noted)

```bash
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json   # demo must always validate
ruff check --no-cache scripts/ tests/
ruff format --check --no-cache scripts/ tests/
python3 -m pytest tests/ -q                                            # 104 tests, all green
check-jsonschema --check-metaschema schemas/*.schema.json
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs     # seconds — visual smoke, no ffmpeg needed
python3 scripts/render_engine.py --demo --output /tmp/sm_gate.mp4       # only when render code changed; exit 0 + QC ok:true
```

- Single test: `python3 -m pytest "tests/test_visual_smoke.py::test_box_downsample_keeps_thin_lines" -q`
- CI runs the same gates plus a full `render_engine.py --demo --… --quality draft` smoke gate; ffmpeg is apt-installed there and integration tests **skip cleanly** without it.
- **mypy** is configured in `pyproject.toml` but not enforced and not installed in the usual scratch venv — ruff + pytest are the enforced gates; mypy runs are advisory only.
- **markdownlint** (npm, v0.49.1) fails on *pre-existing* house docs (`references/`, `docs/adr/`: MD022/MD031/MD034/MD060) — it is not a gate. Don't present it as one, and don't add it to CI without fixing those files first.
- Before spending a full render: `--estimate` (frame count / audio cost) and `--thumbnails DIR` (one PNG per scene). `final` = crf 18, demo/draft = crf 26. Rendering is deterministic only per machine/Pillow build — diff frames, not hashes.
- `*.mp4`, `*_work/`, `audio/` (TTS voice stems, written next to the storyboard or `--media-dir`), `__pycache__/`, `.pytest_cache/` are gitignored artifacts. Never commit rendered outputs.

## Hard-won invariants (do not relearn)

- **Audio-first timing.** Frame counts come from measured VO durations (ffprobe) or explicit beat durations — never guessed. `words[]` and `sfx_events[].t_sec` are **scene-relative**; `start_sec` is auto-assigned sequentially.
- **Two timing paths** (`scripts/tts_align.py`): online → edge-tts `WordBoundary` events (measured, 100 ns ticks); `--offline` or any TTS failure → syllable-weighted model. **Never re-split a joined string to index into `words`** — a boundary event can carry multiple whitespace-separated words (e.g. `"since 2009"`). Wrap the measured token stream (see `paint_kinetic_captions`, which had exactly this bug).
- **`--trim-silence` is a no-op when measured boundaries exist** (word offsets are relative to the untrimmed stem) and was historically destructive to internal pauses — do not "fix" the missing trim. `build_master_wav` must stay tolerant of VO stems shorter than `duration_sec` (regression-tested).
- **New element type?** Painter in `elements.py` + entry in `KNOWN_ELEMENTS` (`storyboard.py`) + tests, in the same change. Unknown types render as **silent no-ops**; only a `warn` line is printed.
- **yuv420p + H.264 high/4.2 + `+faststart`, or nothing** — anything else breaks iOS/IG/TikTok. Audio targets −14 LUFS, −1 dBFS ceiling, 48 kHz stereo; failed ffprobe QC exits 3.
- **RGB only.** ImageDraw can't alpha-blend: buffers are RGB end-to-end; translucency is pre-blended; scene fades are RGB `Image.blend`s.
- **Claims = code.** SKILL.md/README claims must land as tested code in the same change. The test count is quoted in docs — bump every occurrence (SKILL.md, AGENTS.md, `docs/adr/`).
- **Subprocess discipline:** list-form argv, `timeout=`, `capture_output`/`DEVNULL`, `shutil.which()` before use, never `shell=True`.
- **Zero PII** — synthetic placeholders only.
- **Scope:** don't edit sibling skills (`surgical-audit/`, etc.) from this repo. Don't run `install_surgical_media.sh` (installs to `~/.hermes/skills/creative/surgical-media`) without asking.
- **No golden-image tests** by design (fonts drift across hosts) — CI guards on pixel-presence smoke tests instead. Don't bless PNGs.
- **AI image generation is not a fallback** for imagery (credentials unreliable; dishonest for factual documentary content). Fetch open-licensed photos; label every asset with its source license in-frame.

## Demo regeneration

`examples/tri_archetype_storyboard.json` is generated — **never hand-edited**. After changing `build_demo.py` or `tts_align.py`, run `python3 scripts/build_demo.py`, re-validate the board, and re-run the suite.
