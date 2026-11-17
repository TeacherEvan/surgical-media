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
