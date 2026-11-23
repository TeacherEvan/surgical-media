"""Tests for multi-voice casting (tts_align voices-map resolution)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tts_align


def _script(scenes, voices=None):
    script = {"scenes": scenes}
    if voices:
        script["voices"] = voices
    return script


def _scene(sid, text="some narration text"):
    return {"scene_id": sid, "narration": text}


def _recorder(seen):
    def _fake(narration, voice, *a, **k):
        seen.append(voice)
        return (None, 1.0, None)

    return _fake
    schema = json.loads(
        (Path(__file__).parent.parent / "schemas" / "script.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["voices"]["type"] == "object"


def test_scene_voice_override_wins(monkeypatch, tmp_path):
    script = _script(
        [_scene("hook"), _scene("remark"), _scene("other")],
        voices={"hook": "en-GB-George-neural", "remark": "en-US-Jenny-neural"},
    )
    path = tmp_path / "script.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    seen: list[str] = []
    monkeypatch.setattr(tts_align, "synthesize_voice", _recorder(seen))
    out = tmp_path / "board.json"
    rc = tts_align.main(
        [
            "--input",
            str(path),
            "--output",
            str(out),
            "--engine",
            "edge",
            "--media-dir",
            str(tmp_path / "audio"),
        ]
    )
    assert rc == 0
    assert seen == [
        "en-GB-George-neural",
        "en-US-Jenny-neural",
        "en-US-ChristopherNeural",
    ], seen


def test_cli_voice_wins_over_script_voice(monkeypatch, tmp_path):
    script = {"voice": "en-GB-Abbi-neural", "scenes": [_scene("hook")]}
    path = tmp_path / "script.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    seen: list[str] = []
    monkeypatch.setattr(tts_align, "synthesize_voice", _recorder(seen))
    out = tmp_path / "board.json"
    rc = tts_align.main(
        [
            "--input",
            str(path),
            "--output",
            str(out),
            "--engine",
            "edge",
            "--voice",
            "en-AU-Natasha-neural",
        ]
    )
    assert rc == 0
    assert seen == ["en-AU-Natasha-neural"], seen


def test_scene_override_beats_cli(monkeypatch, tmp_path):
    script = _script([_scene("hook")], voices={"hook": "en-GB-George-neural"})
    path = tmp_path / "script.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    seen: list[str] = []
    monkeypatch.setattr(tts_align, "synthesize_voice", _recorder(seen))
    out = tmp_path / "board.json"
    rc = tts_align.main(
        [
            "--input",
            str(path),
            "--output",
            str(out),
            "--engine",
            "edge",
            "--voice",
            "en-AU-Natasha-neural",
        ]
    )
    assert rc == 0
    assert seen == ["en-GB-George-neural"], seen


def test_script_voice_wins_over_default(monkeypatch, tmp_path):
    script = {"voice": "en-GB-Abbi-neural", "scenes": [_scene("only")]}
    path = tmp_path / "script.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    seen: list[str] = []
    monkeypatch.setattr(tts_align, "synthesize_voice", _recorder(seen))
    out = tmp_path / "board.json"
    rc = tts_align.main(
        ["--input", str(path), "--output", str(out), "--engine", "edge"]
    )
    assert rc == 0
    assert seen == ["en-GB-Abbi-neural"], seen
