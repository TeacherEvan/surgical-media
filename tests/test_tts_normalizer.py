"""Tests for the stdlib-only, deterministic tts_normalizer utility."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from tts_normalizer import (
    main,
    normalize_script,
    normalize_text,
    number_to_words,
    year_to_words,
)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tts_normalizer.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI with list argv (never shell=True), capturing text output."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_iso_date():
    assert normalize_text("on 2026-11-21") == (
        "on November twenty first, twenty twenty six"
    )


def test_us_date():
    assert normalize_text("on 11/21/2026") == (
        "on November twenty first, twenty twenty six"
    )


@pytest.mark.parametrize(
    ("year", "spoken"),
    [
        (2026, "twenty twenty six"),
        (1984, "nineteen eighty four"),
        (2000, "two thousand"),
        (2010, "twenty ten"),
    ],
)
def test_year_forms(year: int, spoken: str):
    assert year_to_words(year) == spoken
    assert normalize_text(f"in {year}") == f"in {spoken}"


def test_year_inside_date_not_expanded_twice():
    once = normalize_text("2026-11-21")
    assert once.count("twenty twenty six") == 1
    assert normalize_text(once) == once


def test_currency_billion_and_rand_million():
    assert normalize_text("$3.2B") == "three point two billion dollars"
    assert normalize_text("R12.5m") == "twelve point five million rand"
    assert normalize_text("$5") == "five dollars"


def test_percent():
    assert normalize_text("12%") == "twelve percent"
    assert normalize_text("12.5%") == "twelve point five percent"


def test_hashtag_camelcase_and_allcaps():
    assert normalize_text("#BigTech") == "hash Big Tech"
    assert normalize_text("#AI") == "hash A I"


def test_mention():
    assert normalize_text("@handle") == "at handle"


def test_comma_number():
    assert normalize_text("1,200") == "one thousand two hundred"
    assert number_to_words(1200) == "one thousand two hundred"


def test_decimal_digit_by_digit():
    assert normalize_text("3.14") == "three point one four"
    assert normalize_text("3.2") == "three point two"


@pytest.mark.parametrize(
    ("ordinal", "spoken"),
    [
        ("1st", "first"),
        ("2nd", "second"),
        ("3rd", "third"),
        ("4th", "fourth"),
        ("21st", "twenty first"),
    ],
)
def test_ordinals(ordinal: str, spoken: str):
    assert normalize_text(ordinal) == spoken


def test_url_preserved():
    url = "https://example.com/2026-11-21/1,200?q=$5#AI"
    assert normalize_text(f"see {url} now") == f"see {url} now"


def test_embedded_digits_untouched():
    assert normalize_text("GPT4 and LLaMA3 shipped") == ("GPT4 and LLaMA3 shipped")


def test_no_double_spaces():
    assert "  " not in normalize_text("Meta  raised $3.2B  on  2026-11-21")


def test_idempotence_of_all_rules():
    text = (
        "Meta raised $3.2B on 2026-11-21 #AI. By 11/21/2026, 1,200 shares at "
        "3.14 each, up 12%, beat the 4th quarter #BigTech @handle."
    )
    once = normalize_text(text)
    assert normalize_text(once) == once


def test_nested_json_paths_and_structure_preserved():
    data = {
        "title": "2026 report",
        "beats": [
            {
                "narration": "on 2026-11-21",
                "text": "$5 and #AI",
                "meta": {"x": 42, "note": "12%"},
            }
        ],
        "note": "12%",
    }
    out, changes = normalize_script(data)
    assert out["title"] == "2026 report"
    assert out["beats"][0]["meta"] == {"x": 42, "note": "12%"}
    assert out["note"] == "12%"
    assert out["beats"][0]["narration"] == (
        "on November twenty first, twenty twenty six"
    )
    assert out["beats"][0]["text"] == "five dollars and hash A I"
    assert [c["path"] for c in changes] == [
        "beats/0/narration",
        "beats/0/text",
    ]


def test_report_contents(tmp_path: Path):
    script = tmp_path / "script.json"
    output = tmp_path / "spoken.json"
    report = tmp_path / "report.json"
    script.write_text(
        json.dumps({"beats": [{"narration": "on 2026-11-21"}]}),
        encoding="utf-8",
    )
    result = _run(
        "--input", str(script), "--output", str(output), "--report", str(report)
    )
    assert result.returncode == 0, result.stderr
    changes = json.loads(report.read_text(encoding="utf-8"))
    assert changes == [
        {
            "path": "beats/0/narration",
            "before": "on 2026-11-21",
            "after": "on November twenty first, twenty twenty six",
        }
    ]


def test_cli_emit_text_end_to_end(tmp_path: Path):
    # tmp_path keeps any incidental artifacts isolated from the repo root.
    result = _run("--text", "Meta raised $3.2B on 2026-11-21 #AI", "--emit-text")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "Meta raised three point two billion dollars on November twenty first, "
        "twenty twenty six hash A I"
    )


def test_cli_json_end_to_end(tmp_path: Path):
    script = tmp_path / "script.json"
    output = tmp_path / "spoken.json"
    script.write_text(
        json.dumps({"scenes": [{"text": "in 1984 it cost $5"}]}),
        encoding="utf-8",
    )
    result = _run("--input", str(script), "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert "1 change" in result.stdout
    spoken = json.loads(output.read_text(encoding="utf-8"))
    assert spoken["scenes"][0]["text"] == "in nineteen eighty four it cost five dollars"


def test_cli_main_uses_monkeypatched_argv(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["tts_normalizer.py", "--text", "3.14", "--emit-text"],
    )
    assert main() == 0
    assert capsys.readouterr().out.strip() == "three point one four"


def test_invalid_input_missing_file_exits_2(tmp_path: Path):
    result = _run(
        "--input", str(tmp_path / "missing.json"), "--output", str(tmp_path / "o.json")
    )
    assert result.returncode == 2


def test_invalid_input_malformed_json_exits_2(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    result = _run("--input", str(bad), "--output", str(tmp_path / "o.json"))
    assert result.returncode == 2
