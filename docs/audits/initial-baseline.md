# Initial baseline audit — 3.0 job layer (Wave 0)

**Date:** 2026-11-21 · **Commit:** `506f9fd` (+ uncommitted 3.0 work) · **Scope:** bounded audit required by master plan §3 before any new module.

## Environment

Python 3.11.16 (`.venv`), ruff 0.17.5, mypy 2.4.1, pytest suite via `.venv/bin/python -m pytest tests -q`. System `python3` (3.15) has no pytest — always use the gate venv.

## Baseline results (measured)

| Check | Result |
| :-- | :-- |
| `pytest tests -q` before 3.0 work | **476 passed, 7 warnings, 54 s** (matches AGENTS.md; the 375/395 figures in older plan text are stale history) |
| `mypy scripts/` (strict) after 3.0 work | 0 issues, 44 source files |
| ruff check / format on new files | clean |
| `bash scripts/ci_gates.sh` after 3.0 work | **11/11 gates green**, 514 tests passed (476 + 38 new), draft render + QC ok (2026-11-21) |
| Real job E2E (tri_archetype board, 15 s target) | create→plan→submit→preview→audit→approve→export → PACKAGED; draft render 68 s, QC ok:true; export refused before approval |
| Gate script | had labels `x/9` but 10 gates; relabeled to `x/11` with the new job gate |

## Capability inventory (proposal item → existing code)

| Master-plan item | Verdict | Evidence |
| :-- | :-- | :-- |
| Asset rights registry (§6.4) | **Exists (partial)** — license allowlist + manifest + file-existence check. Gap: no per-asset restriction/expiry fields | `fetch_assets.py`, `monetization_gate.check_assets_license_allowlist` |
| Technical QC | **Exists** | `verify_output.py` (codec/LUFS/drift), `ci_gates.sh` gate 9 |
| Platform adapter (§5.6) | **Exists (partial)** — 3 presets (`shorts_tiktok_reels`, `youtube_long`, `square`); no per-platform YouTube/TikTok split, no `last_reviewed` | `platform_presets.PRESETS` |
| Publishing package | **Exists (partial)** — `publish_kit.build_kit` (chapters, credits, thumbnail pick); no disclosure/provenance block | `publish_kit.py` |
| Visual QA / retention heuristics | **Partial** — `style_lint.py`, `retention_static_hold`, `thumbnail_gen.py`, `contact_sheet.py`; no black-frame/overflow detector | those modules |
| Voices | **Exists** — multi-voice casting | `tts_align.py`, `tests/test_voice_cast.py` |
| Research contract | **Partial** — `investigation_brief.schema.json` (3–8 facts, source URL strings); no claim IDs / claim types / contradictions | `schemas/investigation_brief.schema.json` |
| Job model, lifecycle, persistence, CLI, approval gate, budget gate | **Did not exist → built in this wave** | `job_*.py`, ADR 0005 |
| Originality analyzer, editorial risk review, provider adapters, API, analytics, Content DNA | **Not built (deferred)** | master plan Waves 2–5 |

## Security / reliability review

- `shell=True` / `os.system`: **0** occurrences in `scripts/`. SECURITY.md claim holds.
- Subprocess call sites: 13 (`subprocess.run/Popen/check_output`) vs 15 `timeout=` occurrences — consistent with "explicit timeout"; a per-call-site proof is **not** done (follow-up).
- Network: only `fetch_assets.py` (https-only, 50 MB cap per SECURITY.md; not re-tested here). `threejs/node_modules` is vendored `three` (MIT).
- Secrets: grep hits are identifiers/comments (`token` in text/code painters); no credential handling exists. The job layer adds none and keeps publishing credentials out of scope.
- New code: ids and artifact names are regex-confined (traversal tests), writes are atomic, agent output is validated before state advances, export is bound to the approved video hash.

## Not verified here (honest gaps)

Full `ci_gates.sh` render-time baseline (gates 8/9) is recorded in the walkthrough, not re-measured per backend; Blender/Three.js host-dependent paths untouched; `fetch_assets` live network behaviour untested; per-call-site subprocess timeout proof.

## Recommended changes to the proposal

1. Keep flat `scripts/` layout; use `scripts/job_*.py` (ADR 0005).
2. Reuse `platform_presets`, `publish_kit`, `monetization_gate`, `verify_output`; extend rather than add parallel modules.
3. Extend `investigation_brief` with claim IDs *before* building a Research Director (Wave 2).
4. Use repo preset names (`shorts_tiktok_reels` …) instead of `tiktok`/`youtube_shorts` in job requests.
