import json

import pytest
from storyboard import assign_start_times, total_duration, validate_storyboard


def _valid_board():
    return {
        "meta": {"title": "t"},
        "format": {"width": 1280, "height": 720, "fps": 30},
        "scenes": [
            {
                "scene_id": "a",
                "archetype": "doc_essay",
                "duration_sec": 2.0,
                "elements": [{"type": "background", "color": "#000000"}],
            },
            {
                "scene_id": "b",
                "archetype": "code_report",
                "duration_sec": 3.0,
                "elements": [{"type": "background", "color": "#000000"}],
                "sfx_events": [{"t_sec": 1.5, "sfx": "pop"}],
            },
        ],
    }


def test_valid_board_passes():
    assert validate_storyboard(_valid_board()) == []


def test_missing_title_fails():
    board = _valid_board()
    board["meta"] = {}
    assert any("meta.title" in e for e in validate_storyboard(board))


def test_bad_fps_and_dims():
    board = _valid_board()
    board["format"].update(width=10, height=99999, fps=31)
    errors = validate_storyboard(board)
    assert any("format.width" in e for e in errors)
    assert any("format.height" in e for e in errors)
    assert any("format.fps" in e for e in errors)


def test_unknown_archetype():
    board = _valid_board()
    board["scenes"][0]["archetype"] = "vaporwave"
    assert any("archetype" in e for e in validate_storyboard(board))


def test_element_requires_type():
    board = _valid_board()
    board["scenes"][0]["elements"] = [{"color": "#000"}]
    assert any("elements[0]" in e for e in validate_storyboard(board))


def test_sfx_after_scene_end_rejected():
    board = _valid_board()
    board["scenes"][1]["sfx_events"] = [{"t_sec": 9.9, "sfx": "pop"}]
    assert any("exceeds scene duration" in e for e in validate_storyboard(board))


def test_zoom_out_of_range_rejected():
    board = _valid_board()
    board["scenes"][0]["camera"] = {"zoom_start": 0.5}
    assert any("zoom_start" in e for e in validate_storyboard(board))


def test_assign_start_times_and_total():
    board = assign_start_times(_valid_board())
    assert board["scenes"][0]["start_sec"] == 0.0
    assert board["scenes"][1]["start_sec"] == 2.0
    assert total_duration(_valid_board()) == pytest.approx(5.0)


def test_words_must_be_ordered_pairs():
    board = _valid_board()
    board["scenes"][0]["words"] = [{"word": "hi", "start": 1.5, "end": 1.0}]
    assert any("words[0]" in e for e in validate_storyboard(board))


def test_demo_storyboard_validates():
    demo = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "examples"
        / "tri_archetype_storyboard.json"
    )
    if demo.is_file():
        data = json.loads(demo.read_text(encoding="utf-8"))
        assert validate_storyboard(data) == []
