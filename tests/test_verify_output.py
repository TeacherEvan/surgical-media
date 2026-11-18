import json

import verify_output
from conftest import requires_ffmpeg


def _board(tmp_path, dur=0.6):
    board = {
        "meta": {"title": "qc test"},
        "format": {"width": 320, "height": 180, "fps": 30},
        "scenes": [
            {
                "scene_id": "qc",
                "archetype": "mixed",
                "duration_sec": dur,
                "elements": [{"type": "background", "color": "#0D1117"}],
            },
        ],
    }
    path = tmp_path / "board.json"
    path.write_text(json.dumps(board), encoding="utf-8")
    return path


@requires_ffmpeg
def test_verify_passes_on_tiny_render(tmp_path):
    import render_engine

    board_path = _board(tmp_path)
    out_mp4 = tmp_path / "tiny.mp4"

    class Args:
        storyboard = board_path
        output = out_mp4
        quality = "draft"
        work_dir = tmp_path / "work"
        max_seconds = 30.0
        no_verify = True
        demo = False

    assert render_engine.render(Args()) == 0

    report = verify_output.verify_mp4(
        out_mp4,
        expected_width=320,
        expected_height=180,
        expected_fps=30,
        expected_duration=0.6,
    )
    assert report["ok"], json.dumps(report, indent=2)
    assert all(c["ok"] for c in report["checks"])


@requires_ffmpeg
def test_verify_fails_on_missing_file(tmp_path):
    report = verify_output.verify_mp4(tmp_path / "nope.mp4")
    assert not report["ok"]


@requires_ffmpeg
def test_verify_detects_duration_mismatch(tmp_path):
    import render_engine

    board_path = _board(tmp_path)
    out_mp4 = tmp_path / "tiny2.mp4"

    class Args:
        storyboard = board_path
        output = out_mp4
        quality = "draft"
        work_dir = tmp_path / "work"
        max_seconds = 30.0
        no_verify = True
        demo = False

    assert render_engine.render(Args()) == 0
    report = verify_output.verify_mp4(out_mp4, expected_duration=99.0)
    assert not report["ok"]
    assert any(
        c["check"] == "duration_drift_le_150ms" and not c["ok"]
        for c in report["checks"]
    )


@requires_ffmpeg
def test_render_rejects_overlong_storyboard(tmp_path):
    import render_engine

    board_path = _board(tmp_path, dur=5.0)

    class Args:
        storyboard = board_path
        output = tmp_path / "should_not_exist.mp4"
        quality = "draft"
        work_dir = tmp_path / "work"
        max_seconds = 1.0  # board is 5s — must refuse
        no_verify = True
        demo = False

    assert render_engine.render(Args()) == 2
    assert not (tmp_path / "should_not_exist.mp4").exists()


def test_parse_silencedetect_basic():
    stderr = (
        "[silencedetect @ 0x55] silence_start: 0\n"
        "[silencedetect @ 0x55] silence_end: 1.5 | silence_duration: 1.5\n"
        "[silencedetect @ 0x55] silence_start: 4.0\n"
        "[silencedetect @ 0x55] silence_end: 6.25 | silence_duration: 2.25\n"
    )
    assert verify_output._parse_silencedetect(stderr) == [(0.0, 1.5), (4.0, 6.25)]


def test_parse_silencedetect_trailing_silence_to_eof():
    stderr = "[x] silence_start: 2.0\n"
    assert verify_output._parse_silencedetect(stderr, duration=5.0) == [(2.0, 5.0)]


def test_parse_silencedetect_no_silence():
    assert verify_output._parse_silencedetect("nothing here\n") == []


def test_silence_coverage_sums_and_clamps():
    assert verify_output.silence_coverage([(0, 0.5), (1.0, 2.0)], 4.0) == 0.375
    assert verify_output.silence_coverage([(0, 10)], 4.0) == 1.0
    assert verify_output.silence_coverage([], 4.0) == 0.0
    assert verify_output.silence_coverage([(0, 1)], 0.0) == 0.0


@requires_ffmpeg
def test_silent_mp4_fails_audio_not_silent(tmp_path):
    import subprocess

    out_mp4 = tmp_path / "silent.mp4"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=2:r=24",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out_mp4),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    report = verify_output.verify_mp4(out_mp4)
    silent_check = next(c for c in report["checks"] if c["check"] == "audio_not_silent")
    assert silent_check["ok"] is False
    assert report["ok"] is False
