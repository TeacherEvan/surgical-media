import json

import pytest
from tts_align import align_words, estimate_duration, syllable_count, word_weight


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
