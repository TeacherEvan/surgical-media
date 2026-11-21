"""Offline tests for the executable intake/style/structure preflight gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pipeline_preflight as pf
import pytest


def _brief() -> dict[str, Any]:
    return {
        "facts": [
            {"claim_id": "claim-a1b2c3d4", "source": "https://example.org/a"},
            {"claim_id": "claim-b1b2c3d4", "source": "https://example.org/b"},
            {"claim_id": "claim-c1b2c3d4", "source": "https://example.org/c"},
        ]
    }


def _board(
    style_preset: str = "punchy_pop",
    platform_preset: str = "shorts_tiktok_reels",
    intro_sec: float = 2.0,
) -> dict[str, Any]:
    return {
        "meta": {"title": "Test"},
        "format": {"width": 1080, "height": 1920, "fps": 30},
        "style": {"preset": style_preset},
        "platform": {"preset": platform_preset},
        "scenes": [
            {
                "scene_id": "hook",
                "archetype": "geometry_rig",
                "duration_sec": intro_sec,
                "elements": [
                    {
                        "type": "kinetic_captions",
                        "words": [{"word": "hook", "start": 0.0, "end": 1.0}],
                    }
                ],
                "narration": "Here is the hook.",
            },
            {
                "scene_id": "body",
                "archetype": "doc_essay",
                "duration_sec": 20.0,
                "elements": [{"type": "background", "color": "#0A0E17"}],
            },
            {
                "scene_id": "outro",
                "archetype": "code_report",
                "duration_sec": 3.0,
                "elements": [
                    {
                        "type": "source_tag",
                        "text": "Source: Example (Nov 2026)",
                        "corner": "bl",
                    }
                ],
                "narration": "Follow for more;",
            },
        ],
    }


# -- intake resolution ------------------------------------------------------
def test_intake_maps_style_and_platform() -> None:
    intake = pf.build_intake(60, "comedic", "tiktok", "Demo")
    assert intake["style"] == "comedic"
    assert intake["style_preset"] == "punchy_pop"
    assert intake["archetype"] == "geometry_rig"
    assert intake["platform_preset"] == "shorts_tiktok_reels"
    assert intake["format"] == {"width": 1080, "height": 1920, "fps": 30}
    assert intake["intro"] == {
        "kind": "hook",
        "min_sec": 0.5,
        "max_sec": 3.0,
    }
    assert intake["outro"]["loop"] is True
    assert intake["cadence_sec"] == [0.8, 1.5]


def test_long_form_intake_uses_cold_open_window() -> None:
    intake = pf.build_intake(300, "serious", "youtube_long")
    assert intake["platform_preset"] == "youtube_long"
    assert intake["intro"]["min_sec"] == 3.0
    assert intake["intro"]["max_sec"] == 10.0
    assert intake["outro"]["loop"] is False
    assert intake["format"]["width"] == 1920


def test_hybrid_style_exposes_arc() -> None:
    intake = pf.build_intake(90, "all of the above", "shorts")
    assert intake["style"] == "all_of_the_above"
    assert intake["arc"][0].startswith("catchy")
    assert intake["arc"][-1].startswith("poetic")


@pytest.mark.parametrize(
    ("time", "style", "platform"),
    [
        (60, "unknown", "tiktok"),
        (60, "comedic", "unknown"),
        (900, "comedic", "facebook_reels"),
        (-1, "comedic", "tiktok"),
    ],
)
def test_intake_rejects_bad_inputs(time: float, style: str, platform: str) -> None:
    with pytest.raises(ValueError):
        pf.build_intake(time, style, platform)


# -- structural checks ------------------------------------------------------
def test_intro_window_enforced() -> None:
    ok, detail = pf.check_intro(
        _board()["scenes"], pf.build_intake(60, "comedic", "tiktok")["intro"]
    )
    assert ok and "hook" in detail
    ok, _ = pf.check_intro(
        _board(intro_sec=8.0)["scenes"],
        pf.build_intake(60, "comedic", "tiktok")["intro"],
    )
    assert not ok


def test_outro_requires_cta_and_credits() -> None:
    scenes = _board()["scenes"]
    ok, detail = pf.check_outro(
        scenes, pf.build_intake(60, "comedic", "tiktok")["outro"]
    )
    assert ok and "cta=True" in detail and "credits=True" in detail
    no_credits = json.loads(json.dumps(scenes))
    no_credits[-1]["elements"] = [{"type": "background", "color": "#000000"}]
    ok, _ = pf.check_outro(
        no_credits, pf.build_intake(60, "comedic", "tiktok")["outro"]
    )
    assert not ok


def test_originality_brief_gate() -> None:
    ok, detail = pf.check_brief(_brief())
    assert ok and "3 sourced" in detail
    thin = {"facts": [{"claim_id": "claim-a1b2c3d4", "source": "x"}]}
    ok, _ = pf.check_brief(thin)
    assert not ok


def test_full_board_passes() -> None:
    intake = pf.build_intake(25, "comedic", "tiktok")
    report = pf.check_board(_board(), intake, _brief())
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]
    assert {c["check"] for c in report["checks"]} >= {
        "storyboard_valid",
        "format_matches_intake",
        "style_preset_matches",
        "platform_preset_matches",
        "topic_matched_intro",
        "payoff_outro",
        "duration_within_cap",
        "originality_brief",
    }


def test_wrong_style_preset_fails() -> None:
    intake = pf.build_intake(25, "comedic", "tiktok")
    report = pf.check_board(_board(style_preset="soft_clay"), intake, _brief())
    assert not report["ok"]
    assert not next(
        c for c in report["checks"] if c["check"] == "style_preset_matches"
    )["ok"]


# -- CLI --------------------------------------------------------------------
def test_cli_intake_mode_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "intake.json"
    assert (
        pf.main(
            [
                "--time",
                "60",
                "--style",
                "catchy",
                "--platform",
                "shorts",
                "--intake-out",
                str(out),
            ]
        )
        == 0
    )
    assert json.loads(out.read_text(encoding="utf-8"))["style"] == "catchy"


def test_cli_board_mode_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intake = pf.build_intake(25, "comedic", "tiktok")
    intake_path = tmp_path / "intake.json"
    intake_path.write_text(json.dumps(intake), encoding="utf-8")
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    brief_path = tmp_path / "brief.json"
    brief_path.write_text(json.dumps(_brief()), encoding="utf-8")

    assert (
        pf.main(
            [
                "--board",
                str(board_path),
                "--intake",
                str(intake_path),
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(_board(intro_sec=9.0)), encoding="utf-8")
    assert (
        pf.main(
            [
                "--board",
                str(bad_path),
                "--intake",
                str(intake_path),
                "--brief",
                str(brief_path),
            ]
        )
        == 3
    )
    assert "topic_matched_intro" in capsys.readouterr().err
