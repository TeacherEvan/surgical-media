"""Offline tests for asset_wire — the image-first manifest→board wiring.

No network: manifests are synthetic dicts, boards are minimal JSON. Pins
the contract that fetched plates actually reach the screen with their
attribution, placeholder filler is stripped, and authored visuals are
never clobbered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import asset_wire as aw


def _assets() -> list[dict[str, Any]]:
    return [
        {
            "file": "01_emperor_penguin.jpg",
            "title": "Emperor penguin colony on the ice",
            "creator": "A. Photographer",
            "license": "by",
            "attribution": "A. Photographer — Emperor penguin colony · CC BY 4.0 · https://example.org/1",
        },
        {
            "file": "02_ice_shelf.jpg",
            "title": "Antarctic ice shelf at dusk",
            "creator": "B. Explorer",
            "license": "cc0",
            "attribution": "B. Explorer — Antarctic ice shelf · CC0 · https://example.org/2",
        },
    ]


def _board(width: int = 1080, height: int = 1920) -> dict[str, Any]:
    return {
        "meta": {"title": "wire test"},
        "format": {"width": width, "height": height, "fps": 30},
        "scenes": [
            {
                "scene_id": "s1",
                "archetype": "doc_essay",
                "duration_sec": 4.0,
                "narration": "The emperor penguin breeds through the antarctic winter.",
                "elements": [
                    {"type": "background", "color": "#0A0E17"},
                    {"type": "scaling_chart", "label": "COMPUTE", "placeholder": True},
                    {"type": "kinetic_captions"},
                ],
            },
            {
                "scene_id": "s2",
                "archetype": "geometry_rig",
                "duration_sec": 4.0,
                "narration": "Huddles rotate so every bird shares the cold.",
                "elements": [
                    {"type": "background", "color": "#050508"},
                    {"type": "stick_rig", "placeholder": True},
                    {"type": "kinetic_captions"},
                ],
            },
        ],
    }


def _wire(
    board: dict[str, Any] | None = None,
    assets: list[dict[str, Any]] | None = None,
    tmp_path: Path | None = None,
    subject: str = "",
    brief: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base = tmp_path or Path(".")
    return aw.wire_board(
        board if board is not None else _board(),
        assets if assets is not None else _assets(),
        manifest_dir=base,
        board_dir=base,
        subject=subject,
        brief=brief,
    )


# -- tokens / scoring ---------------------------------------------------------
def test_tokens_strips_stopwords_and_short_words() -> None:
    t = aw.tokens("The Emperor PENGUIN and the ice")
    assert "emperor" in t and "penguin" in t and "ice" in t
    assert "the" not in t and "and" not in t


def test_score_asset_keyword_overlap() -> None:
    a = _assets()[0]
    assert aw.score_asset(a, "emperor penguin colony") >= 2
    assert aw.score_asset(a, "completely unrelated subject") == 0


def test_pick_asset_prefers_best_unused_then_reuses() -> None:
    assets = _assets()
    best, reused = aw.pick_asset(assets, set(), "emperor penguin colony", 0)
    assert best is not None and best["file"] == "01_emperor_penguin.jpg"
    assert not reused
    used = {"01_emperor_penguin.jpg"}
    nxt, reused = aw.pick_asset(assets, used, "emperor penguin colony", 1)
    assert nxt is not None and nxt["file"] == "02_ice_shelf.jpg" and not reused
    both = {"01_emperor_penguin.jpg", "02_ice_shelf.jpg"}
    again, reused = aw.pick_asset(assets, both, "anything", 0)
    assert again is not None and reused
    assert aw.pick_asset([], set(), "x", 0) == (None, False)


# -- manifest loading ---------------------------------------------------------
def test_load_manifest_reads_assets(tmp_path: Path) -> None:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"assets": _assets()}), encoding="utf-8")
    assert len(aw.load_manifest(p)) == 2


def test_load_manifest_tolerates_missing_and_corrupt(tmp_path: Path) -> None:
    assert aw.load_manifest(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert aw.load_manifest(bad) == []
    arr = tmp_path / "arr.json"
    arr.write_text("[]", encoding="utf-8")
    assert aw.load_manifest(arr) == []
    nofile = tmp_path / "nofile.json"
    nofile.write_text(json.dumps({"assets": [{"title": "x"}, _assets()[0]]}))
    assert len(aw.load_manifest(nofile)) == 1


# -- image element construction -----------------------------------------------
def test_image_element_portrait_defaults_to_backdrop_blur(tmp_path: Path) -> None:
    el = aw.image_element(
        _assets()[0], manifest_dir=tmp_path, board_dir=tmp_path, width=1080, height=1920
    )
    assert el["type"] == "image"
    assert el["fit"] == "backdrop_blur"
    assert el["attribution_y"] == aw.PORTRAIT_CREDIT_Y
    assert el["attribution"] == _assets()[0]["attribution"]
    assert el["src"] == "01_emperor_penguin.jpg"
    assert el["box"] == [0, 0, 1080, 1920]


def test_image_element_landscape_defaults_to_cover(tmp_path: Path) -> None:
    el = aw.image_element(
        _assets()[0], manifest_dir=tmp_path, board_dir=tmp_path, width=1920, height=1080
    )
    assert el["fit"] == "cover"
    assert "attribution_y" not in el


def test_image_element_explicit_fit_and_attribution(tmp_path: Path) -> None:
    el = aw.image_element(
        _assets()[0],
        manifest_dir=tmp_path,
        board_dir=tmp_path,
        width=1080,
        height=1920,
        fit="contain",
        attribution="Custom credit",
    )
    assert el["fit"] == "contain"
    assert el["attribution"] == "Custom credit"


def test_image_element_src_relative_to_board(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "assets"
    manifest_dir.mkdir()
    board_dir = tmp_path / "out"
    board_dir.mkdir()
    el = aw.image_element(
        _assets()[0],
        manifest_dir=manifest_dir,
        board_dir=board_dir,
        width=1280,
        height=720,
    )
    assert el["src"] == "../assets/01_emperor_penguin.jpg"


# -- board wiring -------------------------------------------------------------
def test_wire_replaces_placeholder_filler_with_plate() -> None:
    wired, report = _wire()
    s1 = wired["scenes"][0]
    types = [e["type"] for e in s1["elements"]]
    assert "scaling_chart" not in types  # placeholder stripped
    assert types == ["background", "image", "kinetic_captions"]
    plate = s1["elements"][1]
    assert plate["src"] == "01_emperor_penguin.jpg"  # narration keyword match
    assert plate["attribution"]
    assert report[0]["action"] == "wired"


def test_wire_round_robins_when_pool_exhausted() -> None:
    board = _board()
    board["scenes"].append(
        {
            "scene_id": "s3",
            "archetype": "mixed",
            "duration_sec": 3.0,
            "narration": "The ice shelf glows at dusk.",
            "elements": [{"type": "background", "color": "#000000"}],
        }
    )
    wired, report = _wire(board)
    assert report[2]["action"] == "reused"
    assert wired["scenes"][2]["elements"][1]["type"] == "image"


def test_wire_keeps_authored_subject_visuals() -> None:
    board = _board()
    board["scenes"][0]["elements"] = [
        {"type": "svg", "svg": "<svg/>"},
        {"type": "kinetic_captions"},
    ]
    board["scenes"][1]["scene_spec"] = {"category": "orbital_or_field_3d"}
    board["scenes"][1]["elements"] = [{"type": "kinetic_captions"}]
    wired, report = _wire(board)
    assert [r["action"] for r in report] == ["kept", "kept"]
    assert wired["scenes"][0]["elements"][0]["type"] == "svg"


def test_wire_respects_opt_out_kinds() -> None:
    board = _board()
    board["scenes"][1]["visual"] = {"kind": "procedural"}
    wired, report = _wire(board)
    assert report[1]["action"] == "opt-out"
    assert wired["scenes"][1]["elements"][1]["type"] == "stick_rig"


def test_wire_explicit_image_with_manifest_match() -> None:
    board = _board()
    board["scenes"][0]["visual"] = {"image": "02_ice_shelf.jpg"}
    wired, report = _wire(board)
    plate = wired["scenes"][0]["elements"][1]
    assert plate["src"] == "02_ice_shelf.jpg"
    assert plate["attribution"] == _assets()[1]["attribution"]
    assert report[0]["action"] == "explicit"


def test_wire_explicit_image_outside_manifest_keeps_src_and_credit() -> None:
    board = _board()
    board["scenes"][0]["visual"] = {
        "image": "press/portrait.jpg",
        "attribution": "Press room — Portrait · licensed",
    }
    wired, report = _wire(board)
    plate = wired["scenes"][0]["elements"][1]
    assert plate["src"] == "press/portrait.jpg"
    assert plate["attribution"] == "Press room — Portrait · licensed"
    assert report[0]["attributed"] is True


def test_wire_no_assets_leaves_board_and_reports() -> None:
    wired, report = _wire(assets=[])
    assert all(r["action"] == "no-assets" for r in report)
    assert wired["scenes"][0]["elements"][1]["type"] == "scaling_chart"


def test_wire_does_not_mutate_input() -> None:
    board = _board()
    snapshot = json.dumps(board, sort_keys=True)
    _wire(board)
    assert json.dumps(board, sort_keys=True) == snapshot


def test_wire_subject_fallback_matching() -> None:
    board = _board()
    board["scenes"][0]["narration"] = "A remarkable bird endures the cold."
    wired, _ = _wire(board, subject="emperor penguin")
    assert wired["scenes"][0]["elements"][1]["src"] == "01_emperor_penguin.jpg"


def test_wire_landscape_board_uses_cover() -> None:
    wired, _ = _wire(_board(width=1920, height=1080))
    assert wired["scenes"][0]["elements"][1]["fit"] == "cover"


# -- brief visual anchors / assets -------------------------------------------
def test_asset_query_provenance_bridges_latin_binomial_titles() -> None:
    """Real Commons plates are titled 'Aptenodytes forsteri', not 'penguin'."""
    asset = {
        "file": "01_aptenodytes.jpg",
        "title": "Aptenodytes forsteri -Antarctica -blizzard-8.jpg",
        "query": "emperor penguin antarctica",
    }
    assert aw.score_asset(asset, "emperor penguin in the cold") >= 2
    assert aw.score_asset(asset, "industrial machinery factory") == 0


def test_brief_anchor_steers_plate_choice() -> None:
    board = _board()
    board["scenes"][0]["narration"] = "A bird stands on the ice."
    board["scenes"][1]["narration"] = "The cold water churns."
    assets = [
        {"file": "bird.jpg", "title": "penguin portrait", "attribution": "A"},
        {
            "file": "ice.jpg",
            "title": "glacier close-up",
            "attribution": "B",
        },
    ]
    brief = {
        "subject": "antarctica",
        "visual_anchors": [
            {"claim_index": 0, "primitive": "penguin portrait"},
            {"claim_index": 1, "primitive": "glacier close-up"},
        ],
    }
    wired, report = _wire(board, assets, subject="", brief=brief)
    assert wired["scenes"][0]["elements"][1]["src"] == "bird.jpg"
    assert wired["scenes"][1]["elements"][1]["src"] == "ice.jpg"
    assert report[0]["anchor"] == "penguin portrait"
    assert report[1]["anchor"] == "glacier close-up"


def test_brief_visual_assets_join_the_pool(tmp_path: Path) -> None:
    board = _board()
    (tmp_path / "press.jpg").write_bytes(b"fixture")
    brief = {
        "subject": "penguin",
        "visual_assets": [
            {
                "file": "press.jpg",
                "license": "by",
                "attribution": "Press — Portrait · licensed",
            }
        ],
    }
    wired, _ = aw.wire_board(
        board, [], manifest_dir=tmp_path, board_dir=tmp_path, brief=brief
    )
    assert wired["scenes"][0]["elements"][1]["src"] == "press.jpg"
    assert wired["scenes"][0]["elements"][1]["attribution"].startswith("Press")


def test_manifest_wins_over_duplicate_brief_asset(tmp_path: Path) -> None:
    (tmp_path / "same.jpg").write_bytes(b"fixture")
    brief = {"visual_assets": [{"file": "same.jpg", "attribution": "from brief"}]}
    wired, _ = aw.wire_board(
        _board(),
        [{"file": "same.jpg", "attribution": "from manifest", "query": "penguin"}],
        manifest_dir=tmp_path,
        board_dir=tmp_path,
        brief=brief,
    )
    assert wired["scenes"][0]["elements"][1]["attribution"] == "from manifest"


# -- CLI ----------------------------------------------------------------------
def test_cli_wires_and_reports(tmp_path: Path) -> None:
    board_p = tmp_path / "board.json"
    board_p.write_text(json.dumps(_board()), encoding="utf-8")
    manifest_p = tmp_path / "manifest.json"
    manifest_p.write_text(json.dumps({"assets": _assets()}), encoding="utf-8")
    out_p = tmp_path / "wired.json"
    report_p = tmp_path / "report.json"
    assert (
        aw.main(
            [
                "--board",
                str(board_p),
                "--manifest",
                str(manifest_p),
                "--out",
                str(out_p),
                "--report",
                str(report_p),
            ]
        )
        == 0
    )
    wired = json.loads(out_p.read_text(encoding="utf-8"))
    assert wired["scenes"][0]["elements"][1]["type"] == "image"
    assert len(json.loads(report_p.read_text(encoding="utf-8"))) == 2


def test_cli_empty_manifest_exits_2(tmp_path: Path) -> None:
    board_p = tmp_path / "board.json"
    board_p.write_text(json.dumps(_board()), encoding="utf-8")
    manifest_p = tmp_path / "manifest.json"
    manifest_p.write_text(json.dumps({"assets": []}), encoding="utf-8")
    assert (
        aw.main(
            [
                "--board",
                str(board_p),
                "--manifest",
                str(manifest_p),
                "--out",
                str(tmp_path / "w.json"),
            ]
        )
        == 2
    )


def test_cli_bad_board_exits_2(tmp_path: Path) -> None:
    board_p = tmp_path / "board.json"
    board_p.write_text("[]", encoding="utf-8")
    manifest_p = tmp_path / "manifest.json"
    manifest_p.write_text(json.dumps({"assets": _assets()}), encoding="utf-8")
    assert (
        aw.main(
            [
                "--board",
                str(board_p),
                "--manifest",
                str(manifest_p),
                "--out",
                str(tmp_path / "w.json"),
            ]
        )
        == 2
    )
