#!/usr/bin/env python3
"""qc_gate.py — hard pre-delivery QC gate.

Layers measured loudness (EBU R128), dead-air detection, and safe-zone audit
overlays on top of :mod:`verify_output`'s ffprobe checks. This module never
reimplements codec/stream validation — that stays in ``verify_output``.

All external work goes through list-form ``subprocess.run`` with a timeout and
``DEVNULL`` stdin. Missing ffmpeg/ffprobe degrades to a failed check with a
clear detail instead of a traceback, so the gate can never silently pass.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import canvas
import verify_output
from PIL import Image, ImageDraw, ImageFont

FORMAT_SIZES: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1440, 1800),
}

# Canonical 9:16 safe rectangles at the 1080x1920 reference design size.
ORGANIC_RECT_9_16: tuple[int, int, int, int] = (60, 180, 930, 1540)
STRICT_RECT_9_16: tuple[int, int, int, int] = (65, 288, 888, 1248)
REFERENCE_W, REFERENCE_H = 1080, 1920

MASK_AMBER: tuple[int, int, int] = (255, 180, 0)
MASK_RED: tuple[int, int, int] = (255, 48, 48)
MASK_ALPHA = 64  # ~25% — transparent enough to read the frame underneath

TARGET_INTEGRATED_LUFS = -14.0
SUBPROCESS_TIMEOUT = 300

PLATFORM_CAPS_MB: dict[str, int] = {
    "tiktok_android": 72,
    "tiktok_ios": 287,
    "tiktok_web": 4096,
    "reels": 4096,
    "youtube": 256 * 1024,
}

_I_RE = re.compile(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", re.IGNORECASE)
_PEAK_RE = re.compile(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", re.IGNORECASE)


def loudness_from_ffmpeg(stderr: str) -> dict[str, float]:
    """Extract final EBU R128 integrated loudness and true peak from stderr.

    The summary is printed last, so the *last* numeric match wins; this skips
    the per-frame ``I: -inf LUFS`` / ``Peak: -inf dBFS`` progress lines. The
    returned dict may be empty (or hold only one key) when ffmpeg's output is
    truncated — callers turn that into a failed check, never a crash.
    """
    out: dict[str, float] = {}
    integrated = [float(m) for m in _I_RE.findall(stderr)]
    if integrated:
        out["integrated_lufs"] = integrated[-1]
    peaks = [float(m) for m in _PEAK_RE.findall(stderr)]
    if peaks:
        out["true_peak_dbtp"] = peaks[-1]
    return out


def safe_rect_for(
    format_name: str, preset: str, width: int, height: int
) -> tuple[int, int, int, int]:
    """Return the safe rectangle for a format/preset at the given pixel size.

    9:16 uses the reference coordinates scaled to ``width`` x ``height``.
    Every other format derives its base from :data:`canvas.SAFE_ZONES` (via
    ``canvas.safe_rect``); ``strict`` additionally insets that base by 5%.
    """
    if format_name == "9:16":
        sx, sy = width / REFERENCE_W, height / REFERENCE_H
        x0, y0, x1, y1 = ORGANIC_RECT_9_16 if preset == "organic" else STRICT_RECT_9_16
        return (
            round(x0 * sx),
            round(y0 * sy),
            round(x1 * sx),
            round(y1 * sy),
        )

    bx0, by0, bx1, by1 = canvas.safe_rect(width, height)
    if preset == "organic":
        return (bx0, by0, bx1, by1)
    inset_x = round((bx1 - bx0) * 0.05)
    inset_y = round((by1 - by0) * 0.05)
    return (bx0 + inset_x, by0 + inset_y, bx1 - inset_x, by1 - inset_y)


def _complement_rects(
    box: tuple[int, int, int, int], inner: tuple[int, int, int, int]
) -> list[tuple[int, int, int, int]]:
    """Four rectangles covering ``box`` minus ``inner`` (inner within box)."""
    bx0, by0, bx1, by1 = box
    ix0, iy0, ix1, iy1 = inner
    candidates = [
        (bx0, by0, bx1, min(by1, iy0)),
        (bx0, max(by0, iy1), bx1, by1),
        (bx0, max(by0, iy0), min(bx1, ix0), min(by1, iy1)),
        (max(bx0, ix1), max(by0, iy0), bx1, min(by1, iy1)),
    ]
    return [r for r in candidates if r[2] > r[0] and r[3] > r[1]]


def draw_masks(
    image: Image.Image,
    organic: tuple[int, int, int, int],
    strict: tuple[int, int, int, int],
) -> Image.Image:
    """Overlay two translucent audit bands on a copy of ``image``.

    Amber marks the area *outside* the organic safe rectangle; red marks the
    tighter ring between the organic and strict rectangles. Both bands stay
    outside the strict rectangle, so the most conservative safe zone is never
    obscured. Pillow's ImageDraw cannot alpha-blend, so each band is drawn on
    its own RGBA layer and composited before conversion back to RGB.
    """
    width, height = image.size
    base = image.convert("RGBA")

    amber_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    amber_draw = ImageDraw.Draw(amber_layer)
    for rect in _complement_rects((0, 0, width, height), organic):
        amber_draw.rectangle(rect, fill=(*MASK_AMBER, MASK_ALPHA))

    red_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    red_draw = ImageDraw.Draw(red_layer)
    for rect in _complement_rects(organic, strict):
        red_draw.rectangle(rect, fill=(*MASK_RED, MASK_ALPHA))

    out = Image.alpha_composite(Image.alpha_composite(base, amber_layer), red_layer)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    ImageDraw.Draw(out).text(
        (8, 8),
        "AMBER: outside ORGANIC safe zone | RED: outside STRICT safe zone",
        fill=(255, 255, 255, 255),
        font=font,
    )
    return out.convert("RGB")


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Single safe ffmpeg/ffprobe invocation boundary."""
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        check=False,
    )


def _duration_of(probe: dict[str, Any]) -> float | None:
    fmt = probe.get("format") or {}
    candidates: list[Any] = [fmt.get("duration")]
    for stream in probe.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            candidates.append(stream.get("duration"))
    for candidate in candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _frame_times(duration: float) -> list[tuple[str, float]]:
    return [
        ("frame_1", 0.0),
        ("midpoint", duration / 2.0),
        ("outro", max(0.0, duration - 0.5)),
    ]


def _credits_asset_names(credits_json: Path) -> tuple[list[str], str | None]:
    try:
        data = json.loads(credits_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"credits.json unreadable: {exc}"
    entries = data.get("assets", []) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return [], "credits.json has no asset list"
    names: list[str] = [
        Path(str(entry.get("file", ""))).name
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("file", "")).strip()
    ]
    return names, None


def run_gate(
    video: str | Path,
    format_name: str,
    preset: str = "strict",
    frames_dir: str | Path | None = None,
    credits: str | Path | None = None,
    json_path: str | Path | None = None,
    tol_lufs: float = 1.0,
    max_peak: float = -1.0,
    max_silence: float = 0.6,
    expect_width: int | None = None,
    expect_height: int | None = None,
) -> dict[str, Any]:
    """Run every QC stage and return the full JSON-serialisable report."""
    video_path = Path(video)
    report: dict[str, Any] = {
        "video": str(video_path),
        "format": format_name,
        "preset": preset,
        "checks": [],
        "ok": True,
        "loudness": {"integrated_lufs": None, "true_peak_dbtp": None},
        "silences": [],
        "frames": [],
    }

    def add_check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})

    width, height = FORMAT_SIZES.get(format_name, FORMAT_SIZES["9:16"])
    # CI renders the 16:9 demo at 1280x720 rather than the 1920x1080 platform
    # master. Explicit overrides keep the dimension checks strict while allowing
    # that smaller smoke render through the same gate.
    if expect_width is not None:
        width = expect_width
    if expect_height is not None:
        height = expect_height
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ffprobe_ok = shutil.which("ffprobe") is not None

    # 1. Delegate codec/stream validation; read fps from ffprobe for the gate.
    probe: dict[str, Any] = {}
    expected_fps: float | None = None
    if ffprobe_ok:
        try:
            probe = verify_output._ffprobe_json(video_path)
            video_stream = next(
                s
                for s in probe.get("streams", [])
                if isinstance(s, dict) and s.get("codec_type") == "video"
            )
            fps = verify_output._fps_of(video_stream)
            if fps > 0:
                expected_fps = fps
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            StopIteration,
            ValueError,
            TypeError,
        ):
            probe = {}
    try:
        verify_report = verify_output.verify_mp4(
            video_path,
            expected_width=width,
            expected_height=height,
            expected_fps=expected_fps,
        )
    except (
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:  # never let a helper crash the gate
        add_check("verify_output_ran", False, f"verify_output raised: {exc}")
        verify_report = {"checks": [], "ok": False, "duration_sec": None}
    report["checks"].extend(verify_report["checks"])

    duration = _duration_of(probe)
    if duration is None:
        try:
            duration = float(verify_report.get("duration_sec"))
        except (TypeError, ValueError):
            duration = 0.0

    # 2. EBU R128 integrated loudness and true peak.
    loudness: dict[str, float] = {}
    loudness_error: str | None = None
    if ffmpeg_ok:
        try:
            proc = _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostats",
                    "-i",
                    str(video_path),
                    "-filter_complex",
                    "ebur128=peak=true",
                    "-f",
                    "null",
                    "-",
                ]
            )
            loudness = loudness_from_ffmpeg(proc.stderr)
        except (OSError, subprocess.SubprocessError) as exc:
            loudness_error = str(exc)
    integrated = loudness.get("integrated_lufs")
    if integrated is None:
        if loudness_error:
            detail = f"EBU R128 analysis failed: {loudness_error}"
        elif not ffmpeg_ok:
            detail = "ffmpeg not found on PATH; EBU R128 loudness unavailable"
        else:
            detail = "no integrated loudness value parsed from ffmpeg stderr"
        add_check("loudness_integrated", False, detail)
    else:
        add_check(
            "loudness_integrated",
            abs(integrated - TARGET_INTEGRATED_LUFS) <= tol_lufs,
            f"I={integrated:.1f} LUFS "
            f"(target {TARGET_INTEGRATED_LUFS:.1f} +/- {tol_lufs:.1f})",
        )
    peak = loudness.get("true_peak_dbtp")
    if peak is None:
        if loudness_error:
            detail = f"EBU R128 analysis failed: {loudness_error}"
        elif not ffmpeg_ok:
            detail = "ffmpeg not found on PATH; true-peak measurement unavailable"
        else:
            detail = "no true-peak value parsed from ffmpeg stderr"
        add_check("loudness_true_peak", False, detail)
    else:
        add_check(
            "loudness_true_peak",
            peak <= max_peak,
            f"Peak={peak:.1f} dBFS (max {max_peak:.1f})",
        )
    report["loudness"] = {
        "integrated_lufs": loudness.get("integrated_lufs"),
        "true_peak_dbtp": loudness.get("true_peak_dbtp"),
    }

    # 3. Dead air — distinct from verify_output's global silence-coverage net.
    silences: list[dict[str, float]] = []
    if not ffmpeg_ok:
        add_check(
            "no_dead_air",
            False,
            "ffmpeg not found on PATH; dead-air analysis unavailable",
        )
    else:
        try:
            proc = _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostats",
                    "-i",
                    str(video_path),
                    "-af",
                    (
                        f"silencedetect=noise={verify_output.SILENCE_NOISE_DB}dB"
                        f":d={max_silence}"
                    ),
                    "-f",
                    "null",
                    "-",
                ]
            )
            intervals = verify_output._parse_silencedetect(proc.stderr, duration)
            silences = [
                {"start": start, "end": end, "duration": end - start}
                for start, end in intervals
            ]
            limit = max_silence + 0.01
            too_long = [iv for iv in silences if iv["duration"] > limit]
            add_check(
                "no_dead_air",
                not too_long,
                f"{len(too_long)} silence(s) longer than {limit:.2f}s"
                if too_long
                else f"no silence longer than {limit:.2f}s",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            add_check("no_dead_air", False, f"silencedetect failed: {exc}")
    report["silences"] = silences

    # 4. Safe-zone audit frames (two translucent bands + legend).
    frames: list[str] = []
    if frames_dir is not None:
        directory = Path(frames_dir)
        if not ffmpeg_ok:
            add_check(
                "safe_zone_overlays_written",
                False,
                "ffmpeg not found on PATH; audit frames skipped",
            )
        else:
            directory.mkdir(parents=True, exist_ok=True)
            organic = safe_rect_for(format_name, "organic", width, height)
            strict = safe_rect_for(format_name, "strict", width, height)
            for label, t in _frame_times(duration):
                raw = directory / f"{label}_raw.png"
                try:
                    _run(
                        [
                            "ffmpeg",
                            "-hide_banner",
                            "-nostats",
                            "-y",
                            "-ss",
                            f"{t:.3f}",
                            "-i",
                            str(video_path),
                            "-frames:v",
                            "1",
                            str(raw),
                        ]
                    )
                    if not raw.is_file():
                        continue
                    with Image.open(raw) as frame:
                        audited = draw_masks(frame.convert("RGB"), organic, strict)
                    audit_png = directory / f"{label}_audit.png"
                    audited.save(audit_png)
                    frames.append(str(audit_png))
                except (OSError, subprocess.SubprocessError, ValueError) as exc:
                    add_check("safe_zone_extraction", False, f"{label}: {exc}")
                finally:
                    if raw.exists():
                        raw.unlink()
            complete = len(frames) == 3
            add_check(
                "safe_zone_overlays_written",
                complete,
                ", ".join(frames)
                if complete
                else f"only {len(frames)}/3 audit frames written",
            )
    report["frames"] = frames

    # 5. Credits present and every credited asset actually named.
    if credits is not None:
        credits_path = Path(credits)
        exists = credits_path.is_file()
        add_check("credits_file_exists", exists, str(credits_path))
        if exists:
            text = credits_path.read_text(encoding="utf-8", errors="replace")
            add_check(
                "credits_nonempty",
                bool(text.strip()),
                f"{len(text.strip())} character(s)",
            )
            sibling = credits_path.with_name("credits.json")
            if sibling.is_file():
                names, err = _credits_asset_names(sibling)
                if err is not None:
                    add_check("credits_assets_listed", False, err)
                else:
                    missing = [name for name in names if name not in text]
                    add_check(
                        "credits_assets_listed",
                        not missing,
                        f"missing from credits.md: {', '.join(missing)}"
                        if missing
                        else f"all {len(names)} asset file(s) credited",
                    )

    # 6. File size — informational; there is deliberately no --platform flag.
    raw_size: Any = None
    if probe:
        raw_size = (probe.get("format") or {}).get("size")
    try:
        size_bytes = (
            int(raw_size) if raw_size is not None else video_path.stat().st_size
        )
    except (OSError, TypeError, ValueError):
        size_bytes = 0
    caps = ", ".join(f"{name} {mb} MB" for name, mb in PLATFORM_CAPS_MB.items())
    add_check(
        "file_size_reported",
        True,
        f"{size_bytes / 1_000_000:.1f} MB (caps: {caps}) "
        "— informational; platform caps are not enforced",
    )

    report["ok"] = all(check["ok"] for check in report["checks"])
    if json_path is not None:
        import os
        import tempfile

        out_json = Path(json_path)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=out_json.parent,
            prefix=f".{out_json.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp_json = Path(fh.name)
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_json, out_json)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hard pre-delivery QC gate.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument(
        "--format", required=True, choices=("9:16", "16:9", "1:1", "4:5")
    )
    parser.add_argument("--preset", choices=("organic", "strict"), default="strict")
    parser.add_argument("--frames-dir", type=Path, default=None)
    parser.add_argument("--credits", type=Path, default=None)
    parser.add_argument("--json", dest="json_path", type=Path, default=None)
    parser.add_argument("--tol-lufs", type=float, default=1.0)
    parser.add_argument("--max-peak", type=float, default=-1.0)
    parser.add_argument("--max-silence", type=float, default=0.6)
    parser.add_argument("--expect-width", type=int, default=None)
    parser.add_argument("--expect-height", type=int, default=None)
    args = parser.parse_args(argv)

    report = run_gate(
        args.video,
        args.format,
        preset=args.preset,
        frames_dir=args.frames_dir,
        credits=args.credits,
        json_path=args.json_path,
        tol_lufs=args.tol_lufs,
        max_peak=args.max_peak,
        max_silence=args.max_silence,
        expect_width=args.expect_width,
        expect_height=args.expect_height,
    )
    print(json.dumps(report, indent=2))
    if report["ok"]:
        print("qc_gate: PASS", file=sys.stderr)
        return 0
    failed = [check["check"] for check in report["checks"] if not check["ok"]]
    print(f"qc_gate: FAIL — {', '.join(failed)}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
