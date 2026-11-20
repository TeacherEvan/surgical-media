#!/usr/bin/env python3
"""render_engine.py — render a storyboard.json to a broadcast-ready MP4.

Frames are rendered with SupersampledCanvas (2x supersampled, BOX
downsampled at integer scale) and streamed as raw RGB straight into an ffmpeg subprocess —
no intermediate PNGs, no temp frame directories.

Audio is synthesized offline by audio_dsp.build_master_wav (voiceover stems
ducked under a just-intonation pad, SFX on a frame-accurate timeline,
-1 dBFS peak ceiling) and muxed with loudnorm to -14 LUFS TP -1.5
(Spotify/YouTube normalization target).

QC: after encoding, verify_output.verify_mp4() asserts streams,
yuv420p, fps, resolution and A/V duration parity. A failed QC exits 3.
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audio_dsp
import hybrid_compositor
import scene_router
import software_3d_projection
import threejs_bridge
from camera import WorldCamera2D
from canvas import SupersampledCanvas, classify_aspect, layout_zones, rgb
from easings import ease_in_out_cubic
from elements import ElementContext, render_element
from scene_router import CAMERA_3D_DEFAULTS
from storyboard import assign_start_times, total_duration, validate_storyboard

# Return freed heap blocks to the OS. After the first large per-frame buffers
# are freed, glibc raises its mmap threshold and later allocations come from
# the brk heap, which is never trimmed automatically — RSS then grows frame
# over frame until the cgroup ceiling OOM-kills the render. Pair with
# gc.collect() to break canvas<->draw reference cycles (see frame loop).
try:
    _LIBC = ctypes.CDLL("libc.so.6")

    def _malloc_trim() -> None:
        _LIBC.malloc_trim(0)
except OSError:  # non-glibc platform: gc alone still helps

    def _malloc_trim() -> None:
        pass


def build_camera(
    scene_cfg: dict[str, Any], width: int, height: int, seed: int
) -> WorldCamera2D:
    cam = scene_cfg.get("camera") or {}
    orbit_radius_start = float(cam.get("orbit_radius_start", 0.0))
    azimuth_start = float(cam.get("azimuth_start_deg", 0.0))
    return WorldCamera2D(
        width,
        height,
        zoom_start=float(cam.get("zoom_start", 1.0)),
        zoom_end=float(cam.get("zoom_end", 1.0)),
        pan_x=float(cam.get("pan_x", 0.5)),
        pan_y=float(cam.get("pan_y", 0.5)),
        easing=str(cam.get("easing", "ease_out_expo")),
        shake_amplitude_px=float(cam.get("shake_amplitude_px", 0.0)),
        seed=seed,
        mode=str(cam.get("mode", "zoom")),
        pivot_x=(None if cam.get("pivot_x") is None else float(cam["pivot_x"])),
        pivot_y=(None if cam.get("pivot_y") is None else float(cam["pivot_y"])),
        orbit_radius_start=orbit_radius_start,
        orbit_radius_end=(
            None
            if cam.get("orbit_radius_end") is None
            else float(cam["orbit_radius_end"])
        ),
        azimuth_start_deg=azimuth_start,
        azimuth_end_deg=(
            None
            if cam.get("azimuth_end_deg") is None
            else float(cam["azimuth_end_deg"])
        ),
        orbit_easing=(
            None if cam.get("orbit_easing") is None else str(cam["orbit_easing"])
        ),
        elevation_deg=float(cam.get("elevation_deg", 0.0)),
    )


def scene_frames(scene: dict[str, Any], fps: int) -> int:
    return max(1, round(float(scene["duration_sec"]) * fps))


def frame_counts(scenes: list[dict[str, Any]], fps: int) -> list[int]:
    """Bresenham-style cumulative frame quantization for a scene list.

    Per-scene ``round(duration * fps)`` lets each scene's ±0.5-frame error
    accumulate against the audio timeline (built from exact seconds). Instead,
    track the cumulative exact timeline: scene *k* gets
    ``round(T_k * fps) - round(T_{k-1} * fps)`` frames where ``T_k`` is the
    summed exact duration up to scene *k*. Total frames then equal
    ``round(T_total * fps)`` whenever no scene is shorter than half a frame
    (those clamp to the 1-frame floor, like :func:`scene_frames`).
    """
    counts: list[int] = []
    prev_boundary = 0
    acc = 0.0
    for sc in scenes:
        acc += float(sc["duration_sec"])
        boundary = round(acc * fps)
        counts.append(max(1, boundary - prev_boundary))
        prev_boundary = boundary
    return counts


def trauma_at(scene: dict[str, Any], local_time: float, fps: int) -> float:
    """Replay the frame loop's trauma model deterministically for a single instant."""
    events = sorted(
        scene.get("sfx_events") or [], key=lambda ev: float(ev.get("t_sec", 0.0))
    )
    trauma = 0.0
    frame = 1.0 / fps
    t = 0.0
    for ev in events:
        if ev.get("sfx") != "trauma":
            continue
        ev_time = float(ev["t_sec"])
        # decay between the previous trauma timestamp and this event
        while t < min(ev_time, local_time):
            trauma = WorldCamera2D.decay_trauma(trauma, frame)
            t += frame
        if ev_time > local_time:
            break
        trauma = min(1.0, trauma + float(ev.get("intensity", 1.0)))
    while t < local_time:
        trauma = WorldCamera2D.decay_trauma(trauma, frame)
        t += frame
    return trauma


_MANIM_WARNED: set[str] = set()


def _route_scene(scene: dict[str, Any]) -> str:
    """Route a scene to its render backend; never raises."""
    try:
        # scene_router is not resolvable by mypy in this repo config;
        # str() keeps this clean whether route_scene resolves or not
        return str(scene_router.route_scene(scene))
    except ValueError as exc:
        print(
            f"render_engine: warning — {exc}; treating scene as canvas_2d",
            file=sys.stderr,
        )
        return "canvas_2d"


def _warn_manim_once(scene: dict[str, Any]) -> None:
    sid = str(scene.get("scene_id", "?"))
    if sid in _MANIM_WARNED:
        return
    _MANIM_WARNED.add(sid)
    print(
        f"render_engine: WARNING — scene {sid!r}: backend 'manim_math' is not supported; "
        "falling back to canvas_2d rendering (manim deliberately out of scope)",
        file=sys.stderr,
    )


def _spec_route(scene: dict[str, Any]) -> str | None:
    """Return the effective route for a scene_spec scene, or None otherwise."""
    spec = scene.get("scene_spec")
    if not isinstance(spec, dict) or not spec:
        return None
    route = _route_scene(scene)
    if route == "manim_math":
        _warn_manim_once(scene)
        route = "canvas_2d"
    return route


def _blender_adapter_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Map a board ``scene_spec`` to the spec shape ``blender_runner.py`` expects.

    The board schema uses ``camera_3d``/``fstop``/``blender_engine`` while
    blender_runner reads ``camera``/``aperture_fstop``/``engine_pref``. The
    adapted spec is written to the work dir — the board itself is never mutated.
    """
    cam = spec.get("camera_3d") or {}
    return {
        "category": spec.get("category"),
        "engine_pref": spec.get("blender_engine", "AUTO_EEVEE"),
        "transparent_bg": bool(spec.get("transparent_bg", False)),
        "lighting_preset": spec.get("lighting_preset", "cyber_studio_volumetric"),
        "explode_factor": spec.get("explode_factor", 0),
        "boolean_cutaway": bool(spec.get("boolean_cutaway", False)),
        "anchors_3d": spec.get("anchors_3d", []),
        "params": spec.get("params", {}),
        "camera": {
            "focal_length_mm": cam.get(
                "focal_length_mm", CAMERA_3D_DEFAULTS["focal_length_mm"]
            ),
            "aperture_fstop": cam.get("fstop", CAMERA_3D_DEFAULTS["fstop"]),
            "radius_start": cam.get("radius_start", CAMERA_3D_DEFAULTS["radius_start"]),
            "radius_end": cam.get("radius_end", CAMERA_3D_DEFAULTS["radius_end"]),
            "azimuth_start_deg": cam.get(
                "azimuth_start_deg", CAMERA_3D_DEFAULTS["azimuth_start_deg"]
            ),
            "azimuth_end_deg": cam.get(
                "azimuth_end_deg", CAMERA_3D_DEFAULTS["azimuth_end_deg"]
            ),
            "elevation_deg": cam.get(
                "elevation_deg", CAMERA_3D_DEFAULTS["elevation_deg"]
            ),
        },
    }


def _load_blender_tracks(
    tracks_path: Path, spec: dict[str, Any], local_idx: int
) -> list[dict[str, Any]] | None:
    """Read Blender's anchor_tracks.json and merge in label/metric/accent metadata."""
    try:
        payload = json.loads(Path(tracks_path).read_text(encoding="utf-8"))
        frames = payload.get("frames") or []
        if not frames:
            return None
        selection = frames[min(local_idx, len(frames) - 1)]
        entries = selection.get("anchors", []) if isinstance(selection, dict) else []
        meta = {
            str(a.get("anchor_id")): a
            for a in (spec.get("anchors_3d") or [])
            if isinstance(a, dict)
        }
        tracked: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            m = meta.get(str(entry.get("anchor_id")), {})
            tracked.append(
                {
                    **entry,
                    "label": m.get("label", entry.get("anchor_id", "")),
                    "metric": m.get("metric", ""),
                    "accent_hex": m.get("accent_hex", "#38BDF8"),
                }
            )
        return tracked
    except Exception:  # noqa: BLE001 — unusable track data means "no HUD", never an abort
        return None


def _scene_spec_frame(
    scene: dict[str, Any],
    cv: SupersampledCanvas,
    local_idx: int,
    local_t: float,
    blender_dir: Path | None,
) -> list[dict[str, Any]] | None:
    """Paint the 3D pass for a scene_spec scene; return tracked HUD anchors.

    Prefers a pre-rendered Blender plate when ``blender_dir`` holds the frame
    and anchor tracks; otherwise draws the always-available software 3D pass.
    Returns ``None`` when no tracked anchors are available for the HUD.
    """
    spec = scene["scene_spec"]
    if blender_dir is not None:
        frame_path = Path(blender_dir) / f"frame_{local_idx + 1:04d}.png"
        tracks_path = Path(blender_dir) / "anchor_tracks.json"
        if frame_path.is_file() and tracks_path.is_file():
            try:
                with Image.open(frame_path) as im:
                    has_alpha = im.mode == "RGBA"
                    bimg = im.convert("RGBA" if has_alpha else "RGB")
                    bimg = bimg.resize(cv.image.size, Image.Resampling.LANCZOS)
                if bimg.mode == "RGBA":
                    cv.image.paste(bimg, (0, 0), bimg)
                else:
                    cv.image.paste(bimg, (0, 0))
            except Exception as exc:  # noqa: BLE001 — never abort the render for a plate
                print(
                    f"render_engine: warning — blender plate for scene "
                    f"{scene.get('scene_id')!r} failed ({exc}); software 3D fallback",
                    file=sys.stderr,
                )
            else:
                tracks = _load_blender_tracks(tracks_path, spec, local_idx)
                if tracks is None:
                    print(
                        f"render_engine: note — scene {scene.get('scene_id')!r}: "
                        "anchor_tracks.json unusable; HUD overlay skipped"
                    )
                return tracks
    try:
        # software_3d_projection is not resolvable by mypy in this repo config
        return cast(
            "list[dict[str, Any]] | None",
            software_3d_projection.render_3d_scene_and_track(cv, spec, local_t),
        )
    except NotImplementedError:
        # Unimplemented category must propagate: the validator rejects those
        # boards up front, so reaching here is a real bug, not a fallback.
        raise
    except Exception as exc:  # noqa: BLE001 — a broken 3D pass never aborts the render
        print(
            f"render_engine: warning — scene {scene.get('scene_id')!r}: "
            f"software 3D pass failed ({exc}); continuing without the 3D layer",
            file=sys.stderr,
        )
        return None


def _paint_scene_frame(
    scene: dict[str, Any],
    width: int,
    height: int,
    scale: int,
    seed: int,
    local_idx: int,
    fps: int,
    trauma: float,
    base_dir: str | None = None,
    blender_dir: Path | None = None,
    camera: WorldCamera2D | None = None,
    zones: dict[str, tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    """Render one frame of a scene: 3D pass (if any), then elements on top, then fades."""
    n_frames = scene_frames(scene, fps)
    local_t = local_idx / max(1, n_frames - 1)
    local_time = local_idx / fps
    time_sec = float(scene.get("start_sec", 0.0)) + local_time
    spec = (
        scene.get("scene_spec") if isinstance(scene.get("scene_spec"), dict) else None
    )
    zones = zones if zones is not None else layout_zones(width, height)
    scene_camera = (
        None
        if spec
        else (
            camera if camera is not None else build_camera(scene, width, height, seed)
        )
    )

    cv = SupersampledCanvas(
        width,
        height,
        scale=scale,
        camera=scene_camera,
        background="#050811" if spec else _background_color(scene),
    )
    cv.set_frame(local_t, time_sec, trauma=trauma)

    if spec:
        route = _spec_route(scene)
        if route in ("blender_hybrid", "blender_3d", "threejs_hybrid", "threejs_3d"):
            tracks = _scene_spec_frame(scene, cv, local_idx, local_t, blender_dir)
            if route in ("blender_hybrid", "threejs_hybrid"):
                if tracks:
                    prefix = "THREE.JS 3D" if route == "threejs_hybrid" else "3D HYBRID"
                    title = spec.get("hud_title") or (
                        f"{prefix} // {str(spec.get('category', '')).upper()}"
                    )
                    hybrid_compositor.composite_3d_tracked_hud(
                        cv,
                        tracks,
                        title,
                        local_t,
                        aspect_ratio=classify_aspect(width, height),
                    )
                else:
                    print(
                        f"render_engine: note — scene {scene.get('scene_id')!r}: "
                        "no tracked anchors; HUD overlay skipped"
                    )

    ctx = ElementContext(
        width=width,
        height=height,
        t=local_t,
        scene_time=time_sec,
        local_time=local_time,
        words=scene.get("words", []),
        seed=seed,
        trauma=trauma,
        zones=zones,
        base_dir=base_dir,
    )
    for el in scene.get("elements", []):
        render_element(cv, el, ctx)
    frame: Image.Image = cv.final()

    # scene edge fades (blend in RGB space — Pillow ImageDraw has no alpha blend)
    scene_dur = float(scene["duration_sec"])
    fade_in = float(scene.get("fade_in_sec", 0.25))
    fade_out = float(scene.get("fade_out_sec", 0.25))
    fade = 0.0
    if fade_in > 0 and local_time < fade_in:
        u = max(0.0, min(1.0, local_time / fade_in))
        fade = max(fade, 1.0 - ease_in_out_cubic(u))
    if fade_out > 0 and (scene_dur - local_time) < fade_out:
        u = max(0.0, min(1.0, (scene_dur - local_time) / fade_out))
        fade = max(fade, 1.0 - ease_in_out_cubic(u))
    if fade > 0.0:
        fade_rgb = rgb(str(scene.get("fade_color", "#000000")))
        veil = Image.new("RGB", (width, height), fade_rgb)
        frame = Image.blend(frame, veil, min(1.0, fade))
    return frame


def paint_frame(
    scene: dict[str, Any],
    width: int,
    height: int,
    scale: int,
    seed: int,
    local_idx: int,
    fps: int,
    base_dir: str | None = None,
) -> Image.Image:
    """Render exactly one frame of a scene (used by --thumbnails)."""
    trauma = trauma_at(scene, local_idx / fps, fps)
    return _paint_scene_frame(
        scene,
        width,
        height,
        scale,
        seed,
        local_idx,
        fps,
        trauma,
        base_dir=base_dir,
        blender_dir=None,
        camera=build_camera(scene, width, height, seed),
        zones=layout_zones(width, height),
    )


def render_thumbnails(board_path: Path, out_dir: Path, scale: int = 2) -> list[Path]:
    """One representative PNG per scene — lets agents see work before a full render."""
    board = json.loads(board_path.read_text(encoding="utf-8"))
    board = assign_start_times(board)
    fmt = board["format"]
    width, height, fps = int(fmt["width"]), int(fmt["height"]), int(fmt["fps"])
    seed = int(board.get("meta", {}).get("seed", 20261118))
    base_dir = str(board_path.resolve().parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for scene in board["scenes"]:
        n = scene_frames(scene, fps)
        idx = min(n - 1, max(0, round(0.55 * (n - 1))))
        thumb_plate_dir: Path | None = None
        if _spec_route(scene) in ("threejs_hybrid", "threejs_3d"):
            probe = scene_router.probe_threejs_environment()
            if probe.get("available"):
                sid = str(scene["scene_id"])
                t_norm = idx / max(1, n - 1)
                cand_dir = out_dir / f".threejs_thumb_{sid}"
                cand_spec = out_dir / f".threejs_thumb_{sid}_spec.json"
                rendered = threejs_bridge.prerender_threejs_scene(
                    sid,
                    scene["scene_spec"],
                    cand_dir,
                    cand_spec,
                    width,
                    height,
                    fps,
                    1,
                    probe,
                    base_dir=base_dir,
                    frame_t=t_norm,
                )
                if rendered is not None:
                    f1 = rendered / "frame_0001.png"
                    target_f = rendered / f"frame_{idx + 1:04d}.png"
                    if f1.is_file() and f1 != target_f:
                        shutil.copyfile(f1, target_f)
                    thumb_plate_dir = rendered
        if thumb_plate_dir is not None:
            trauma = trauma_at(scene, idx / fps, fps)
            frame = _paint_scene_frame(
                scene,
                width,
                height,
                scale,
                seed,
                idx,
                fps,
                trauma,
                base_dir=base_dir,
                blender_dir=thumb_plate_dir,
                camera=build_camera(scene, width, height, seed),
                zones=layout_zones(width, height),
            )
            shutil.rmtree(thumb_plate_dir, ignore_errors=True)
            (out_dir / f".threejs_thumb_{scene['scene_id']}_spec.json").unlink(
                missing_ok=True
            )
        else:
            frame = paint_frame(
                scene, width, height, scale, seed, idx, fps, base_dir=base_dir
            )
        out = out_dir / f"{scene['scene_id']}.png"
        frame.save(out)
        written.append(out)
    return written


def estimate(board: dict[str, Any]) -> dict[str, Any]:
    fmt = board["format"]
    fps = int(fmt["fps"])
    width, height = int(fmt["width"]), int(fmt["height"])
    total_frames = sum(frame_counts(board["scenes"], fps))
    duration = total_duration(board)
    spec_routes = [
        {
            "scene_id": sc.get("scene_id"),
            "backend": sc.get("backend", "auto"),
            "route": _spec_route(sc),
        }
        for sc in board["scenes"]
        if sc.get("scene_spec")
    ]
    report = {
        "scenes": len(board["scenes"]),
        "duration_sec": round(duration, 2),
        "resolution": f"{width}x{height}",
        "fps": fps,
        "total_frames": total_frames,
        "audio_mix_seconds_estimate": round(duration * 0.22, 1),
        "approximate_render_note": (
            "~0.1-0.15s per frame on a 4-core CPU at 720p 2x supersampled; "
            "1080p costs ~2x; 60fps doubles frame count"
        ),
    }
    if spec_routes:
        report["scene_spec_scenes"] = spec_routes
        report["scene_spec_note"] = (
            "scene_spec scenes render via the software 3D pass; when Blender (>=3.6) "
            "or Three.js (Node >=22 + Chromium + local three.module.js) is available, "
            "blender_* / threejs_* scenes are pre-rendered into <work_dir>/ and "
            "composited under the HUD, with automatic software fallback on any failure"
        )
    return report


def _prerender_blender_plates(
    board: dict[str, Any],
    work_dir: Path,
    width: int,
    height: int,
    fps: int,
    per_scene_frames: list[int],
) -> dict[str, Path]:
    """Pre-render blender_hybrid/blender_3d scene_spec scenes to per-scene PNG plates.

    Returns ``{scene_id: plate_dir}``. Any failure (no binary, non-zero exit,
    timeout, adapter error) leaves the scene out of the map — the frame painter
    falls back to the software 3D pass. Never raises and never aborts the render.
    """
    wanted = [
        (scene, n)
        for scene, n in zip(board["scenes"], per_scene_frames)
        if _spec_route(scene) in ("blender_hybrid", "blender_3d")
    ]
    if not wanted:
        return {}
    probe = scene_router.probe_blender_environment()
    if not probe.get("available"):
        print(
            "render_engine: blender binary not available; "
            "scene_spec scenes will use the software 3D renderer"
        )
        return {}
    binary = str(probe.get("binary") or "blender")
    plates: dict[str, Path] = {}
    for scene, n_frames in wanted:
        sid = str(scene["scene_id"])
        plate_dir = work_dir / f"blender_{sid}"
        spec_path = work_dir / f"blender_{sid}_spec.json"
        try:
            spec_path.write_text(
                json.dumps(_blender_adapter_spec(scene["scene_spec"])),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    binary,
                    "-b",
                    "-P",
                    str(SCRIPT_DIR / "blender_runner.py"),
                    "--",
                    "--spec",
                    str(spec_path),
                    "--out-dir",
                    str(plate_dir),
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                    "--fps",
                    str(fps),
                    "--frames",
                    str(n_frames),
                ],
                check=False,
                timeout=600,
                capture_output=True,
            )
        except Exception as exc:  # noqa: BLE001 — timeout/OSError → software fallback
            print(
                f"render_engine: warning — blender pre-render for scene {sid!r} "
                f"errored ({exc}); software fallback",
                file=sys.stderr,
            )
            continue
        if result.returncode != 0:
            tail = (result.stderr or b"").decode(errors="replace")[-800:]
            print(
                f"render_engine: warning — blender pre-render for scene {sid!r} "
                f"exited {result.returncode}; software fallback\n{tail}",
                file=sys.stderr,
            )
            continue
        plates[sid] = plate_dir
        print(
            f"render_engine: scene {sid!r}: blender plate pre-rendered to {plate_dir} "
            f"({n_frames} frames)"
        )
    return plates


def _prerender_threejs_plates(
    board: dict[str, Any],
    work_dir: Path,
    width: int,
    height: int,
    fps: int,
    per_scene_frames: list[int],
    *,
    base_dir: Path | str | None = None,
    reuse_plates: bool = False,
) -> dict[str, Path]:
    """Pre-render threejs_hybrid/threejs_3d scene_spec scenes to per-scene PNG plates.

    Returns ``{scene_id: plate_dir}``. Any failure (missing Node/Chromium/three,
    non-zero exit, timeout) leaves the scene out of the map — the frame painter
    falls back to the software 3D pass. Never raises and never aborts the render.
    """
    wanted = [
        (scene, n)
        for scene, n in zip(board["scenes"], per_scene_frames)
        if _spec_route(scene) in ("threejs_hybrid", "threejs_3d")
    ]
    if not wanted:
        return {}
    probe = scene_router.probe_threejs_environment()
    if not probe.get("available"):
        reason = probe.get("reason") or "runtime unavailable"
        print(
            f"render_engine: threejs runtime not available ({reason}); "
            "scene_spec scenes will use the software 3D renderer"
        )
        return {}
    plates: dict[str, Path] = {}
    for scene, n_frames in wanted:
        sid = str(scene["scene_id"])
        plate_dir = work_dir / f"threejs_{sid}"
        spec_path = work_dir / f"threejs_{sid}_spec.json"
        if (
            reuse_plates
            and (plate_dir / "anchor_tracks.json").is_file()
            and (plate_dir / f"frame_{n_frames:04d}.png").is_file()
        ):
            plates[sid] = plate_dir
            print(
                f"render_engine: scene {sid!r}: reusing cached threejs plate at "
                f"{plate_dir} ({n_frames} frames)"
            )
            continue
        rendered = threejs_bridge.prerender_threejs_scene(
            sid,
            scene["scene_spec"],
            plate_dir,
            spec_path,
            width,
            height,
            fps,
            n_frames,
            probe,
            base_dir=base_dir,
        )
        if rendered is not None:
            plates[sid] = rendered
            print(
                f"render_engine: scene {sid!r}: threejs plate pre-rendered to "
                f"{rendered} ({n_frames} frames)"
            )
    return plates


def render(args: argparse.Namespace) -> int:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("render_engine: ffmpeg and ffprobe are required on PATH", file=sys.stderr)
        return 2

    board_path = args.storyboard.resolve()
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"render_engine: cannot read storyboard: {exc}", file=sys.stderr)
        return 2

    errors = validate_storyboard(board)
    if errors:
        for err in errors:
            print(f"render_engine: {err}", file=sys.stderr)
        return 2

    board = assign_start_times(board)
    fmt = board["format"]
    width, height, fps = int(fmt["width"]), int(fmt["height"]), int(fmt["fps"])
    seed = int(board.get("meta", {}).get("seed", 20261118))
    audio_cfg = board.get("audio") or {}
    pad = bool(audio_cfg.get("pad", True))
    pad_level = float(audio_cfg.get("pad_level", 0.055))
    duck_depth = float(audio_cfg.get("duck_depth", 0.72))
    pad_style = str(audio_cfg.get("pad_style", "drone"))

    # resolve VO paths relative to the storyboard location
    for scene in board["scenes"]:
        vo = scene.get("vo_wav")
        if vo and not Path(vo).is_absolute():
            scene["vo_wav"] = str((board_path.parent / vo).resolve())

    duration = total_duration(board)
    if duration > args.max_seconds:
        print(
            f"render_engine: storyboard is {duration:.1f}s > --max-seconds {args.max_seconds}; "
            f"refusing to render (raise the limit explicitly if intentional)",
            file=sys.stderr,
        )
        return 2

    quality = args.quality
    scale = 2  # pre-raster supersampling — do not reduce; it defeats anti-aliasing
    if quality == "draft":
        crf, preset = "26", "veryfast"
    else:
        crf, preset = "18", "medium"

    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- audio master ------------------------------------------------------
    work_dir = (
        Path(args.work_dir)
        if args.work_dir
        else out_path.parent / f"{out_path.stem}_work"
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    master_wav = work_dir / "master.wav"
    build_scenes = [dict(sc) for sc in board["scenes"]]
    t0 = time.time()
    audio_dsp.build_master_wav(
        build_scenes,
        master_wav,
        pad=pad,
        pad_level=pad_level,
        duck_depth=duck_depth,
        pad_style=pad_style,
    )
    t_audio = time.time() - t0

    # ---- ffmpeg video pipe ---------------------------------------------------
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-i",
        str(master_wav),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        crf,
        "-profile:v",
        "high",
        "-level",
        "4.2",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-af",
        "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    frame_idx = 0
    per_scene_frames = frame_counts(board["scenes"], fps)
    total_frames = sum(per_scene_frames)
    plate_dirs = {
        **_prerender_blender_plates(
            board, work_dir, width, height, fps, per_scene_frames
        ),
        **_prerender_threejs_plates(
            board,
            work_dir,
            width,
            height,
            fps,
            per_scene_frames,
            base_dir=board_path.parent,
            reuse_plates=bool(getattr(args, "reuse_plates", False)),
        ),
    }
    t0 = time.time()
    prev_scene_tail: Image.Image | None = None
    try:
        for scene, n_frames in zip(board["scenes"], per_scene_frames):
            trauma = 0.0
            scene_camera = build_camera(scene, width, height, seed)
            scene_zones = layout_zones(width, height)
            sfx_events = sorted(
                scene.get("sfx_events") or [],
                key=lambda ev: float(ev.get("t_sec", 0.0)),
            )
            fired: set[int] = set()
            transition_mode = str(scene.get("transition", "cut")).lower()
            transition_sec = (
                float(scene.get("transition_sec", 0.75))
                if transition_mode == "dissolve"
                else 0.0
            )
            last_scene_frame: Image.Image | None = None

            for local_idx in range(n_frames):
                local_time = local_idx / fps

                # fire camera-trauma / audio events due on this frame
                for k, ev in enumerate(sfx_events):
                    if k not in fired and local_time >= float(ev.get("t_sec", 0.0)):
                        fired.add(k)
                        if ev.get("sfx") == "trauma":
                            trauma = min(1.0, trauma + float(ev.get("intensity", 1.0)))

                frame = _paint_scene_frame(
                    scene,
                    width,
                    height,
                    scale,
                    seed,
                    local_idx,
                    fps,
                    trauma,
                    base_dir=str(board_path.parent),
                    blender_dir=plate_dirs.get(str(scene.get("scene_id"))),
                    camera=scene_camera,
                    zones=scene_zones,
                )

                if (
                    prev_scene_tail is not None
                    and transition_sec > 0.0
                    and local_time < transition_sec
                ):
                    alpha = ease_in_out_cubic(
                        max(0.0, min(1.0, local_time / transition_sec))
                    )
                    frame = Image.blend(prev_scene_tail, frame, alpha)

                if local_idx == n_frames - 1:
                    last_scene_frame = frame.copy()

                assert proc.stdin is not None
                proc.stdin.write(frame.tobytes())
                frame_idx += 1
                if frame_idx % 15 == 0:
                    # Break canvas<->draw reference cycles and hand freed heap
                    # back to the OS; keeps RSS flat instead of ~25 MB/frame.
                    del frame
                    gc.collect()
                    _malloc_trim()
                trauma = WorldCamera2D.decay_trauma(trauma, 1.0 / fps)
                if frame_idx % max(1, fps * 2) == 0 or frame_idx == total_frames:
                    elapsed = time.time() - t0
                    rate = frame_idx / max(elapsed, 1e-6)
                    print(
                        f"render_engine: {frame_idx}/{total_frames} frames "
                        f"({rate:.1f} fps, eta {(total_frames - frame_idx) / max(rate, 1e-6):.0f}s)",
                        flush=True,
                    )
            prev_scene_tail = last_scene_frame
    except BrokenPipeError:
        proc.wait()
        stderr_tail = (
            (proc.stderr.read() or b"").decode(errors="replace")[-2000:]
            if proc.stderr
            else ""
        )
        print(f"render_engine: ffmpeg died mid-render:\n{stderr_tail}", file=sys.stderr)
        return 4

    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        stderr_tail = (
            (proc.stderr.read() or b"").decode(errors="replace")[-2000:]
            if proc.stderr
            else ""
        )
        print(
            f"render_engine: ffmpeg exited {proc.returncode}:\n{stderr_tail}",
            file=sys.stderr,
        )
        return 4

    t_render = time.time() - t0
    print(
        f"render_engine: encoded {out_path.name} in {t_render:.1f}s "
        f"(audio {t_audio:.1f}s, {frame_idx} frames @ {width}x{height} {fps}fps, crf {crf})"
    )

    # ---- QC ------------------------------------------------------------------
    if not args.no_verify:
        import verify_output

        report = verify_output.verify_mp4(
            out_path,
            expected_width=width,
            expected_height=height,
            expected_fps=fps,
            expected_duration=duration,
            storyboard=board_path,
        )
        print(json.dumps(report, indent=2))
        if not report["ok"]:
            print("render_engine: QC FAILED — see report above", file=sys.stderr)
            return 3
    return 0


def _background_color(scene: dict[str, Any]) -> str:
    for el in scene.get("elements", []):
        if el.get("type") == "background":
            return str(el.get("color", "#000000"))
    return "#000000"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a surgical-media storyboard to MP4."
    )
    parser.add_argument("--storyboard", type=Path, default=None)
    parser.add_argument("--output", default=Path("surgical_media_out.mp4"), type=Path)
    parser.add_argument("--quality", choices=["draft", "final"], default="final")
    parser.add_argument(
        "--work-dir",
        default=None,
        type=Path,
        help="Scratch dir for the audio master (default: <out>_work/)",
    )
    parser.add_argument("--max-seconds", type=float, default=600.0)
    parser.add_argument(
        "--no-verify", action="store_true", help="Skip the ffprobe QC pass"
    )
    parser.add_argument(
        "--estimate",
        action="store_true",
        help="Print frame count / audio cost and exit without rendering",
    )
    parser.add_argument(
        "--thumbnails",
        type=Path,
        default=None,
        metavar="DIR",
        help="Write one representative PNG per scene to DIR and exit",
    )
    parser.add_argument(
        "--reuse-plates",
        action="store_true",
        help="Reuse complete cached 3D plates already present in --work-dir",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Render the bundled three-archetype showcase instead of --storyboard",
    )
    args = parser.parse_args()

    if args.demo:
        demo = SCRIPT_DIR.parent / "examples" / "tri_archetype_storyboard.json"
        if not demo.is_file():
            print(f"render_engine: demo storyboard missing at {demo}", file=sys.stderr)
            return 2
        args.storyboard = demo
        if args.output.name == "surgical_media_out.mp4":
            args.output = Path("demo_showcase.mp4")
    if args.storyboard is None:
        parser.error("--storyboard is required unless --demo is passed")

    if args.estimate:
        try:
            board = json.loads(args.storyboard.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"render_engine: cannot read storyboard: {exc}", file=sys.stderr)
            return 2
        errors = validate_storyboard(board)
        if errors:
            for err in errors:
                print(f"render_engine: {err}", file=sys.stderr)
            return 2
        print(json.dumps(estimate(board), indent=2))
        return 0

    if args.thumbnails is not None:
        written = render_thumbnails(args.storyboard, args.thumbnails)
        for path in written:
            print(f"thumbnail: {path}")
        return 0

    return render(args)


if __name__ == "__main__":
    raise SystemExit(main())
