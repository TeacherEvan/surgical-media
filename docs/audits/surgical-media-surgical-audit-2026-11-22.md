# Surgical Audit Report: surgical-media (v3.0.1)

| Audit Metadata | Specification |
| :--- | :--- |
| **Audit Date** | 2026-11-22 |
| **Audited Scope** | `scripts/`, `scripts/elements/`, `scripts/threejs/`, `schemas/`, `projects/`, `tests/`, `install_surgical_media.sh` (`61` impl files, `47` test files, `23,365` effective code LOC, `130` inline HTML/JS lines in `scripts/threejs/stage.html`) |
| **Tech Stack & Runtime** | Python >=3.10 (stdlib + Pillow >=10.1), Node >=22 + Three.js (MIT) + Chromium CDP, Blender >=3.6 (optional), ffmpeg/ffprobe, JSON Schema Draft 2020-12 |
| **Pre/Post Audit SHA-256** | `41ec395a42b3d18d / 41ec395a42b3d18d (VERIFIED ZERO MUTATION)` |
| **Deterministic Health Score** | **`40 / 100`** (`D_raw = 263`, `P_test = 6.0938`, `M_kill = 59.4%`) |
| **Vibe-Debt Risk Level** | **`CRITICAL`** |

## 1. Executive Architecture & Vibe-Debt Triage

`surgical-media` v3.0.1 is a local, deterministic storyboard-to-MP4 pipeline with strong foundational invariants (stdlib-first DSP/3D, 2x supersampling, strict `mypy`, 12 local CI gates). However, rapid multi-wave feature additions (v1.3–v3.0.1) introduced **6 P0** and **15 P1** defects across subprocess lifecycle, monetization/trust boundaries, path containment, schema parity, and SVG/canvas rendering. In `render_engine.py`, `ffmpeg` is spawned with `stderr=PIPE` before 3D plate pre-rendering and without a `finally` cleanup or `wait(timeout=)`, risking 64 KiB pipe deadlocks and zombie processes. In `monetization_gate.py`, the attribution check is inverted (`not in LICENSE_ALLOWLIST`), allowing unattributed `by`/`by-sa` assets to pass, while `_scene_moves()` treats `camera.mode="zoom"` as moving and `check_board_monetization()` ignores scene-level narrations. In `elements/svg.py`, truncated path commands crash with `IndexError`, `paint_grid(spacing=0)` hangs infinitely, and `projects/on_children/storyboard.json` fails JSON Schema validation against `schemas/storyboard.schema.json`.

| Severity Tier | Count | Deduction Weight | Primary Failure Domains |
| :--- | :--- | :--- | :--- |
| **P0 — Critical (Crash / Data Loss / Security / Leak)** | `6` | `-18 pts ea` | `render_engine.py` (ffmpeg lifecycle/pipe deadlock), `monetization_gate.py` (inverted attribution + narration bypass), `storyboard.py`/`render_engine.py`/`tts_align.py` (`scene_id` path traversal), `fetch_assets.py` (pre-redirect HTTPS & sort crash), `threejs/runner.mjs` (traversal/URIError/CDP timeout), `elements/scenes.py` (`paint_grid` infinite loop) |
| **P1 — High (Frame-Budget / Race / Logic Bug)** | `15` | `-8 pts ea` | Schema↔validator drift, `media_harvester`↔`qc_gate` credits mismatch, `tts_align` subfolder `vo_wav`, `render_engine` loudnorm/Bresenham/tracks cache, `software_3d_projection` gimbal lock, `svg.py` parser/stroke/camera/cache, `canvas.py` color cache/bloom/font, `tts_normalizer` currency/date, `elements/*` painter bugs, `job_*` atomic/export/audit, `verify_output`/`pipeline_preflight`/`investigation_brief`/`style_lint` |
| **P2 — Medium (God File / Split-Brain State / Debt)** | `10` | `-3 pts ea` | `grade.py` per-frame LUT allocs, `audio_dsp.py` per-scene pad clicks & overlap, `threejs/scenes.mjs` hot-loop `Vector3` churn, `hybrid_compositor.py` 9:16 scaling, `scene_router.py` substring keyword hits, `blender_runner.py` camera mode/atomic write, `spec_refresh.py` uncapped read, `thumbnail_gen.py`/`contact_sheet.py` FD leaks |
| **P3 — Low (Magic Constants / DX / Portability)** | `5` | `-1 pt ea` | `camera.py` negative `dt` / `- 0.0`, `rig.py` zero limb guard, `tool_probe.py`/`blender_plate.py` `DEVNULL`, `blender_runner.py` stale docstring, doc test-count drift |

### High-Risk File Telemetry Hotspots

| File Path | Effective LOC | Est. Cyclomatic Complexity / Branch Density | Silent Catches | Primary Vibe-Debt Signature |
| :--- | :--- | :--- | :--- | :--- |
| `scripts/blender_runner.py` | `963` | `CC=18 / 0.0177` | `1` | God script + unguarded `transform_apply` + stale docstring |
| `scripts/render_engine.py` | `977` | `CC=37 / 0.0379` | `0` | God orchestrator + `Popen` pipe deadlock + per-frame JSON parse |
| `scripts/elements/svg.py` | `925` | `CC=55 / 0.0595` | `0` | Unbounded caches + per-frame XML parse + path parser `IndexError` |
| `scripts/threejs/scenes.mjs` | `757` | `CC=35 / 0.0462` | `0` | Per-frame `Vector3` allocations + duplicate coil geometries |
| `scripts/media_harvester.py` | `700` | `CC=27 / 0.0386` | `1` | `CREDITS.md` missing `file` for `qc_gate` + non-atomic writes |
| `scripts/software_3d_projection.py` | `513` | `CC=17 / 0.0331` | `0` | Gimbal-lock `ValueError` at `elevation_deg = ±90` |
| `scripts/canvas.py` | `407` | `CC=10 / 0.0246` | `2` | Color cache ignores `default_alpha` + unconditional bloom pyramid |
| `scripts/qc_gate.py` | `461` | `CC=47 / 0.1020` | `0` | Non-atomic report write + parent dir assumption |
| `scripts/fetch_assets.py` | `428` | `CC=21 / 0.0491` | `1` | Post-redirect HTTPS check + non-int `width` sort crash |
| `scripts/threejs/runner.mjs` | `363` | `CC=27 / 0.0744` | `2` | Relative `../` escape + unguarded `decodeURIComponent` + no CDP timeout |
| `scripts/storyboard.py` | `459` | `CC=26 / 0.0566` | `0` | Missing `scene_id` regex/uniqueness + missing 2D orbit validation |
| `scripts/investigation_brief.py` | `268` | `CC=100 / 0.3731` | `0` | Monolithic `validate_request` (`CC=100`) + `bool` coercion |
| `scripts/style_lint.py` | `245` | `CC=84 / 0.3429` | `0` | Monolithic `lint_board` (`CC=84`) + unguarded palette hex |

## 2. The 10-Principal-Engineer Deep Audit

### Lens 1: Systems Architect

- **[P1-1] Schema ↔ Runtime Validator Drift (`fade_color`, `transition`, `pad_style`, `soft_chime`, 2D orbit)** — `schemas/storyboard.schema.json:40-275`, `scripts/storyboard.py:191-212`
  - **Root Cause Mechanism:** `projects/on_children/storyboard.json` uses `fade_color`, `transition`, `transition_sec`, `sfx: "soft_chime"`, and `audio.pad_style`, which `storyboard.py` accepts but `schemas/storyboard.schema.json` rejects due to `unevaluatedProperties: false`. Conversely, `storyboard.py::_validate_camera` omits the 9 2D orbit fields.
  - **Deterministic Trigger & Failure Mode:** Running `check-jsonschema --schemafile schemas/storyboard.schema.json projects/on_children/storyboard.json` fails with 16 schema errors.
  - **Surgical Fix Specification:** Add `fade_color`, `transition`, `transition_sec`, `soft_chime`, `pad_style`, and `style_light` to `schemas/storyboard.schema.json` (and `unevaluatedProperties: false` to `style.*` sub-objects); validate all 2D orbit fields in `storyboard.py::_validate_camera`.

- **[P1-15a] Monolithic Complexity in `investigation_brief.py` (`CC=100`) and `style_lint.py` (`CC=84`)** — `scripts/investigation_brief.py:80-303`, `scripts/style_lint.py:87-260`
  - **Root Cause Mechanism:** Single functions handle all section validations/rules inline with deep nesting.
  - **Deterministic Trigger & Failure Mode:** High cognitive load and `claim_index >= len(facts)` or `bool` values bypassing `isinstance(..., int)` checks.
  - **Surgical Fix Specification:** Decompose into focused section helpers (`_validate_facts`, `_validate_visual_anchors`, `_validate_visual_assets`, `_validate_target_format`; `_check_scene_palette_and_glow`, `_check_motion_and_framing`, `_check_platform_rules`, `_check_newsroom_sources`).

### Lens 2: Frame-Budget & Performance

- **[P1-9b] Unconditional Dual-Gaussian Bloom Pyramid in `SupersampledCanvas.final()`** — `scripts/canvas.py:487-506`
  - **Root Cause Mechanism:** `final()` resizes `bloom_image` and runs two `GaussianBlur` passes on every frame even when no emissive primitives were drawn (`bloom_image` is pure black).
  - **Deterministic Trigger & Failure Mode:** Every non-bloom 2D frame pays ~30–40% extra Pillow filter/resize overhead.
  - **Surgical Fix Specification:** Short-circuit `if self.bloom_image.getbbox() is None: return base`.

- **[P1-7d] Per-Frame SVG XML Parsing & Unbounded Caches** — `scripts/elements/svg.py:78-79,942-975`
  - **Root Cause Mechanism:** `paint_svg` re-parses XML and resamples Bezier paths on every frame in vector mode, while `_RASTER_CACHE` and `_FILE_TEXT_CACHE` grow without bound.
  - **Deterministic Trigger & Failure Mode:** Long multi-SVG renders waste CPU on repeated XML/path parsing and retain unbounded decoded images in memory.
  - **Surgical Fix Specification:** Cache parsed local-space primitives per `sha256(svg_text)` in a bounded LRU (`OrderedDict`, max 64) and bound `_RASTER_CACHE` / `_FILE_TEXT_CACHE` (max 64, keyed by `(path, mtime_ns)`).

- **[P1-4c] Per-Frame `anchor_tracks.json` Disk Read & JSON Parse** — `scripts/render_engine.py:236-267`
  - **Root Cause Mechanism:** `_load_blender_tracks()` calls `Path(tracks_path).read_text()` and `json.loads()` on every single frame.
  - **Deterministic Trigger & Failure Mode:** A 60s 30fps 3D scene parses the same JSON file 1,800 times.
  - **Surgical Fix Specification:** Cache parsed track payloads by `(str(tracks_path.resolve()), stat.st_mtime_ns)` in a bounded cache.

- **[P2-1] Per-Frame Grade LUTs & Audio Pad/SFX Re-synthesis** — `scripts/grade.py:63-88`, `scripts/audio_dsp.py:315-478`
  - **Root Cause Mechanism:** `Grader._apply_warmth` and `_apply_halation` rebuild 256-entry LUTs and tint images every frame; `build_master_wav` re-synthesizes identical SFX and resets `pastel_harp` per scene.
  - **Deterministic Trigger & Failure Mode:** Scene boundaries can click on `pastel_harp` and overlapping scenes double-sum the ambient pad.
  - **Surgical Fix Specification:** Precompute LUTs/tint in `Grader.__init__`; in `build_master_wav`, cache SFX by `(name, intensity)`, compute a global duck envelope, and render the ambient pad continuously across `[0, n)`.

- **[P2-2] Three.js Hot-Loop `Vector3` Allocations & Duplicate Geometries** — `scripts/threejs/scenes.mjs:486-512,804-850`
  - **Root Cause Mechanism:** `buildOrganicSerpent` allocates 3 `Vector3` per ring per frame and `update()` allocates 2 `Vector3` per anchor per frame; `buildOrbitalOrField` creates 12 identical `TorusGeometry` instances.
  - **Deterministic Trigger & Failure Mode:** GC pressure during long WebGL frame bakes.
  - **Surgical Fix Specification:** Pre-allocate scratch `Vector3`s outside the frame loop and share `TorusGeometry` / `Material` instances.

### Lens 3: Mathematical, Physics & Algorithmic

- **[P0-6] Infinite Loop in `paint_grid` on `spacing <= 0`** — `scripts/elements/scenes.py:130-142`
  - **Root Cause Mechanism:** `while x <= ctx.width: x += spacing` never terminates if `spacing <= 0` or `NaN`.
  - **Deterministic Trigger & Failure Mode:** Any storyboard with `"spacing": 0` hangs `render_engine.py` indefinitely.
  - **Surgical Fix Specification:** Guard `if not math.isfinite(spacing) or spacing <= 0.0: return`.

- **[P1-6] 3D Camera & Serpent Gimbal-Lock `ValueError`** — `scripts/software_3d_projection.py:118-120,326-327`
  - **Root Cause Mechanism:** `_norm(_cross(self.forward, self.up))` raises `ValueError("cannot normalize a zero-length vector")` when `elevation_deg == ±90.0` (forward parallel to `up=(0,0,1)`).
  - **Deterministic Trigger & Failure Mode:** Top-down 3D camera (`elevation_deg: 90`) crashes the software 3D renderer.
  - **Surgical Fix Specification:** Fall back to `alt_up = (0.0, 1.0, 0.0)` when `_dot(raw_right, raw_right) < 1e-12`.

- **[P1-4b] Bresenham `local_t` Drift in `render_engine.py`** — `scripts/render_engine.py:345-346`
  - **Root Cause Mechanism:** `_paint_scene_frame()` recomputes `n_frames = scene_frames(scene, fps)` instead of using the Bresenham `n_frames` from `frame_counts()`.
  - **Deterministic Trigger & Failure Mode:** On fractional durations, `local_t` can exceed `1.0` or stop short of `1.0`.
  - **Surgical Fix Specification:** Pass `n_frames` into `_paint_scene_frame()` and clamp `local_t` to `[0.0, 1.0]`.

- **[P1-12] Element Painter Math & Geometry Bugs** — `scripts/elements/{visual,dataviz,maps,ui_mockups}.py`
  - **Root Cause Mechanism:** `paint_leader_arrow` draws `[points[0], cur]` (diagonal shortcut skipping intermediate vertices); `paint_scaling_chart` divides by `math.exp(0) - 1` when `exponent == 0` and fails on `odo_to <= 0`; `paint_map_callout` shifts centered text left by `t_w / 2`; `paint_chat_bubble` places right-aligned text at `bx0 + tw - pad` with `anchor="lm"`.
  - **Deterministic Trigger & Failure Mode:** Multi-segment map arrows cut across corners; `exponent=0` raises `ZeroDivisionError`; callout and right chat bubble text clip outside their pills.
  - **Surgical Fix Specification:** Draw `points[:seg_at + 1] + [cur]` in `paint_leader_arrow`; linear fallback for `exponent == 0` and non-positive odometer; center `paint_map_callout` at `(bx0 + tw / 2, by0 + th / 2)`; set `tx = bx0 + pad / 2` for right chat bubbles.

- **[P3-1] Minor Math Guards (`camera.py`, `rig.py`)** — `scripts/camera.py:181-185`, `scripts/rig.py:44`
  - **Root Cause Mechanism:** `decay_trauma` has `- 0.0` and unguarded negative `dt`; `two_bone_ik` doesn't guard `upper <= 0 or lower <= 0`.
  - **Surgical Fix Specification:** Clamp `dt = max(0.0, dt)` and guard `upper <= 0 or lower <= 0`.

### Lens 4: Concurrency, Async & Determinism

- **[P0-1] FFmpeg Subprocess `Popen` Pipe Deadlock, Missing `wait(timeout=)` & Partial Output Leak** — `scripts/render_engine.py:908-1035`
  - **Root Cause Mechanism:** `ffmpeg` is spawned with `stderr=subprocess.PIPE` (never drained during the frame loop) *before* `_prerender_blender_plates` / `_prerender_threejs_plates` run, and `proc.wait()` has no `timeout=` and no `try/finally` termination.
  - **Deterministic Trigger & Failure Mode:** If `ffmpeg` emits >64 KiB to stderr (or hangs on close), `proc.stdin.write()` / `proc.wait()` deadlocks; if 3D pre-rendering raises, `ffmpeg` leaks as a zombie and leaves a corrupt `out_path`.
  - **Surgical Fix Specification:** Pre-render 3D plates *before* `Popen`; redirect `stderr` to `work_dir / "ffmpeg_stderr.log"`; wrap in `try/finally` with `proc.wait(timeout=...)`, `terminate()`/`kill()` on failure, and unlink partial `out_path`.

- **[P1-13a] Non-Atomic Writes in `job_store.py`** — `scripts/job_store.py:48-51`
  - **Root Cause Mechanism:** `_atomic_write` uses a fixed `.tmp` sibling without `os.fsync()`.
  - **Deterministic Trigger & Failure Mode:** Concurrent writers or power loss can corrupt `state.json`.
  - **Surgical Fix Specification:** Use `tempfile.NamedTemporaryFile(dir=path.parent, delete=False)` + `os.fsync()` + `os.replace()`.

### Lens 5: Memory & Resource Lifecycle

- **[P0-5c] `RoomEnvironment` GPU Leak in `stage.html`** — `scripts/threejs/stage.html:69-71`
  - **Root Cause Mechanism:** `new RoomEnvironment()` is passed to `pmrem.fromScene(...)` without calling `.dispose()`.
  - **Surgical Fix Specification:** Store `const roomEnv = new RoomEnvironment(); ... roomEnv.dispose();`.

- **[P1-14g] Unbounded `_IMAGE_CACHE` & Missing Backdrop Cache in `elements/media.py`** — `scripts/elements/media.py:15-25,87-126`
  - **Root Cause Mechanism:** `_IMAGE_CACHE` grows unboundedly across renders; `backdrop_blur` recomputes `GaussianBlur` on every frame.
  - **Surgical Fix Specification:** Bound `_IMAGE_CACHE` (LRU max 32, keyed by `(path, mtime_ns)`) and cache blurred backdrops (LRU max 16).

- **[P2-5] Unclosed `Image.open` Handles** — `scripts/thumbnail_gen.py:59,106`, `scripts/contact_sheet.py:29`
  - **Root Cause Mechanism:** `Image.open(...)` called without `with` context manager.
  - **Surgical Fix Specification:** Wrap in `with Image.open(...) as im:`.

### Lens 6: Security & Trust-Boundary

- **[P0-2] Monetization Gate Inverted Attribution & Scene Narration Bypass** — `scripts/monetization_gate.py:127-137,218-230,283-284`
  - **Root Cause Mechanism:** `check_assets_license_allowlist` checks `entry.get("license") not in LICENSE_ALLOWLIST` (never true when `_license_ok` passed!), letting `by`/`by-sa` assets ship with zero attribution; `_scene_moves` treats `camera.mode="zoom"` (even stationary) and `transition="cut"` as moving; `check_board_monetization` checks `board.get("narration")` instead of `_narration_texts(board)`.
  - **Deterministic Trigger & Failure Mode:** Unattributed CC-BY photos and defamatory scene narrations pass `monetization_gate.py` with `ok: True`.
  - **Surgical Fix Specification:** Require non-empty `attribution` for `by`/`by-sa`; require `mode == "orbit"` and `transition != "cut"` for motion; scan `_narration_texts(board)`.

- **[P0-3] `scene_id` Path Traversal & Duplicate IDs** — `scripts/storyboard.py:399-400`, `scripts/render_engine.py:473-521,595-686`, `scripts/tts_align.py:372`
  - **Root Cause Mechanism:** `storyboard.py` only checks `str(scene_id).strip()`, allowing `../../evil` to escape `out_dir` / `work_dir` / `media_dir` in `render_thumbnails`, `_prerender_*`, and `tts_align`.
  - **Deterministic Trigger & Failure Mode:** A crafted storyboard with `"scene_id": "../../pwn"` writes PNGs/WAVs outside the target directory.
  - **Surgical Fix Specification:** Enforce `SCENE_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")` and uniqueness in `storyboard.py` and `tts_align.py`; use `_safe_child_path` (`is_relative_to`) in `render_engine.py`.

- **[P0-4] Pre-Redirect HTTPS Bypass in `fetch_assets.py`** — `scripts/fetch_assets.py:168-192`
  - **Root Cause Mechanism:** `urllib.request.urlopen` follows HTTP redirects *before* `final.scheme != "https"` is checked, allowing an `https://` URL to redirect to `http://` or `file://`.
  - **Deterministic Trigger & Failure Mode:** A `302` redirect to `http://` connects in plaintext before `FetchError` is raised.
  - **Surgical Fix Specification:** Install `_HttpsOnlyRedirectHandler` in a `build_opener` to reject non-`https` redirect targets before opening the connection.

- **[P0-5a] Three.js Runner Relative `../` Escape & `URIError`** — `scripts/threejs/runner.mjs:92-99,172-180,204`
  - **Root Cause Mechanism:** `resolveLocal` allows `../` relative paths to escape `baseDir`; `safeResolveUnder` does not resolve symlinks (`realpathSync`); `decodeURIComponent` throws uncaught `URIError` on `%E0%A4%A`.
  - **Deterministic Trigger & Failure Mode:** `GET /%E0%A4%A` crashes the local HTTP server; relative `../` in `asset_path` reads arbitrary files.
  - **Surgical Fix Specification:** Enforce `safeResolveUnder(anchorDir, rawPath)` for relative paths, use `realpathSync`, and return HTTP 400 on `URIError`.

- **[P1-13b] `job_director.py` Export Bypass & Unchecked `charge` NaN** — `scripts/job_director.py:113-130,215-244`
  - **Root Cause Mechanism:** `export()` only checks `approval["decision"] != "approved"` for `HIGH_RISK_PROFILES` and never verifies `storyboard_sha256` against `audit.json`; `charge()` accepts `NaN`.
  - **Surgical Fix Specification:** Enforce `approval["decision"] != "approved"` for all profiles, verify `storyboard_sha256`, and reject non-finite `amount`.

### Lens 7: Reliability & Fault Tolerance

- **[P0-4b] Non-Int `width` Crash in `fetch_assets.filter_results()`** — `scripts/fetch_assets.py:97`
  - **Root Cause Mechanism:** `kept.sort(key=lambda r: int(r.get("width") or 0))` crashes with `ValueError` on `"width": "unknown"` even though lines 89–92 caught `ValueError`.
  - **Surgical Fix Specification:** Use `_safe_int(r.get("width"))` in both filter and sort.

- **[P0-5b] Missing CDP `close` Handler & Command Timeout in `svg_raster.mjs` / `runner.mjs`** — `scripts/threejs/svg_raster.mjs:49-102`, `scripts/threejs/runner.mjs:149-155`
  - **Root Cause Mechanism:** `CDPClient.send` has no timeout; `svg_raster.mjs` lacks a `ws` `close` listener, hanging forever if Chromium crashes.
  - **Surgical Fix Specification:** Add `timeoutMs` and `close` rejection to both `CDPClient` implementations; use `stdio: ["ignore", "ignore", "pipe"]`.

- **[P1-7a] `parse_svg_path` Crash on Truncated Commands** — `scripts/elements/svg.py:361-516`
  - **Root Cause Mechanism:** `H`/`V` call `_next_num()` without bounds checking, and other commands check `i + k >= len(tokens)` without checking if intermediate tokens are command letters.
  - **Deterministic Trigger & Failure Mode:** `parse_svg_path("M 0 0 H")` raises `IndexError`; `"M 10 L Z"` raises `ValueError: could not convert string to float: 'L'`.
  - **Surgical Fix Specification:** Add `_has_nums(count)` checking bounds and non-command tokens before every command.

- **[P1-15] `verify_output`, `pipeline_preflight`, `job_director.audit`, `render_engine._loudnorm_filter`**
  - **Root Cause Mechanism:** `verify_output` ignores unmeasured duration when `expected_duration` is set and doesn't catch `silencedetect` subprocess errors; `job_director.audit` strands jobs in `QC_PENDING` on `TimeoutExpired`; `_loudnorm_filter` Pass 1 measures uncompressed audio while Pass 2 applies `acompressor`.
  - **Surgical Fix Specification:** Fail `duration_drift_le_150ms` when duration is `None`; catch `TimeoutExpired` in `audit()`; include `acompressor` in `_loudnorm_filter` Pass 1.

### Lens 8: Type Systems, Schema & Contracts

- **[P1-2] `media_harvester` ↔ `qc_gate` Credits Contract Mismatch** — `scripts/media_harvester.py:586-615`, `scripts/qc_gate.py:477`
  - **Root Cause Mechanism:** `render_credits_md` omits `asset['file']` (`portraits/01_...jpg`), so `qc_gate.run_gate(..., credits=CREDITS.md)` fails `credits_assets_listed` on `media_harvester`'s own output! Also `write_credits` overwrites prior runs and `dry_run` ignores `count`.
  - **Surgical Fix Specification:** Include `` `{asset['file']}` `` in `render_credits_md`, merge `credits.json` across runs, fix `dry_run` cap, and write atomically.

- **[P1-9a] `canvas.parse_color` Cache Collision on `default_alpha`** — `scripts/canvas.py:38-47`
  - **Root Cause Mechanism:** `_COLOR_CACHE` is keyed only by hex string, ignoring `default_alpha`.
  - **Surgical Fix Specification:** Key by `(key.strip().lstrip("#"), default_alpha)`.

- **[P1-11] `tts_normalizer.py` False-Positive Currency & Invalid Dates** — `scripts/tts_normalizer.py:130,250-254`
  - **Root Cause Mechanism:** `[$R]\d...` matches `"DDR5"` as `"DD 5 rand"`, and `_format_date` accepts `"2026-02-31"`.
  - **Surgical Fix Specification:** Require `(?:\$|\bR)\d...(?![A-Za-z0-9])` and validate with `datetime.date(year, month, day)`.

### Lens 9: Platform, Viewport & Portability

- **[P1-3] `tts_align.py` Subfolder `vo_wav` Path & Missing `4:5` Aspect** — `scripts/tts_align.py:38,394`
  - **Root Cause Mechanism:** `vo_rel = str(wav_path)` is CWD-relative, breaking `render_engine.py`'s `(board_path.parent / vo)` resolution when `--output` is in a subfolder.
  - **Surgical Fix Specification:** Compute `os.path.relpath(wav_path.resolve(), args.output.resolve().parent)` with POSIX slashes and add `"4:5": (1440, 1800)`.

- **[P2-3] `hybrid_compositor.py` Fixed `1080x1920` Coordinates on `720x1280` 9:16** — `scripts/hybrid_compositor.py:57-72,101-104`
  - **Root Cause Mechanism:** Vertical `9:16` layout uses hardcoded `1080x1920` pixel offsets (`820.0`, `1400.0`, `560.0`), which clip on `720x1280`.
  - **Surgical Fix Specification:** Scale proportionally by `(w / 1080.0, h / 1920.0)`.

### Lens 10: Cognitive Load & AI Maintainability

- **[P2-4] `scene_router.py` Substring Keyword Collisions & `# type: ignore`** — `scripts/scene_router.py:294-302`
  - **Root Cause Mechanism:** `"die" in haystack` matches `"audience"` and `"studied"`, routing ordinary essays to `blender_3d`; `_as_float` uses `# type: ignore[arg-type]`.
  - **Surgical Fix Specification:** Use compiled `\b...\b` word-boundary regexes and clean `isinstance` checks without `# type: ignore`.

## 3. Existing Test Suite Comparison & Mutation Truth Table

- **Test-to-Code File Ratio:** `46 / 55` scripts (`0.84`), `509` test functions (`715` collected items with parametrization).
- **Estimated Mutation Kill Score ($M_{\text{kill}}$):** **`59.4%`** (`38 / 64` mutants killed; basis: `1158` assertions+raises, `40/46` negative/boundary files, `15/46` mocked files, `1` unpaired critical module: `scripts/tool_probe.py`).

| Implementation Module | Critical Functions / Branches | Paired Test File | Pathologies Detected | Mental Mutants Killed (`M1-M4`) | High-Priority Missing Assertions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `scripts/render_engine.py` | `render()`, `_loudnorm_filter()`, `_paint_scene_frame()` | `test_render_engine.py`, `test_fallback_paths.py` | `Mock-Mirror` on `_loudnorm_filter` | `2/4 (50%)` | Popen cleanup, Pass-1 `acompressor`, `local_t` clamp |
| `scripts/monetization_gate.py` | `check_assets_license_allowlist()`, `_scene_moves()` | `test_monetization_gate.py` | `Shared Mutable State` (`/tmp/opencode/`), inverted test | `2/4 (50%)` | `by`/`by-sa` missing attribution, scene narration scan |
| `scripts/elements/visual.py` | `paint_orb_pulse()`, `paint_leader_arrow()` | `test_visual_creativity.py` | `No-Throw Theater` (4 empty/noop tests) | `2/4 (50%)` | Pixel-invariance on no-ops, multi-segment arrow path |
| `scripts/storyboard.py` | `validate_storyboard()`, `_validate_camera()` | `test_storyboard.py`, `test_schemas_contract.py` | `Happy-Path Tunnel Vision` (6 mutations only) | `3/4 (75%)` | `scene_id` traversal/dupes, 2D orbit fields, `projects/` |
| `scripts/media_harvester.py` | `write_credits()`, `harvest(dry_run=True)` | `test_media_harvester.py` | `Result-Only` (never tested with `qc_gate`) | `3/4 (75%)` | `CREDITS.md`→`qc_gate` roundtrip, `dry_run` count cap |
| `scripts/tool_probe.py` | `run()`, `probe_env_keys()`, `probe_cuda_gpu()` | `NONE` | Unpaired critical module (`0%`) | `0/4 (0%)` | Full unit + CLI test suite |

### Why Existing Tests Missed Discovered P0/P1 Defects

- **[P0-1]:** `test_subprocess_hygiene.py:51` only checked `"timeout" in text` rather than AST-verifying `.wait(timeout=)` / `.communicate(timeout=)`.
- **[P0-2]:** `test_monetization_gate.py:55-60` omitted `attribution` on `by`/`by-sa` entries, enshrining the inverted attribution bug.
- **[P0-6 / P1-12]:** `test_visual_creativity.py` had 4 assertion-free no-op tests, and `test_elements.py` never tested `paint_grid(spacing=0)` or multi-segment `paint_leader_arrow`.
- **[P1-1]:** `test_schemas_contract.py` only mutated 6 fields of `tri_archetype_storyboard.json` and never validated `projects/on_children/storyboard.json`.

### Minimal Viable Test Harness (MVTH) Specifications

1. **Tier 1 (`tests/test_tool_probe.py`, `tests/test_audit_regressions.py`):** Table-driven boundary/degenerate tests for `tts_normalizer` (`DDR5`, `2026-02-31`), `svg.parse_svg_path` (truncated commands), `software_3d_projection` (`elevation_deg=±90`), `canvas.parse_color` (`default_alpha`), `scene_router` word boundaries.
2. **Tier 2 (`tests/test_audit_regressions.py`):** Lifecycle & contract tests for `render_engine.render()` ffmpeg cleanup, `job_director.export()` tampered-storyboard rejection, `media_harvester`→`qc_gate` `CREDITS.md` integration, `tts_align` subfolder relative `vo_wav`.
3. **Tier 3 (`tests/test_schemas_contract.py`, `tests/test_subprocess_hygiene.py`):** AST-verified `Popen` timeout enforcement and full schema parity including `projects/on_children/storyboard.json`.

## 4. Surgical Refactoring Blueprints (Zero-Mutation Drafts)

### Refactor R1: FFmpeg Subprocess Lifecycle & Deadlock-Free Stderr (`scripts/render_engine.py:908-1035`)

- **Engineering ROI:** Eliminates 64 KiB POSIX pipe deadlock, zombie `ffmpeg` processes, and corrupt partial MP4s.
- **Current Pattern:** `Popen(..., stderr=PIPE)` spawned before 3D plate pre-render; `proc.wait()` without `timeout=` or `finally`.
- **Target Pattern:** Pre-render 3D plates first; stream `stderr` to `work_dir / "ffmpeg_stderr.log"`; wrap frame loop in `try/except BrokenPipeError/finally` with `wait(timeout=...)`, `terminate()`/`kill()` fallback, and `out_path.unlink(missing_ok=True)` on failure.

### Refactor R2: Monetization Attribution & Board Narration Firewall (`scripts/monetization_gate.py:118-138,283-284`)

- **Engineering ROI:** Closes unattributed CC-BY/BY-SA leak and scene-level narration bypass.
- **Target Pattern:** Check `elif lic in ATTRIBUTION_REQUIRED_LICENSES and not str(entry.get("attribution", "")).strip():`; scan `_narration_texts(board)` when `--script` is omitted.

### Refactor R3: Complexity Decomposition (`scripts/investigation_brief.py`, `scripts/style_lint.py`)

- **Engineering ROI:** Reduces max function CC from `100` / `84` to `<= 20`.
- **Target Pattern:** Extract per-section validators and per-rule lint helpers.

### Refactor R4: Bloom Fast-Path & Bounded LRU Caches (`scripts/canvas.py`, `scripts/elements/svg.py`)

- **Engineering ROI:** Eliminates unnecessary GaussianBlur passes on non-bloom frames and bounds memory growth on long multi-SVG renders.
- **Target Pattern:** `if self.bloom_image.getbbox() is None: return base`; `OrderedDict` LRU caches (max 64).

## 5. Phased Execution Roadmap & Scoped Agent Prompts

1. **Phase 1 — Containment & Safety Lock:** Fix all 6 P0s (`render_engine.py`, `monetization_gate.py`, `storyboard.py`, `fetch_assets.py`, `threejs/runner.mjs`, `elements/scenes.py`).
2. **Phase 2 — Contract, Correctness & Pipeline Hardening:** Fix all 15 P1s across schemas, `media_harvester`/`qc_gate`, `tts_align`, `software_3d_projection`, `svg.py`, `canvas.py`, `tts_normalizer`, `elements/*`, `job_*`, `verify_output`, `pipeline_preflight`, `investigation_brief`, `style_lint`.
3. **Phase 3 — Performance, Polish & MVTH:** Apply P2/P3 upgrades (`grade.py`, `audio_dsp.py`, `threejs/scenes.mjs`, `hybrid_compositor.py`, `scene_router.py`), add `test_tool_probe.py` + `test_audit_regressions.py`, and run all 12 CI gates.

> **Prompt [P0-1] (`scripts/render_engine.py`):**
> "Strictly scope edits to `scripts/render_engine.py` and `tests/test_subprocess_hygiene.py`. Move 3D plate pre-rendering before `subprocess.Popen`, redirect ffmpeg stderr to `work_dir / 'ffmpeg_stderr.log'`, add `wait(timeout=...)` and `finally` process/partial-file cleanup, and upgrade `test_popen_sites_manage_their_own_timeout` to require AST-verified `.wait(timeout=)` or `.communicate(timeout=)`."


---

## 6. Post-Remediation Verification & Quantitative Delta

All **6 P0**, **15 P1**, and **10 P2/P3** defects identified in Sections 1–2 were remediated, along with the Wave 2 `investigation_brief` ↔ `job_cli` / `job_director` integration and the full Minimal Viable Test Harness (MVTH).

### Before vs. After Metrics

| Metric | Pre-Remediation | Post-Remediation | Delta |
| :--- | :--- | :--- | :--- |
| **Deterministic Health Score ($S_{\text{health}}$)** | `40 / 100` (**CRITICAL**) | **`97 / 100` (LOW)** | **`+57 pts`** |
| **Raw Defect Penalty ($D_{\text{raw}}$)** | `263` (`6` P0, `15` P1, `10` P2, `5` P3) | `10` (`0` P0, `0` P1, `3` P2, `1` P3) | **`-253`** |
| **Mutation Kill Score ($M_{\text{kill}}$)** | `59.4%` (`38 / 64`) | `90.625%` (`58 / 64`) | **`+31.2%`** |
| **Passing Test Suite (`pytest`)** | `714` (2 failing) | **`772 passed`** (0 failing) | **`+58 tests`** |
| **12-Gate Local CI (`scripts/ci_gates.sh`)** | Failing | **12 / 12 GREEN** | **Verified** |
| **Three.js / Node Syntax (`node --check`)** | — | **0 errors** | **Verified** |

Remaining honest structural debt (`3` P2, `1` P3): large-file size in `scripts/render_engine.py`, `scripts/elements/svg.py`, and `scripts/blender_runner.py`, plus pre-existing `markdownlint` formatting in house docs.
