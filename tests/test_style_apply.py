"""Offline tests for generation-side style application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pipeline_preflight as pf
import storyboard
import style_apply


def _intake(style: str = "comedic", platform: str = "tiktok") -> dict[str, Any]:
    return pf.build_intake(25, style, platform, "Test")


def _board(intro_sec: float = 8.0) -> dict[str, Any]:
    return {
        "meta": {"title": "Draft"},
        "format": {"width": 1920, "height": 1080, "fps": 30},
        "scenes": [
            {
                "scene_id": "hook",
                "archetype": "mixed",
                "duration_sec": intro_sec,
                "elements": [{"type": "background", "color": "#000000"}],
                "words": [
                    {"word": "one", "start": 0.0, "end": 2.0},
                    {"word": "two", "start": 6.0, "end": 8.0},
                ],
                "sfx_events": [{"t_sec": 7.0, "sfx": "pop"}],
            },
            {
                "scene_id": "body",
                "archetype": "doc_essay",
                "duration_sec": 12.0,
                "elements": [{"type": "background", "color": "#111111"}],
            },
            {
                "scene_id": "outro",
                "archetype": "mixed",
                "duration_sec": 3.0,
                "elements": [{"type": "background", "color": "#222222"}],
            },
        ],
    }


def test_applies_presets_budgets_and_format() -> None:
    styled, changes = style_apply.apply_style(_board(), _intake())
    assert styled["style"]["preset"] == "punchy_pop"
    assert styled["platform"]["preset"] == "shorts_tiktok_reels"
    assert styled["platform"]["caption_style"] == "sticker"
    assert styled["platform"]["hook_max_sec"] == 3.0
    assert styled["format"] == {"width": 1080, "height": 1920, "fps": 30}
    assert any(c["path"] == "style/preset" for c in changes)


def test_scene_archetypes_follow_matrix() -> None:
    styled, _ = style_apply.apply_style(_board(), _intake())
    assert [s["archetype"] for s in styled["scenes"]] == [
        "geometry_rig",
        "geometry_rig",
        "geometry_rig",
    ]


def test_hybrid_uses_tonal_arc_rotation() -> None:
    styled, _ = style_apply.apply_style(_board(), _intake("all of the above"))
    assert styled["style"]["preset"] == "punchy_pop"
    assert [s["archetype"] for s in styled["scenes"]] == [
        "code_report",
        "geometry_rig",
        "doc_essay",
    ]


def test_intro_clamp_rescales_word_and_sfx_times() -> None:
    styled, changes = style_apply.apply_style(_board(8.0), _intake())
    first = styled["scenes"][0]
    assert first["duration_sec"] == 1.75  # midpoint of 0.5..3.0
    assert first["words"][-1]["end"] <= 1.75
    assert first["sfx_events"][0]["t_sec"] <= 1.75
    assert any(c["path"] == "scenes/0/duration_sec" for c in changes)


def test_start_sec_recomputed_after_intro_clamp() -> None:
    board = _board(8.0)
    for scene, start in zip(board["scenes"], (0.0, 8.0, 20.0)):
        scene["start_sec"] = start
    styled, changes = style_apply.apply_style(board, _intake())
    assert [s["start_sec"] for s in styled["scenes"]] == [0.0, 1.75, 13.75]
    assert any(c["path"] == "scenes/*/start_sec" for c in changes)
    assert storyboard.total_duration(styled) == 16.75


def test_outro_gets_credit_tag_and_cta_placeholder() -> None:
    styled, changes = style_apply.apply_style(_board(), _intake())
    last = styled["scenes"][-1]
    assert any(
        e.get("type") == "source_tag" for e in last["elements"] if isinstance(e, dict)
    )
    assert "[CTA: follow/subscribe]" in last["narration"]
    assert any(c["path"] == "scenes/-1/elements/+source_tag" for c in changes)


def test_existing_credits_and_cta_are_preserved() -> None:
    board = _board()
    board["scenes"][-1]["elements"].append(
        {"type": "source_tag", "text": "Source: Real Outlet (Nov 2026)"}
    )
    board["scenes"][-1]["narration"] = "Subscribe for the next one."
    styled, changes = style_apply.apply_style(board, _intake())
    assert not any(c["path"].endswith("+source_tag") for c in changes)
    assert styled["scenes"][-1]["narration"] == "Subscribe for the next one."
    assert styled["scenes"][-1]["elements"][-1]["text"].startswith(
        "Source: Real Outlet"
    )


def test_apply_is_idempotent() -> None:
    once, _first_changes = style_apply.apply_style(_board(), _intake())
    twice, second_changes = style_apply.apply_style(once, _intake())
    assert twice == once
    assert second_changes == []


def test_no_factual_claim_is_invented() -> None:
    board = _board()
    styled, _ = style_apply.apply_style(board, _intake())
    body_before = board["scenes"][1]
    body_after = styled["scenes"][1]
    assert body_after.get("narration") == body_before.get("narration")
    assert "[CTA:" not in body_after.get("narration", "")


def test_applied_example_board_validates() -> None:
    example = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "tri_archetype_storyboard.json"
    )
    board = json.loads(example.read_text(encoding="utf-8"))
    styled, _ = style_apply.apply_style(board, _intake())
    assert storyboard.validate_storyboard(styled) == []


def test_cli_writes_outputs(tmp_path: Path) -> None:
    intake_path = tmp_path / "intake.json"
    board_path = tmp_path / "board.json"
    out_path = tmp_path / "storyboard.json"
    report_path = tmp_path / "changes.json"
    intake_path.write_text(json.dumps(_intake()), encoding="utf-8")
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    assert (
        style_apply.main(
            [
                "--intake",
                str(intake_path),
                "--board",
                str(board_path),
                "--out",
                str(out_path),
                "--report",
                str(report_path),
            ]
        )
        == 0
    )
    assert (
        json.loads(out_path.read_text(encoding="utf-8"))["style"]["preset"]
        == "punchy_pop"
    )
    assert len(json.loads(report_path.read_text(encoding="utf-8"))) > 0


def test_cli_rejects_missing_scenes(tmp_path: Path) -> None:
    intake_path = tmp_path / "intake.json"
    board_path = tmp_path / "board.json"
    intake_path.write_text(json.dumps(_intake()), encoding="utf-8")
    board_path.write_text(json.dumps({"meta": {"title": "x"}}), encoding="utf-8")
    assert (
        style_apply.main(
            [
                "--intake",
                str(intake_path),
                "--board",
                str(board_path),
                "--out",
                str(tmp_path / "out.json"),
            ]
        )
        == 2
    )
