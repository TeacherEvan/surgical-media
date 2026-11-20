"""Platform presets: caption defaults, validation, schema parity, no stdlib shadowing."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import platform_presets as pp
import storyboard

EXAMPLE = REPO / "examples" / "tri_archetype_storyboard.json"
SCHEMA = REPO / "schemas" / "storyboard.schema.json"


def _board(**extra):
    b = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    b.update(extra)
    return b


def _caption(board):
    for scene in board["scenes"]:
        for el in scene.get("elements", []):
            if el["type"] == "kinetic_captions":
                return el
    raise AssertionError("no captions in example")


def test_stdlib_platform_not_shadowed():
    import platform as stdlib_platform

    assert hasattr(stdlib_platform, "system")


def test_no_platform_block_is_noop():
    b = _board()
    assert pp.apply_platform(b) is b


def test_sticker_defaults_fill_but_explicit_keys_win():
    b = _board(
        style={"preset": "punchy_pop"},
        platform={"preset": "shorts_tiktok_reels"},
        format={"width": 1080, "height": 1920, "fps": 30},
    )
    cap = _caption(storyboard.assign_start_times(b))
    assert cap["bg_color"] == "none"
    assert cap["stroke_color"] == "#1B1B1F"
    assert cap["y_anchor"] == 0.60
    assert cap["size"] == round(1920 * 0.034)
    # explicit authoring is preserved
    b["scenes"][0]["elements"] = [
        {"type": "kinetic_captions", "size": 33, "accent": "#112233"}
    ]
    cap2 = _caption(storyboard.assign_start_times(b))
    assert cap2["size"] == 33 and cap2["accent"] == "#112233"
    assert cap2["bg_color"] == "none"


def test_editorial_uses_serif_and_translucent_card():
    b = _board(style={"preset": "soft_clay"}, platform={"preset": "youtube_long"})
    cap = _caption(storyboard.assign_start_times(b))
    assert cap["font_family"] == "serif" and cap["bg_alpha"] < 1.0
    assert cap["bg_color"] == "#F5E9DD"


def test_none_leaves_captions_untouched():
    b = _board(platform={"preset": "youtube_long", "caption_style": "none"})
    assert _caption(storyboard.assign_start_times(b)) == _caption(b)


def test_input_not_mutated():
    b = _board(style={"preset": "noir_restraint"}, platform={"preset": "square"})
    snapshot = json.dumps(b, sort_keys=True)
    storyboard.assign_start_times(b)
    assert json.dumps(b, sort_keys=True) == snapshot


def test_validation_errors():
    errs = storyboard.validate_storyboard(
        _board(platform={"preset": "vhs", "caption_style": "x", "hook_max_sec": 0})
    )
    assert any("platform.preset" in e for e in errs)
    assert any("platform.caption_style" in e for e in errs)
    assert any("hook_max_sec" in e for e in errs)
    assert storyboard.validate_storyboard(_board(platform={"preset": "square"})) == []


def test_schema_parity():
    jsonschema = pytest.importorskip("jsonschema")
    v = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text("utf-8")))
    assert not list(v.iter_errors(_board(platform={"preset": "square"})))
    assert list(v.iter_errors(_board(platform={"preset": "vhs"})))
    assert list(v.iter_errors(_board(platform={"bogus": 1})))


def test_mix_hex_and_family():
    assert pp.mix_hex("#000000", "#FFFFFF", 0.5) == "#808080"
    assert pp.font_family("CormorantGaramond") == "serif"
    assert pp.font_family(None) == "sans"
