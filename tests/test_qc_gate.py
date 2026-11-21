"""Offline tests for the hard pre-delivery QC gate."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import qc_gate
import verify_output
from PIL import Image

EBUR_OK = """\
Integrated loudness:
 I:         -14.0 LUFS
 LRA:         4.0 LU
True peak:
 Peak:       -1.2 dBFS
"""

SILENCE_OK = """\
[silencedetect @ 0x1] silence_start: 1.000
[silencedetect @ 0x1] silence_end: 1.300 | silence_duration: 0.300
"""

PROBE: dict[str, Any] = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "pix_fmt": "yuv420p",
            "width": 1080,
            "height": 1920,
            "r_frame_rate": "30/1",
            "duration": "10.0",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": 48000,
            "channels": 2,
            "duration": "10.0",
        },
    ],
    "format": {"duration": "10.0", "size": "12345678"},
}


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ebur: str = EBUR_OK,
    silence: str = SILENCE_OK,
    ffmpeg: bool = True,
) -> list[tuple[list[str], dict[str, Any]]]:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/ffmpeg" if ffmpeg else None
    )
    monkeypatch.setattr(
        verify_output, "_ffprobe_json", lambda path: copy.deepcopy(PROBE)
    )

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((list(argv), kwargs))
        joined = " ".join(str(a) for a in argv)
        if "ebur128" in joined:
            stderr = ebur
        elif "silencedetect" in joined:
            stderr = silence
        elif "-frames:v" in argv:
            Image.new("RGB", (1080, 1920), (0, 0, 0)).save(argv[-1])
            stderr = ""
        else:
            stderr = ""
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _video(tmp_path: Path) -> Path:
    path = tmp_path / "final.mp4"
    path.write_bytes(b"fake-mp4")
    return path


def _checks(report: dict[str, Any]) -> dict[str, bool]:
    return {c["check"]: c["ok"] for c in report["checks"]}


# -- loudness parsing ------------------------------------------------------
def test_loudness_parses_final_summary() -> None:
    parsed = qc_gate.loudness_from_ffmpeg(
        "[Parsed_ebur128_0 @ x] t: 1.0 I: -inf LUFS Peak: -inf dBFS\n" + EBUR_OK
    )
    assert parsed == {"integrated_lufs": -14.0, "true_peak_dbtp": -1.2}


def test_loudness_last_numeric_match_wins() -> None:
    stderr = "I: -20.0 LUFS\nPeak: -0.5 dBFS\n" + EBUR_OK
    assert qc_gate.loudness_from_ffmpeg(stderr) == {
        "integrated_lufs": -14.0,
        "true_peak_dbtp": -1.2,
    }


def test_loudness_empty_on_garbage() -> None:
    assert qc_gate.loudness_from_ffmpeg("nothing useful here") == {}


def test_loudness_check_pass_and_tolerance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fakes(monkeypatch, ebur="I: -14.8 LUFS\nPeak: -1.2 dBFS\n")
    report = qc_gate.run_gate(_video(tmp_path), "9:16", tol_lufs=1.0)
    assert _checks(report)["loudness_integrated"] is True

    _install_fakes(monkeypatch, ebur="I: -14.8 LUFS\nPeak: -1.2 dBFS\n")
    strict = qc_gate.run_gate(_video(tmp_path), "9:16", tol_lufs=0.2)
    assert _checks(strict)["loudness_integrated"] is False


@pytest.mark.parametrize(
    ("peak", "expected"),
    [(-1.0, True), (-1.2, True), (-0.999, False), (0.0, False)],
)
def test_true_peak_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, peak: float, expected: bool
) -> None:
    _install_fakes(monkeypatch, ebur=f"I: -14.0 LUFS\nPeak: {peak:.3f} dBFS\n")
    report = qc_gate.run_gate(_video(tmp_path), "9:16", max_peak=-1.0)
    assert _checks(report)["loudness_true_peak"] is expected


# -- dead air --------------------------------------------------------------
def test_dead_air_flags_overlong_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = (
        "silence_start: 0.000\nsilence_end: 0.600\n"
        "silence_start: 2.000\nsilence_end: 3.200\n"
    )
    _install_fakes(monkeypatch, silence=stderr)
    report = qc_gate.run_gate(_video(tmp_path), "9:16", max_silence=0.6)
    assert _checks(report)["no_dead_air"] is False
    assert [round(s["duration"], 2) for s in report["silences"]] == [0.6, 1.2]


def test_dead_air_accepts_short_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = "silence_start: 0.000\nsilence_end: 0.600\n"
    _install_fakes(monkeypatch, silence=stderr)
    report = qc_gate.run_gate(_video(tmp_path), "9:16", max_silence=0.6)
    assert _checks(report)["no_dead_air"] is True


# -- safe rect math --------------------------------------------------------
@pytest.mark.parametrize(
    ("fmt", "preset", "width", "height", "expected"),
    [
        ("9:16", "organic", 1080, 1920, (60, 180, 930, 1540)),
        ("9:16", "strict", 1080, 1920, (65, 288, 888, 1248)),
        ("9:16", "strict", 2160, 3840, (130, 576, 1776, 2496)),
        ("16:9", "organic", 1920, 1080, (96, 64, 1824, 1016)),
        ("16:9", "strict", 1920, 1080, (182, 112, 1738, 968)),
        ("1:1", "organic", 1080, 1080, (80, 80, 1000, 1000)),
        ("1:1", "strict", 1080, 1080, (126, 126, 954, 954)),
        ("4:5", "organic", 1440, 1800, (80, 80, 1360, 1720)),
        ("4:5", "strict", 1440, 1800, (144, 162, 1296, 1638)),
    ],
)
def test_safe_rect_for(
    fmt: str,
    preset: str,
    width: int,
    height: int,
    expected: tuple[int, int, int, int],
) -> None:
    assert qc_gate.safe_rect_for(fmt, preset, width, height) == expected


def test_strict_rect_is_inside_organic() -> None:
    for fmt in qc_gate.FORMAT_SIZES:
        width, height = qc_gate.FORMAT_SIZES[fmt]
        ox0, oy0, ox1, oy1 = qc_gate.safe_rect_for(fmt, "organic", width, height)
        sx0, sy0, sx1, sy1 = qc_gate.safe_rect_for(fmt, "strict", width, height)
        assert ox0 <= sx0 < sx1 <= ox1
        assert oy0 <= sy0 < sy1 <= oy1


# -- overlay pixels --------------------------------------------------------
def test_draw_masks_pixel_presence() -> None:
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    out = qc_gate.draw_masks(image, qc_gate.ORGANIC_RECT_9_16, qc_gate.STRICT_RECT_9_16)
    assert out.mode == "RGB"
    px = out.load()
    amber = px[5, 5]  # outside organic
    red = px[62, 500]  # between organic and strict
    clean = px[500, 800]  # inside strict
    assert amber[0] > amber[1] > amber[2] == 0
    assert red[0] > red[1] and red[0] > red[2] and red[1] < 40
    assert clean == (0, 0, 0)


# -- credits ---------------------------------------------------------------
def test_credits_checks_pass_and_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fakes(monkeypatch)
    credits = tmp_path / "CREDITS.md"
    credits.write_text("Photo by A — photo.jpg\n", encoding="utf-8")
    (tmp_path / "credits.json").write_text(
        json.dumps({"assets": [{"file": "assets/photo.jpg"}]}), encoding="utf-8"
    )
    passed = qc_gate.run_gate(_video(tmp_path), "9:16", credits=credits)
    assert all(
        _checks(passed)[name]
        for name in (
            "credits_file_exists",
            "credits_nonempty",
            "credits_assets_listed",
        )
    )

    credits.write_text("No assets named here.\n", encoding="utf-8")
    failed = qc_gate.run_gate(_video(tmp_path), "9:16", credits=credits)
    assert _checks(failed)["credits_assets_listed"] is False


def test_credits_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fakes(monkeypatch)
    report = qc_gate.run_gate(_video(tmp_path), "9:16", credits=tmp_path / "none.md")
    assert _checks(report)["credits_file_exists"] is False
    assert "credits_nonempty" not in _checks(report)


def test_credits_skipped_when_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fakes(monkeypatch)
    report = qc_gate.run_gate(_video(tmp_path), "9:16")
    assert "credits_file_exists" not in _checks(report)


# -- report / CLI ----------------------------------------------------------
def test_report_structure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fakes(monkeypatch)
    report = qc_gate.run_gate(_video(tmp_path), "9:16", preset="strict")
    assert set(report) >= {
        "video",
        "format",
        "preset",
        "checks",
        "ok",
        "loudness",
        "silences",
        "frames",
    }
    assert set(report["loudness"]) == {"integrated_lufs", "true_peak_dbtp"}
    assert isinstance(report["ok"], bool)
    for check in report["checks"]:
        assert set(check) == {"check", "ok", "detail"}
    assert report["format"] == "9:16"
    assert report["preset"] == "strict"


def test_verify_output_checks_are_merged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fakes(monkeypatch)
    report = qc_gate.run_gate(_video(tmp_path), "9:16")
    names = set(_checks(report))
    assert {"codec_h264", "pix_fmt_yuv420p", "audio_not_silent"} <= names


def test_explicit_dimension_overrides_replace_format_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fakes(monkeypatch)
    # The fake probe is 1080x1920; without overrides a 16:9 gate expects
    # 1920x1080 and fails. Explicit overrides must keep the strict checks.
    report = qc_gate.run_gate(
        _video(tmp_path),
        "16:9",
        expect_width=1080,
        expect_height=1920,
    )
    checks = _checks(report)
    assert checks["width"] is True
    assert checks["height"] is True
    assert report["ok"] is True

    argv = [
        "--video",
        str(_video(tmp_path)),
        "--format",
        "16:9",
        "--expect-width",
        "1080",
        "--expect-height",
        "1920",
    ]
    _install_fakes(monkeypatch)
    assert qc_gate.main(argv) == 0


def test_exit_codes_and_stdio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    video = _video(tmp_path)
    _install_fakes(monkeypatch)
    assert qc_gate.main(["--video", str(video), "--format", "9:16"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out)["ok"] is True
    assert "PASS" in err

    _install_fakes(monkeypatch, ebur="I: -20.0 LUFS\nPeak: -1.2 dBFS\n")
    assert qc_gate.main(["--video", str(video), "--format", "9:16"]) == 3
    out, err = capsys.readouterr()
    assert json.loads(out)["ok"] is False
    assert "FAIL" in err
    assert "loudness_integrated" in err


def test_json_file_written(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fakes(monkeypatch)
    json_path = tmp_path / "report.json"
    qc_gate.run_gate(_video(tmp_path), "9:16", json_path=json_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["ok"] is True


def test_no_ffmpeg_degradation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fakes(monkeypatch, ffmpeg=False)
    report = qc_gate.run_gate(_video(tmp_path), "9:16", frames_dir=tmp_path / "frames")
    checks = _checks(report)
    assert checks["loudness_integrated"] is False
    assert checks["loudness_true_peak"] is False
    assert checks["no_dead_air"] is False
    assert checks["safe_zone_overlays_written"] is False
    details = " ".join(c["detail"] for c in report["checks"])
    assert "ffmpeg not found" in details
    assert report["ok"] is False


# -- frame extraction ------------------------------------------------------
def test_frame_extraction_argv_and_overlays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _install_fakes(monkeypatch)
    frames_dir = tmp_path / "frames"
    report = qc_gate.run_gate(_video(tmp_path), "9:16", frames_dir=frames_dir)

    extractions = [(argv, kwargs) for argv, kwargs in calls if "-frames:v" in argv]
    assert len(extractions) == 3
    for argv, kwargs in extractions:
        assert isinstance(argv, list)
        assert argv[0] == "ffmpeg"
        assert "shell" not in kwargs
        assert kwargs.get("timeout") == qc_gate.SUBPROCESS_TIMEOUT
        assert kwargs.get("stdin") is subprocess.DEVNULL
    assert [argv[argv.index("-ss") + 1] for argv, _ in extractions] == [
        "0.000",
        "5.000",
        "9.500",
    ]

    assert _checks(report)["safe_zone_overlays_written"] is True
    assert len(report["frames"]) == 3
    for path in report["frames"]:
        audit = Path(path)
        assert audit.name.endswith("_audit.png")
        assert audit.is_file()
        assert Image.open(audit).size == (1080, 1920)
