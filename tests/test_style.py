"""Style bible: presets, merging, @role resolution, validator + schema parity."""

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import storyboard
import style

EXAMPLE = REPO / "examples" / "tri_archetype_storyboard.json"
SCHEMA = REPO / "schemas" / "storyboard.schema.json"


def _board(**style_block):
    b = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    if style_block:
        b["style"] = style_block
    return b


def test_expected_presets_exist():
    assert {
        "soft_clay",
        "punchy_pop",
        "newsroom_clean",
        "noir_restraint",
        "risograph",
        "tech_blueprint",
    } <= set(style.list_presets())


@pytest.mark.parametrize("name", style.list_presets())
def test_every_preset_is_valid(name):
    errors: list[str] = []
    style.validate_style({"preset": name}, errors)
    assert errors == []
    resolved = style.resolve_style({"preset": name})
    assert set(resolved["palette"]) == set(style.PALETTE_ROLES)


def test_inline_overrides_merge_per_role():
    r = style.resolve_style({"preset": "soft_clay", "palette": {"accent": "#112233"}})
    assert r["palette"]["accent"] == "#112233"
    assert r["palette"]["ground"] == "#F5E9DD"


def test_unknown_preset_and_traversal_rejected():
    errors: list[str] = []
    style.validate_style({"preset": "nope"}, errors)
    assert any("unknown style preset" in e for e in errors)
    with pytest.raises(ValueError):
        style.load_preset("../schemas/storyboard")


def test_role_refs_resolve_and_no_style_is_noop():
    plain = _board()
    assert style.apply_style(plain) is plain
    b = _board(preset="punchy_pop")
    b["scenes"][0]["elements"] = [{"type": "background", "color": "@ground"}]
    out = style.apply_style(b)
    assert out["scenes"][0]["elements"][0]["color"] == "#FFF4D6"
    assert out["style"]["palette"]["accent"] == "#FF4D6D"
    assert b["scenes"][0]["elements"][0]["color"] == "@ground"  # input untouched


def test_unresolved_ref_is_a_validation_error():
    b = _board()
    b["scenes"][0]["elements"] = [{"type": "background", "color": "@accent"}]
    assert any("@accent" in e for e in storyboard.validate_storyboard(b))


def test_bad_style_values_rejected():
    b = _board(palette={"accent": "red"}, grade={"grain": 3}, motion={"feel": "wild"})
    errs = storyboard.validate_storyboard(b)
    assert any("palette.accent" in e for e in errs)
    assert any("grade.grain" in e for e in errs)
    assert any("motion.feel" in e for e in errs)


def test_valid_style_board_validates_and_assigns_start_times():
    b = _board(preset="noir_restraint")
    assert storyboard.validate_storyboard(b) == []
    assert storyboard.assign_start_times(b)["style"]["material"]["family"] == "metal"


def test_style_block_passes_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text("utf-8")))
    good = _board(preset="soft_clay", palette={"accent": "#A65A38"})
    assert list(validator.iter_errors(good)) == []
    bad = copy.deepcopy(good)
    bad["style"]["palette"]["accent"] = "red"
    assert list(validator.iter_errors(bad))
    bad2 = copy.deepcopy(good)
    bad2["style"]["bogus"] = 1
    assert list(validator.iter_errors(bad2))


def test_ease_set_matches_storyboard():
    assert style.VALID_EASES == storyboard.VALID_EASINGS


def test_motion_camera_default_only_for_scenes_without_camera():
    b = _board(preset="punchy_pop")
    b["scenes"][0].pop("camera", None)
    b["scenes"][1]["camera"] = {"zoom_end": 1.5}
    out = storyboard.assign_start_times(b)
    assert out["scenes"][0]["camera"]["zoom_end"] > 1.08
    assert out["scenes"][1]["camera"] == {"zoom_end": 1.5}
    assert storyboard.validate_storyboard(b) == []


def test_kelvin_to_hex_warm_vs_cool():
    warm, cool = style.kelvin_to_hex(2700), style.kelvin_to_hex(9000)
    w, c = int(warm[1:3], 16), int(cool[1:3], 16)
    wb, cb = int(warm[5:7], 16), int(cool[5:7], 16)
    assert w > wb and cb > c
    assert (
        style.kelvin_to_hex(6600) == "#FFFFFF" or style.kelvin_to_hex(6600)[1:3] == "FF"
    )


def test_style_light_injected_only_into_scene_specs():
    import threejs_bridge

    b = _board(preset="soft_clay")
    b["scenes"][0]["scene_spec"] = {"category": "orbital_or_field_3d"}
    out = style.apply_style(b)
    spec = out["scenes"][0]["scene_spec"]
    assert spec["style_light"]["bg_hex"] == "#F5E9DD"
    assert "scene_spec" not in out["scenes"][1]
    assert "style_light" not in b["scenes"][0]["scene_spec"]  # input untouched
    assert (
        threejs_bridge.threejs_adapter_spec(spec)["style_light"] == spec["style_light"]
    )
    import render_engine

    assert (
        render_engine._blender_adapter_spec(spec)["style_light"] == spec["style_light"]
    )
    assert "style_light" not in threejs_bridge.threejs_adapter_spec({"category": "x"})
