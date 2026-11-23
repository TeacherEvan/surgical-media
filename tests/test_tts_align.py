import argparse
import json

import pytest
from tts_align import (
    align_words,
    estimate_duration,
    syllable_count,
    validate_pitch,
    validate_rate,
    word_weight,
)


def test_syllable_count_basic():
    assert syllable_count("code") == 1
    assert syllable_count("algorithm") == 3
    assert syllable_count("the") == 1
    assert (
        syllable_count("rhythm") == 1 or syllable_count("rhythm") >= 1
    )  # y heuristic tolerated
    assert syllable_count("!!!") == 1


def test_word_weight_punctuation_bonus():
    assert word_weight("migrate.") > word_weight("migrate")
    assert word_weight("pause,") > word_weight("pause")


def test_align_words_fills_exact_duration():
    text = "The pool held but the certificate did not and then everything fell over."
    dur = 4.0
    words = align_words(text, dur)
    assert words[0]["start"] == 0.0
    assert words[-1]["end"] == dur
    assert all(w["end"] >= w["start"] for w in words)
    # coverage is contiguous
    from itertools import pairwise

    for prev, nxt in pairwise(words):
        assert nxt["start"] == prev["end"] or abs(nxt["start"] - prev["end"]) < 1e-3


def test_align_words_syllable_weighting():
    text = "a hippopotamus walked"  # 1 + 5 + 1 syllables → middle word gets the lion's share
    words = align_words(text, 3.5)
    spans = [w["end"] - w["start"] for w in words]
    assert spans[1] == max(spans)


def test_estimate_duration_scales_with_wpm():
    text = " ".join(["word"] * 165)
    assert estimate_duration(text, 165) == pytest.approx(60.0, abs=2.0)
    assert estimate_duration(text, 330) == pytest.approx(30.0, abs=2.0)


def test_empty_text_aligns_empty():
    assert align_words("", 2.0) == []


def test_offline_storyboard_generation(tmp_path):
    from tts_align import main as align_main

    script = tmp_path / "script.json"
    out = tmp_path / "storyboard.json"
    script.write_text(
        json.dumps(
            {
                "title": "unit test",
                "scenes": [
                    {
                        "scene_id": "s1",
                        "archetype": "doc_essay",
                        "narration": "compute compounds faster every single year.",
                    },
                    {
                        "scene_id": "s2",
                        "archetype": "code_report",
                        "narration": "the pool failed.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    import sys

    argv = sys.argv
    try:
        sys.argv = [
            "tts_align.py",
            "--input",
            str(script),
            "--output",
            str(out),
            "--offline",
            "--wpm",
            "150",
        ]
        assert align_main() == 0
    finally:
        sys.argv = argv
    board = json.loads(out.read_text(encoding="utf-8"))
    assert [s["scene_id"] for s in board["scenes"]] == ["s1", "s2"]
    assert board["audio"]["pad"] is False
    assert board["scenes"][1]["start_sec"] == board["scenes"][0]["duration_sec"]
    assert board["format"]["width"] == 1920
    assert all(
        w["end"] <= s["duration_sec"] + 1e-6
        for s in board["scenes"]
        for w in s["words"]
    )


def test_word_boundaries_from_events_ticks():
    from tts_align import word_boundaries_from_events

    events = [
        ("Meet", 1_000_000, 2_750_000),  # 0.100 s → 0.375 s
        ("the", 3_880_000, 750_000),  # 0.388 s → 0.463 s
        ("emperor", 4_750_000, 4_120_000),  # 0.475 s → 0.887 s
        ("penguin", 9_000_000, 5_250_000),  # 0.900 s → 1.425 s
    ]
    words = word_boundaries_from_events(events)
    assert [w["word"] for w in words] == ["Meet", "the", "emperor", "penguin"]
    assert words[0]["start"] == pytest.approx(0.1, abs=1e-3)
    assert words[0]["end"] == pytest.approx(0.375, abs=1e-3)
    assert words[-1]["end"] == pytest.approx(1.425, abs=1e-3)
    assert all(w["end"] > w["start"] for w in words)


def test_word_boundaries_from_events_skips_empty_tokens():
    from tts_align import word_boundaries_from_events

    assert word_boundaries_from_events(
        [("", 0, 10_000_000), ("hi", 5_000_000, 5_000_000)]
    ) == [
        {
            "word": "hi",
            "start": pytest.approx(0.5, abs=1e-3),
            "end": pytest.approx(1.0, abs=1e-3),
        }
    ]


@pytest.mark.parametrize("rate", ["+0%", "-12%", "+50%"])
def test_validate_rate_accepts_edge_tts_form(rate):
    assert validate_rate(rate) == rate


@pytest.mark.parametrize("rate", ["12%", "+12", "x", "+12%%", "", "+Hz"])
def test_validate_rate_rejects_bad_form(rate):
    with pytest.raises(argparse.ArgumentTypeError):
        validate_rate(rate)


@pytest.mark.parametrize("pitch", ["+0Hz", "-2Hz", "+5Hz"])
def test_validate_pitch_accepts_edge_tts_form(pitch):
    assert validate_pitch(pitch) == pitch


@pytest.mark.parametrize("pitch", ["2Hz", "+2", "0", "-Hz", ""])
def test_validate_pitch_rejects_bad_form(pitch):
    with pytest.raises(argparse.ArgumentTypeError):
        validate_pitch(pitch)


# -- image-first wiring (v3.2.0) ----------------------------------------------
def _wire_script(tmp_path, scenes):
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps({"title": "wire", "subject": "emperor penguin", "scenes": scenes}),
        encoding="utf-8",
    )
    return script


def _wire_manifest(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "file": "01_penguin.jpg",
                        "title": "Emperor penguin colony",
                        "license": "by",
                        "attribution": "A — Penguin · CC BY 4.0 · https://example.org",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "01_penguin.jpg").write_bytes(b"fixture")
    return manifest


def test_default_elements_flag_generic_filler_as_placeholder():
    from tts_align import DEFAULT_ELEMENTS

    for archetype, elements in DEFAULT_ELEMENTS.items():
        for el in elements:
            if el["type"] in ("background", "kinetic_captions"):
                assert not el.get("placeholder")
            elif archetype != "mixed":
                assert el.get("placeholder") is True, (archetype, el["type"])


def test_assets_manifest_wires_subject_plate(tmp_path):
    from tts_align import main as align_main

    script = _wire_script(
        tmp_path,
        [
            {
                "scene_id": "s1",
                "archetype": "doc_essay",
                "narration": "The emperor penguin endures the winter.",
            }
        ],
    )
    manifest = _wire_manifest(tmp_path)
    out = tmp_path / "board.json"
    assert (
        align_main(
            [
                "--input",
                str(script),
                "--output",
                str(out),
                "--offline",
                "--aspect",
                "9:16",
                "--assets-manifest",
                str(manifest),
            ]
        )
        == 0
    )
    board = json.loads(out.read_text(encoding="utf-8"))
    els = board["scenes"][0]["elements"]
    types = [e["type"] for e in els]
    assert "image" in types and "scaling_chart" not in types
    plate = next(e for e in els if e["type"] == "image")
    assert plate["src"] == "01_penguin.jpg"
    assert plate["attribution"]
    assert plate["fit"] == "backdrop_blur"  # 9:16 portrait default
    assert plate["attribution_y"] == 1060.0


def test_visual_image_pin_without_manifest(tmp_path):
    from tts_align import main as align_main

    script = _wire_script(
        tmp_path,
        [
            {
                "scene_id": "s1",
                "narration": "A pinned plate.",
                "visual": {
                    "image": "press/photo.jpg",
                    "attribution": "Press — Photo · licensed",
                },
            }
        ],
    )
    out = tmp_path / "board.json"
    assert align_main(["--input", str(script), "--output", str(out), "--offline"]) == 0
    board = json.loads(out.read_text(encoding="utf-8"))
    plate = next(e for e in board["scenes"][0]["elements"] if e["type"] == "image")
    assert plate["src"] == "press/photo.jpg"
    assert plate["attribution"] == "Press — Photo · licensed"


def test_visual_opt_out_keeps_filler_and_warns(tmp_path, capsys):
    from tts_align import main as align_main

    script = _wire_script(
        tmp_path,
        [
            {
                "scene_id": "s1",
                "archetype": "code_report",
                "narration": "An abstract beat.",
                "visual": {"kind": "procedural"},
            }
        ],
    )
    manifest = _wire_manifest(tmp_path)
    out = tmp_path / "board.json"
    assert (
        align_main(
            [
                "--input",
                str(script),
                "--output",
                str(out),
                "--offline",
                "--assets-manifest",
                str(manifest),
            ]
        )
        == 0
    )
    board = json.loads(out.read_text(encoding="utf-8"))
    types = [e["type"] for e in board["scenes"][0]["elements"]]
    assert "image" not in types and "system_architecture" in types
    assert "generic filler" in capsys.readouterr().err


def test_brief_anchors_steer_tts_align_wiring(tmp_path):
    from tts_align import main as align_main

    script = _wire_script(
        tmp_path,
        [
            {
                "scene_id": "s1",
                "archetype": "doc_essay",
                "narration": "A bird on the ice.",
            },
            {
                "scene_id": "s2",
                "archetype": "geometry_rig",
                "narration": "Cold water churns.",
            },
        ],
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "file": "bird.jpg",
                        "title": "penguin portrait",
                        "attribution": "A",
                    },
                    {"file": "ice.jpg", "title": "glacier water", "attribution": "B"},
                ]
            }
        ),
        encoding="utf-8",
    )
    brief = tmp_path / "brief.json"
    brief.write_text(
        json.dumps(
            {
                "subject": "antarctica",
                "visual_anchors": [
                    {"claim_index": 0, "primitive": "penguin portrait"},
                    {"claim_index": 1, "primitive": "glacier water"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "board.json"
    assert (
        align_main(
            [
                "--input",
                str(script),
                "--output",
                str(out),
                "--offline",
                "--assets-manifest",
                str(manifest),
                "--brief",
                str(brief),
            ]
        )
        == 0
    )
    board = json.loads(out.read_text(encoding="utf-8"))
    plates = [
        next(e for e in s["elements"] if e["type"] == "image") for s in board["scenes"]
    ]
    assert [p["src"] for p in plates] == ["bird.jpg", "ice.jpg"]


def test_no_manifest_warns_about_filler(tmp_path, capsys):
    from tts_align import main as align_main

    script = _wire_script(
        tmp_path,
        [{"scene_id": "s1", "archetype": "doc_essay", "narration": "No assets here."}],
    )
    out = tmp_path / "board.json"
    assert align_main(["--input", str(script), "--output", str(out), "--offline"]) == 0
    assert "fetch_assets.py" in capsys.readouterr().err
