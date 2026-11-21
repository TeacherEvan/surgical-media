"""Unit tests for render_engine frame quantization — no rendering required."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render_engine
from render_engine import estimate, frame_counts, scene_frames

EXAMPLE = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "tri_archetype_storyboard.json"
)


def _scenes(durations):
    return [{"duration_sec": d} for d in durations]


def test_scene_frames_rounds_and_floors():
    assert scene_frames({"duration_sec": 1.0}, 30) == 30
    assert scene_frames({"duration_sec": 0.001}, 30) == 1  # floor of one frame


def test_frame_counts_exact_integer_case():
    assert frame_counts(_scenes([1.0, 2.0, 0.5]), 30) == [30, 60, 15]


def test_frame_counts_stays_within_one_frame_of_exact_total():
    # cumulative drift case: 7 × 0.35 s at 30 fps; exact = 73.5 frames
    counts = frame_counts(_scenes([0.35] * 7), 30)
    assert abs(sum(counts) - 7 * 0.35 * 30) <= 1.0
    # per-scene quantization is strictly worse here (70 frames)
    assert sum(counts) > sum(scene_frames(s, 30) for s in _scenes([0.35] * 7))


def test_frame_counts_single_scene_and_empty():
    assert frame_counts([], 30) == []
    assert frame_counts(_scenes([2.4]), 25) == [60]


def test_frame_counts_never_zero():
    counts = frame_counts(_scenes([0.001, 0.001, 2.0]), 30)
    assert all(c >= 1 for c in counts)


def test_estimate_frame_total_matches_frame_counts():
    import json

    board = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    fps = board["format"]["fps"]
    report = estimate(board)
    assert report["total_frames"] == sum(frame_counts(board["scenes"], fps))
    assert report["scenes"] == len(board["scenes"])
    assert report["fps"] == fps


def _measured_json() -> str:
    return json.dumps(
        {
            "measured_I": "-16.2",
            "measured_TP": "-2.5",
            "measured_LRA": "5.1",
            "measured_thresh": "-26.4",
            "offset": "+0.2",
        }
    )


def test_two_pass_loudnorm_uses_measured_values(monkeypatch: Any, tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout="", stderr=f"noise\n{_measured_json()}\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    filt = render_engine._loudnorm_filter(tmp_path / "master.wav")
    assert "measured_I=-16.20" in filt
    assert "linear=true" in filt
    assert "alimiter=limit=0.891" in filt
    assert calls and calls[0][0] == "ffmpeg"
    assert "-c" not in calls[0]  # list argv, never shell=True


def test_two_pass_loudnorm_accepts_legacy_json_keys(monkeypatch: Any, tmp_path: Path):
    legacy = json.dumps(
        {
            "input_i": "-17.66",
            "input_tp": "-1.00",
            "input_lra": "2.60",
            "input_thresh": "-27.66",
            "target_offset": "1.61",
        }
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", legacy),
    )
    filt = render_engine._loudnorm_filter(tmp_path / "master.wav")
    assert "measured_I=-17.66" in filt
    assert "offset=1.61" in filt
    assert "acompressor" in filt


def test_two_pass_loudnorm_falls_back_on_bad_measurement(
    monkeypatch: Any, tmp_path: Path
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", "no json here"),
    )
    filt = render_engine._loudnorm_filter(tmp_path / "master.wav")
    assert "measured_I" not in filt
    assert "loudnorm=I=-14:TP=-2:LRA=11" in filt


def test_two_pass_loudnorm_falls_back_without_ffmpeg(monkeypatch: Any, tmp_path: Path):
    monkeypatch.setattr(render_engine.shutil, "which", lambda name: None)
    filt = render_engine._loudnorm_filter(tmp_path / "master.wav")
    assert "measured_I" not in filt
    assert "linear=true" not in filt
