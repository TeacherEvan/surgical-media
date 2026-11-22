#!/usr/bin/env python3
"""verify_output.py — ffprobe QC assertions for rendered MP4s.

Fails hard (exit 1) if:
  * video or audio stream is missing
  * video pixel format is not yuv420p (breaks iOS / Safari / Instagram / TikTok)
  * resolution or fps deviates from expectation
  * integrated duration drifts from the storyboard by more than 150 ms
  * video codec is not H.264
  * more than 75% of the audio track is digital silence (pad + VO always present)

Usage:
    verify_output.py --input out.mp4 [--storyboard board.json]
                     [--expect-width 1920] [--expect-height 1080] [--expect-fps 30]
                     [--expect-duration 14.0] [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from monetization_gate import check_board_monetization

DRIFT_TOLERANCE_SEC = 0.150
MAX_SILENCE_FRACTION = (
    0.75  # pipeline always mixes a pad + VO — >75% silent means broken audio
)
SILENCE_NOISE_DB = -50.0
SILENCE_MIN_SEC = 0.8


def _parse_silencedetect(
    stderr: str, duration: float | None = None
) -> list[tuple[float, float]]:
    """Parse ffmpeg silencedetect stderr into (start, end) second pairs."""
    starts = [
        float(m) for m in re.findall(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)", stderr)
    ]
    ends = [
        float(m) for m in re.findall(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)", stderr)
    ]
    intervals: list[tuple[float, float]] = []
    for i, start in enumerate(starts):
        if i < len(ends):
            intervals.append((start, ends[i]))
        elif duration is not None:
            intervals.append((start, duration))  # trailing silence to EOF
    return intervals


def silence_coverage(intervals: list[tuple[float, float]], duration: float) -> float:
    if duration <= 0:
        return 0.0
    return min(1.0, sum(max(0.0, end - start) for start, end in intervals) / duration)


def _ffprobe_json(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
        text=True,
    )
    return cast(dict[str, Any], json.loads(proc.stdout))


def _fps_of(stream: dict[str, Any]) -> float:
    rate = stream.get("r_frame_rate") or stream.get("avg_frame_rate") or "0/1"
    num, _, den = str(rate).partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def verify_mp4(
    path: str | Path,
    expected_width: int | None = None,
    expected_height: int | None = None,
    expected_fps: float | None = None,
    expected_duration: float | None = None,
    storyboard: str | Path | None = None,
    max_silence_fraction: float = MAX_SILENCE_FRACTION,
    monetization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(path)
    report: dict[str, Any] = {"input": str(path), "checks": [], "ok": True}

    def check(name: str, passed: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "ok": bool(passed), "detail": detail})
        if not passed:
            report["ok"] = False

    if monetization is not None:
        for issue in monetization["issues"]:
            scene = f" (scene: {issue['scene']})" if issue.get("scene") else ""
            check(
                issue["rule"],
                issue["severity"] != "ERROR",
                f"[{issue['severity']}] {issue['detail']}{scene}",
            )

    if storyboard is not None:
        try:
            board = json.loads(Path(storyboard).read_text(encoding="utf-8"))
            fmt = board.get("format", {})
            expected_width = expected_width or int(fmt.get("width", 0)) or None
            expected_height = expected_height or int(fmt.get("height", 0)) or None
            expected_fps = expected_fps or float(fmt.get("fps", 0)) or None
            if expected_duration is None:
                expected_duration = sum(
                    float(s["duration_sec"]) for s in board.get("scenes", [])
                )
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            check("storyboard_readable", False, str(exc))

    if not path.is_file():
        check("file_exists", False, f"no such file: {path}")
        return report

    try:
        probe = _ffprobe_json(path)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        check("ffprobe_runs", False, str(exc))
        return report

    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    check("video_stream_present", video is not None)
    check("audio_stream_present", audio is not None)

    duration = None
    try:
        duration = float(probe.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass

    if video:
        check(
            "codec_h264",
            video.get("codec_name") == "h264",
            f"codec={video.get('codec_name')}",
        )
        check(
            "pix_fmt_yuv420p",
            video.get("pix_fmt") == "yuv420p",
            f"pix_fmt={video.get('pix_fmt')} (yuv420p required for iOS/Safari/IG/TikTok)",
        )
        if expected_width:
            w_actual = int(video.get("width", 0))
            w_ok = w_actual == expected_width
            check(
                "width",
                w_ok,
                f"{w_actual} == {expected_width}"
                if w_ok
                else f"{video.get('width')} != {expected_width}",
            )
        if expected_height:
            h_actual = int(video.get("height", 0))
            h_ok = h_actual == expected_height
            check(
                "height",
                h_ok,
                f"{h_actual} == {expected_height}"
                if h_ok
                else f"{video.get('height')} != {expected_height}",
            )
        if expected_fps:
            fps = _fps_of(video)
            fps_ok = abs(fps - expected_fps) < 0.01
            check(
                "fps",
                fps_ok,
                f"{fps:.3f} == {expected_fps}"
                if fps_ok
                else f"{fps:.3f} != {expected_fps}",
            )
        if duration is None:
            try:
                duration = float(video.get("duration"))
            except (TypeError, ValueError):
                pass

    if audio:
        check(
            "audio_codec_aac",
            audio.get("codec_name") == "aac",
            f"codec={audio.get('codec_name')}",
        )
        sr = int(audio.get("sample_rate", 0))
        check("audio_48k", sr == 48000, f"sample_rate={sr}")
        # Broken-audio net: the pipeline always mixes a pad + VO, so an
        # (almost) fully silent track means the master build failed silently.
        if duration and shutil.which("ffmpeg"):
            try:
                proc = subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "info",
                        "-i",
                        str(path),
                        "-af",
                        f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_SEC}",
                        "-f",
                        "null",
                        "-",
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                check("audio_not_silent", False, f"silencedetect failed: {exc}")
            else:
                intervals = _parse_silencedetect(proc.stderr, duration)
                coverage = silence_coverage(intervals, duration)
                check(
                    "audio_not_silent",
                    coverage <= max_silence_fraction,
                    f"{coverage * 100:.0f}% silent (max {max_silence_fraction * 100:.0f}%); "
                    f"{len(intervals)} interval(s)",
                )

    if expected_duration is not None:
        if duration is None:
            check("duration_drift_le_150ms", False, "duration could not be measured")
        else:
            drift = abs(duration - expected_duration)
            check(
                "duration_drift_le_150ms",
                drift <= DRIFT_TOLERANCE_SEC,
                f"|{duration:.3f} - {expected_duration:.3f}| = {drift * 1000:.0f} ms",
            )

    report["streams"] = {
        "video": {
            k: video.get(k)
            for k in ("codec_name", "pix_fmt", "width", "height", "r_frame_rate")
        }
        if video
        else None,
        "audio": {k: audio.get(k) for k in ("codec_name", "sample_rate", "channels")}
        if audio
        else None,
    }
    report["duration_sec"] = duration
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="QC-verify a rendered MP4.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--storyboard", type=Path, default=None)
    parser.add_argument("--expect-width", type=int, default=None)
    parser.add_argument("--expect-height", type=int, default=None)
    parser.add_argument("--expect-fps", type=float, default=None)
    parser.add_argument("--expect-duration", type=float, default=None)
    parser.add_argument(
        "--max-silence-fraction",
        type=float,
        default=MAX_SILENCE_FRACTION,
        help="Fail if more than this fraction of the track is silent (default 0.75)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="assets/manifest.json — run monetization gates",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=None,
        help="script.json — adversarial-phrasing scan",
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="Also write the report JSON here"
    )
    args = parser.parse_args()

    if shutil.which("ffprobe") is None:
        print("verify_output: ffprobe not found on PATH", file=sys.stderr)
        return 2

    monetization: dict[str, Any] | None = None
    if args.manifest or args.script:
        board = (
            json.loads(args.storyboard.read_text(encoding="utf-8"))
            if args.storyboard
            else {}
        )
        monetization = check_board_monetization(
            board,
            board_path=args.storyboard,
            manifest_path=args.manifest,
            script_path=args.script,
        )

    report = verify_mp4(
        args.input,
        expected_width=args.expect_width,
        expected_height=args.expect_height,
        expected_fps=args.expect_fps,
        expected_duration=args.expect_duration,
        storyboard=args.storyboard,
        max_silence_fraction=args.max_silence_fraction,
        monetization=monetization,
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    if not report["ok"]:
        failed = [c["check"] for c in report["checks"] if not c["ok"]]
        print(f"verify_output: FAIL — {', '.join(failed)}", file=sys.stderr)
        return 1
    print("verify_output: PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
