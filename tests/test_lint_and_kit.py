"""Tests for style_lint, contact_sheet, and publish_kit."""

import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import contact_sheet
import publish_kit
import style_lint

EXAMPLE = REPO / "examples" / "tri_archetype_storyboard.json"


def _board(**extra):
    b = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    b.update(extra)
    return b


def test_style_lint_catches_slop_tells():
    b = _board(
        style={"preset": "newsroom_clean"},
        platform={"preset": "shorts_tiktok_reels"},
        format={"width": 1280, "height": 720, "fps": 30},
    )
    # Remove hook text from scene 0, add unsourced quote_card, and center 3 scenes
    b["scenes"][0].pop("words", None)
    b["scenes"][0]["elements"] = [{"type": "background", "color": "@ground"}]
    b["scenes"][1]["elements"] = [
        {
            "type": "quote_card",
            "quote": "Claim without source",
            "box": [240, 160, 1040, 560],
        }
    ]
    b["scenes"][2]["elements"] = [{"type": "background", "box": [240, 160, 1040, 560]}]
    b["scenes"].append(
        {
            "scene_id": "extra_centered",
            "archetype": "doc_essay",
            "duration_sec": 8.0,
            "elements": [{"type": "background", "box": [240, 160, 1040, 560]}],
        }
    )
    rules = {f["rule"] for f in style_lint.lint_board(b)}
    assert "no_hook" in rules
    assert "unsourced_claim" in rules
    assert "aspect_mismatch" in rules
    assert "long_hold" in rules
    assert style_lint.score(style_lint.lint_board(b)) < 100


def test_style_lint_catches_audio_and_overlay_antipatterns():
    b = _board(
        audio={"pad": True, "pad_style": "drone"},
    )
    b["scenes"][0]["narration"] = "Spoken line."
    b["scenes"][0]["sfx_events"] = [
        {"t_sec": 0.5, "sfx": "chime"},
        {"t_sec": 0.8, "sfx": "whoosh"},
    ]
    b["scenes"][1]["elements"] = [
        {"type": "image", "src": "a.png", "box": [0, 0, 1280, 720], "attribution": "A"},
        {
            "type": "quote_card",
            "quote": "Over photo",
            "fill": "#000000",
            "alpha": 0.95,
            "box": [100, 100, 1100, 500],
        },
        {"type": "kinetic_captions", "bg_color": "#000000", "bg_alpha": 0.95},
    ]
    rules = {f["rule"] for f in style_lint.lint_board(b)}
    assert "synth_pad_enabled" in rules
    assert "tonal_sfx_overuse" in rules
    assert "synth_sfx_used" in rules
    assert "opaque_text_box" in rules
    assert "text_obstructs_visual" in rules


def test_reference_boards_score_100_on_style_lint():
    for ref in sorted((REPO / "examples").glob("ref_*.json")):
        findings = style_lint.lint_board(json.loads(ref.read_text(encoding="utf-8")))
        assert style_lint.score(findings) == 100, f"{ref.name}: {findings}"


def test_contact_sheet_builds_tiled_image(tmp_path):
    thumbs = []
    for i, col in enumerate([(200, 80, 80), (80, 200, 80), (80, 80, 200)]):
        p = tmp_path / f"scene_{i}.png"
        Image.new("RGB", (320, 180), col).save(p)
        thumbs.append(p)
    out = tmp_path / "sheet.png"
    contact_sheet.build_sheet(thumbs, out, cols=2, tile_w=160)
    assert out.is_file()
    with Image.open(out) as im:
        assert im.width > 320
        assert im.height > 180


def test_publish_kit_generates_chapters_credits_and_thumbnail(tmp_path):
    b = _board(platform={"preset": "youtube_long"})
    for i, s in enumerate(b["scenes"]):
        s["duration_sec"] = 12.0
        s["words"] = [{"word": f"word{i}", "start": 0.1, "end": 0.5}]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"assets": [{"attribution": "Photo by Alice (CC-BY)"}]})
    )
    tdir = tmp_path / "thumbs"
    tdir.mkdir()
    Image.new("RGB", (160, 90), (20, 20, 20)).save(tdir / "s0.png")
    hi = Image.new("RGB", (160, 90), (20, 20, 20))
    hi.paste((240, 240, 240), (40, 20, 120, 70))
    hi.save(tdir / "s1.png")

    md = publish_kit.build_kit(b, manifest=manifest, thumbs=tdir)
    assert "## Chapters" in md
    assert "0:00" in md
    assert "Photo by Alice (CC-BY)" in md
    assert "`s1.png`" in md
    assert "AI / synthetic-content disclosure" in md


# -- image-first anti-slop rules (v3.2.0) -------------------------------------
def test_lint_flags_board_with_no_subject_imagery():
    b = _board()
    b["meta"].pop("visual_intent", None)
    for s in b["scenes"]:
        s.pop("scene_spec", None)
        s["elements"] = [
            e for e in s["elements"] if e.get("type") not in ("image", "svg", "map")
        ]
    rules = {f["rule"] for f in style_lint.lint_board(b)}
    assert "no_subject_imagery" in rules


def test_lint_visual_intent_opt_out_silences_no_subject_imagery():
    b = _board()
    for s in b["scenes"]:
        s.pop("scene_spec", None)
        s["elements"] = [
            e for e in s["elements"] if e.get("type") not in ("image", "svg", "map")
        ]
    b["meta"]["visual_intent"] = "procedural_showcase"
    rules = {f["rule"] for f in style_lint.lint_board(b)}
    assert "no_subject_imagery" not in rules


def test_lint_flags_low_visual_coverage():
    b = _board()
    b["meta"].pop("visual_intent", None)
    b["scenes"][0]["elements"].insert(
        0, {"type": "image", "src": "assets/a.jpg", "attribution": "A"}
    )
    for s in b["scenes"][1:]:
        s.pop("scene_spec", None)
        s["elements"] = [
            e for e in s["elements"] if e.get("type") not in ("image", "svg", "map")
        ]
    rules = {f["rule"] for f in style_lint.lint_board(b)}
    assert "low_visual_coverage" in rules
    assert "no_subject_imagery" not in rules


def test_lint_flags_placeholder_filler():
    b = _board()
    b["scenes"][0]["elements"].append(
        {"type": "scaling_chart", "label": "COMPUTE", "placeholder": True}
    )
    findings = style_lint.lint_board(b)
    ph = [f for f in findings if f["rule"] == "placeholder_visual"]
    assert ph and ph[0]["scene"] == b["scenes"][0]["scene_id"]


def test_lint_photo_board_has_no_imagery_findings():
    photo = REPO / "examples" / "photo_essay_storyboard.json"
    b = json.loads(photo.read_text(encoding="utf-8"))
    rules = {f["rule"] for f in style_lint.lint_board(b)}
    assert "no_subject_imagery" not in rules
    assert "placeholder_visual" not in rules


def test_lint_unused_assets_flagged_with_manifest(tmp_path):
    b = _board()
    b["scenes"][0]["elements"].append(
        {"type": "image", "src": "assets/shown.jpg", "attribution": "A"}
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"assets": [{"file": "shown.jpg"}, {"file": "never_shown.jpg"}]}),
        encoding="utf-8",
    )
    findings = style_lint.lint_board(b, manifest)
    unused = [f for f in findings if f["rule"] == "unused_assets"]
    assert unused and "never_shown.jpg" in unused[0]["message"]
    # without the manifest flag the rule stays silent
    assert not [f for f in style_lint.lint_board(b) if f["rule"] == "unused_assets"]
