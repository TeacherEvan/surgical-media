"""Unit tests for render_engine frame quantization — no rendering required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
