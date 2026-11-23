"""Offline tests for per-beat imagery acquisition (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import fetch_scene_assets as fsa


def _script() -> dict[str, Any]:
    return {
        "title": "Penguins",
        "subject": "emperor penguin",
        "scenes": [
            {
                "scene_id": "s1",
                "narration": "Meet the emperor penguin on the ice.",
                "visual": {"query": "emperor penguin colony"},
            },
            {
                "scene_id": "s2",
                "narration": "The emperor penguin huddles against the winter wind.",
            },
            {
                "scene_id": "s3",
                "narration": "Watch the penguin slide into the freezing ocean water.",
            },
            {
                "scene_id": "s4",
                "narration": "Follow for more about the emperor penguin.",
            },
        ],
    }


def test_explicit_visual_query_wins() -> None:
    out = fsa.derive_queries(_script())
    assert out[0] == {"scene_id": "s1", "query": "emperor penguin colony"}


def test_auto_query_drops_stopwords_and_ranks_informative_words() -> None:
    out = fsa.derive_queries(_script())
    q2 = out[1]["query"]
    assert "winter" in q2 and "huddles" in q2
    assert "the" not in q2.lower() and "watch" not in q2.lower()


def test_duplicate_queries_collapse() -> None:
    data = {
        "subject": "penguin",
        "scenes": [
            {"scene_id": "a", "narration": "A penguin walks."},
            {"scene_id": "b", "narration": "A penguin walks."},
        ],
    }
    out = fsa.derive_queries(data)
    assert len(out) == 1 and out[0]["scene_id"] == "a"


def test_subject_fills_empty_narration() -> None:
    data = {
        "subject": "emperor penguin",
        "scenes": [{"scene_id": "a", "narration": "the and for are"}],
    }
    assert fsa.derive_queries(data)[0]["query"] == "emperor penguin"


def test_fetch_all_calls_each_query_and_reports_failures(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    calls: list[str] = []
    outcomes = [0, 2, 0]

    def fake(query: str, *args: Any, **kwargs: Any) -> int:
        calls.append(query)
        return outcomes[len(calls) - 1]

    monkeypatch.setattr(fsa.fetch_assets, "download_assets", fake)
    queries = [{"scene_id": "a", "query": "penguin"}, {"scene_id": "b", "query": "ice"}]
    assert fsa.fetch_all(queries, tmp_path / "assets", 3, 800, 30.0, False) == 0
    assert calls == ["penguin", "ice"]
    assert "no imagery for 'b'" in capsys.readouterr().err


def test_failed_beat_retries_with_broad_subject(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[str] = []
    outcomes = {"specific": 2, "emperor penguin": 0}

    def fake(query: str, *args: Any, **kwargs: Any) -> int:
        calls.append(query)
        return outcomes.get(query, 2)

    monkeypatch.setattr(fsa.fetch_assets, "download_assets", fake)
    assert (
        fsa.fetch_all(
            [{"scene_id": "a", "query": "specific"}],
            tmp_path / "assets",
            3,
            800,
            30.0,
            False,
            fallback="emperor penguin",
        )
        == 0
    )
    assert calls == ["specific", "emperor penguin"]


def test_fetch_all_fails_when_every_query_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(fsa.fetch_assets, "download_assets", lambda *a, **k: 2)
    assert (
        fsa.fetch_all(
            [{"scene_id": "a", "query": "x"}], tmp_path / "assets", 3, 800, 30.0, False
        )
        == 2
    )


def test_cli_dry_run_prints_plan(tmp_path: Path, capsys: Any) -> None:
    script = tmp_path / "script.json"
    script.write_text(json.dumps(_script()), encoding="utf-8")
    assert (
        fsa.main(
            ["--input", str(script), "--out-dir", str(tmp_path / "assets"), "--dry-run"]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert len(plan) >= 2 and plan[0]["query"] == "emperor penguin colony"


def test_cli_bad_input_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    assert fsa.main(["--input", str(bad)]) == 2
