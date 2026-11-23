"""Tests for the local Kokoro voice engine (no model download required)."""

import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest
from kokoro_voice import (
    DEFAULT_VOICE,
    is_available,
    runtime_dir,
    runtime_python,
    weighted_words,
    word_weight,
)
from tts_align import main as align_main
from tts_align import synthesize_kokoro_voice


def test_default_voice_is_af_heart():
    assert DEFAULT_VOICE == "af_heart"


def test_runtime_dir_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KOKORO_HOME", str(tmp_path))
    assert runtime_dir() == tmp_path


def test_runtime_python_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KOKORO_PYTHON", str(tmp_path / "py"))
    assert runtime_python() == tmp_path / "py"


def test_is_available_requires_all_parts(monkeypatch, tmp_path):
    monkeypatch.setenv("KOKORO_HOME", str(tmp_path))
    monkeypatch.delenv("KOKORO_PYTHON", raising=False)
    assert not is_available()
    interpreter = tmp_path / "venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    assert not is_available()
    (tmp_path / "model_quantized.onnx").touch()
    assert not is_available()
    (tmp_path / "voices.npz").touch()
    assert is_available()


def test_word_weight_punctuation_bonus():
    assert word_weight("end.", 3) > word_weight("end", 3)
    assert word_weight("wait,", 4) > word_weight("wait", 4)


def test_weighted_words_is_contiguous_and_exact():
    words = weighted_words("one two three", 3.0, [3, 5, 2])
    assert words[0]["start"] == 0.0
    assert words[-1]["end"] == 3.0
    for prev, nxt in pairwise(words):
        assert abs(nxt["start"] - prev["end"]) < 1e-3


def test_weighted_words_uses_phoneme_length():
    words = weighted_words("a hippopotamus walked", 3.0, [1, 11, 5])
    spans = [w["end"] - w["start"] for w in words]
    assert spans[1] == max(spans)


def test_weighted_words_rejects_mismatch():
    with pytest.raises(ValueError):
        weighted_words("one two", 1.0, [1])


def test_weighted_words_empty():
    assert weighted_words("", 1.0, []) == []


def test_kokoro_helper_json_is_parsed(monkeypatch, tmp_path):
    payload = {
        "duration": 2.5,
        "words": [{"word": "hello", "start": 0.0, "end": 2.5}],
    }
    monkeypatch.setattr("tts_align.kokoro_runtime_python", lambda: Path("python"))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, json.dumps(payload), ""),
    )
    path, duration, words = synthesize_kokoro_voice("hello", "af_heart", tmp_path, "s1")
    assert path == tmp_path / "s1.wav"
    assert duration == 2.5
    assert words == payload["words"]


def test_kokoro_helper_bad_json_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr("tts_align.kokoro_runtime_python", lambda: Path("python"))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "not json", ""),
    )
    assert synthesize_kokoro_voice("hello", "af_heart", tmp_path, "s1") == (
        None,
        None,
        None,
    )


def test_auto_engine_uses_kokoro_when_installed(monkeypatch, tmp_path):
    script = tmp_path / "script.json"
    out = tmp_path / "board.json"
    script.write_text(
        json.dumps(
            {
                "title": "kokoro test",
                "scenes": [
                    {"scene_id": "s1", "narration": "Strings attached."},
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_words = [
        {"word": "Strings", "start": 0.0, "end": 0.5},
        {"word": "attached.", "start": 0.5, "end": 1.0},
    ]
    monkeypatch.setattr("tts_align.kokoro_available", lambda: True)
    monkeypatch.setattr(
        "tts_align.synthesize_kokoro_voice",
        lambda *a, **k: (tmp_path / "s1.wav", 1.0, fake_words),
    )
    argv = sys.argv
    try:
        sys.argv = [
            "tts_align.py",
            "--input",
            str(script),
            "--output",
            str(out),
            "--engine",
            "auto",
            "--aspect",
            "9:16",
        ]
        assert align_main() == 0
    finally:
        sys.argv = argv
    board = json.loads(out.read_text(encoding="utf-8"))
    assert board["meta"]["description"].endswith("Voice: kokoro/af_heart.")
    assert board["scenes"][0]["words"] == fake_words
