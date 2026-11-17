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
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audio_dsp
from camera import WorldCamera2D
from canvas import SupersampledCanvas, layout_zones
from elements import ElementContext, render_element
from storyboard import assign_start_times, total_duration, validate_storyboard


def build_camera(scene_cfg: dict, width: int, height: int, seed: int) -> WorldCamera2D:
    cam = scene_cfg.get("camera") or {}
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
    )


def scene_frames(scene: dict, fps: int) -> int:
    return max(1, round(float(scene["duration_sec"]) * fps))


def trauma_at(scene: dict, local_time: float, fps: int) -> float:
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


def paint_frame(
    scene: dict,
    width: int,
    height: int,
    scale: int,
    seed: int,
    local_idx: int,
    fps: int,
    base_dir: str | None = None,
):
    """Render exactly one frame of a scene (used by --thumbnails)."""
    n_frames = scene_frames(scene, fps)
    local_t = local_idx / max(1, n_frames - 1)
    local_time = local_idx / fps
    time_sec = float(scene.get("start_sec", 0.0)) + local_time
    scene_dur = float(scene["duration_sec"])
    camera = build_camera(scene, width, height, seed)
    zones = layout_zones(width, height)
    trauma = trauma_at(scene, local_time, fps)

    cv = SupersampledCanvas(
        width, height, scale=scale, camera=camera, background=_background_color(scene)
    )
    cv.set_frame(local_t, time_sec, trauma=trauma)
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
    for el in scene["elements"]:
        render_element(cv, el, ctx)
    frame = cv.final()

    fade_in = float(scene.get("fade_in_sec", 0.25))
    fade_out = float(scene.get("fade_out_sec", 0.25))
    black = Image.new("RGB", (width, height), (0, 0, 0))
    fade = 0.0
    if fade_in > 0 and local_time < fade_in:
        fade = max(fade, 1.0 - local_time / fade_in)
    if fade_out > 0 and (scene_dur - local_time) < fade_out:
        fade = max(fade, 1.0 - (scene_dur - local_time) / fade_out)
    if fade > 0.0:
        frame = Image.blend(frame, black, min(1.0, fade))
    return frame


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
        frame = paint_frame(
            scene, width, height, scale, seed, idx, fps, base_dir=base_dir
        )
        out = out_dir / f"{scene['scene_id']}.png"
        frame.save(out)
        written.append(out)
    return written


def estimate(board: dict) -> dict:
    fmt = board["format"]
    fps = int(fmt["fps"])
    width, height = int(fmt["width"]), int(fmt["height"])
    total_frames = sum(scene_frames(sc, fps) for sc in board["scenes"])
    duration = total_duration(board)
    return {
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
        build_scenes, master_wav, pad=pad, pad_level=pad_level, duck_depth=duck_depth
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
    total_frames = sum(scene_frames(sc, fps) for sc in board["scenes"])
    t0 = time.time()
    black = Image.new("RGB", (width, height), (0, 0, 0))
    try:
        for scene in board["scenes"]:
            scene_dur = float(scene["duration_sec"])
            n_frames = scene_frames(scene, fps)
            camera = build_camera(scene, width, height, seed)
            zones = layout_zones(width, height)
            trauma = 0.0
            fade_in = float(scene.get("fade_in_sec", 0.25))
            fade_out = float(scene.get("fade_out_sec", 0.25))
            sfx_events = sorted(
                scene.get("sfx_events") or [],
                key=lambda ev: float(ev.get("t_sec", 0.0)),
            )
            fired: set[int] = set()

            for local_idx in range(n_frames):
                local_t = local_idx / max(1, n_frames - 1)
                local_time = local_idx / fps
                time_sec = float(scene.get("start_sec", 0.0)) + local_time

                # fire camera-trauma / audio events due on this frame
                for k, ev in enumerate(sfx_events):
                    if k not in fired and local_time >= float(ev.get("t_sec", 0.0)):
                        fired.add(k)
                        if ev.get("sfx") == "trauma":
                            trauma = min(1.0, trauma + float(ev.get("intensity", 1.0)))

                cv = SupersampledCanvas(
                    width,
                    height,
                    scale=scale,
                    camera=camera,
                    background=_background_color(scene),
                )
                cv.set_frame(local_t, time_sec, trauma=trauma)
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
                    base_dir=str(board_path.parent),
                )
                for el in scene["elements"]:
                    render_element(cv, el, ctx)
                frame = cv.final()

                # scene edge fades (blend in RGB space — Pillow ImageDraw has no alpha blend)
                fade = 0.0
                if fade_in > 0 and local_time < fade_in:
                    fade = max(fade, 1.0 - local_time / fade_in)
                if fade_out > 0 and (scene_dur - local_time) < fade_out:
                    fade = max(fade, 1.0 - (scene_dur - local_time) / fade_out)
                if fade > 0.0:
                    frame = Image.blend(frame, black, min(1.0, fade))

                assert proc.stdin is not None
                proc.stdin.write(frame.tobytes())
                frame_idx += 1
                trauma = WorldCamera2D.decay_trauma(trauma, 1.0 / fps)
                if frame_idx % max(1, fps * 2) == 0 or frame_idx == total_frames:
                    elapsed = time.time() - t0
                    rate = frame_idx / max(elapsed, 1e-6)
                    print(
                        f"render_engine: {frame_idx}/{total_frames} frames "
                        f"({rate:.1f} fps, eta {(total_frames - frame_idx) / max(rate, 1e-6):.0f}s)",
                        flush=True,
                    )
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


def _background_color(scene: dict) -> str:
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
