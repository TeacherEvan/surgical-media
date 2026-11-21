"""Offline tests for the executable Step 2 spec-refresh / drift gate."""

from __future__ import annotations

import io
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import spec_refresh as sr


def _real_text() -> str:
    return sr.DEFAULT_DOC.read_text(encoding="utf-8")


def _write_real(tmp_path: Path) -> Path:
    path = tmp_path / "spec.md"
    path.write_text(_real_text(), encoding="utf-8")
    return path


def _report_and_err(capsys: pytest.CaptureFixture[str]) -> tuple[dict[str, Any], str]:
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


# -- baseline contract -------------------------------------------------------
def test_baseline_shape_and_compilable_needles() -> None:
    assert isinstance(sr.BASELINE, dict)
    assert len(sr.BASELINE) >= 15
    for name, entry in sr.BASELINE.items():
        assert isinstance(name, str) and name
        assert isinstance(entry, tuple) and len(entry) == 2
        needle, description = entry
        assert isinstance(needle, str) and needle
        assert isinstance(description, str) and description
        re.compile(needle)


def test_baseline_covers_required_fact_groups() -> None:
    assert {c for c in sr.BASELINE if c.startswith("license_")} == {
        "license_kokoro",
        "license_apache",
        "license_xtts",
        "license_remotion",
        "license_remotion_price",
    }
    assert sr.BASELINE["baseline_date"][0] == re.escape("2026-11-21")


@pytest.mark.parametrize("name", sorted(sr.BASELINE))
def test_every_baseline_needle_matches_real_doc(name: str) -> None:
    needle = sr.BASELINE[name][0]
    assert re.search(needle, _real_text()) is not None, name


# -- local drift detection ---------------------------------------------------
def test_real_doc_passes_check_doc() -> None:
    report = sr.check_doc(_real_text())
    assert report["ok"] is True
    assert report["baseline_date"] == "2026-11-21"
    assert len(report["checks"]) == len(sr.BASELINE)
    assert all(c["ok"] for c in report["checks"])
    assert report["drift"] == []


def test_drift_when_license_needle_removed() -> None:
    original = _real_text()
    mutated = original.replace("Kokoro-82M", "Kokoro-82X")
    assert mutated != original
    report = sr.check_doc(mutated)
    assert report["ok"] is False
    failed = [c for c in report["checks"] if not c["ok"]]
    assert [c["check"] for c in failed] == ["license_kokoro"]
    assert any("license_kokoro" in line for line in report["drift"])


def test_drift_when_baseline_date_changed() -> None:
    original = _real_text()
    mutated = original.replace("2026-11-21", "2027-11-21")
    assert mutated != original
    report = sr.check_doc(mutated)
    assert report["ok"] is False
    assert any("baseline_date" in line for line in report["drift"])


def test_drift_when_price_changed() -> None:
    original = _real_text()
    mutated = original.replace("$0.01/render", "$0.05/render")
    assert mutated != original
    report = sr.check_doc(mutated)
    assert not next(
        c for c in report["checks"] if c["check"] == "license_remotion_price"
    )["ok"]


def test_drift_when_safe_rectangle_mutated() -> None:
    original = _real_text()
    mutated = original.replace("x=65..888, y=288..1248", "x=66..888, y=288..1248")
    assert mutated != original
    report = sr.check_doc(mutated)
    assert not next(c for c in report["checks"] if c["check"] == "safe_strict_rect")[
        "ok"
    ]


def test_both_minus_glyphs_accepted_for_audio_facts() -> None:
    unicode_doc = "integrated −14 LUFS, true peak ≤ −1.0 dBTP."
    ascii_doc = "integrated -14 LUFS, true peak ≤ -1.0 dBTP."
    for text in (unicode_doc, ascii_doc):
        report = sr.check_doc(text)
        assert next(c for c in report["checks"] if c["check"] == "audio_lufs")["ok"]
        assert next(c for c in report["checks"] if c["check"] == "audio_true_peak")[
            "ok"
        ]


def test_xtts_check_requires_non_commercial_context() -> None:
    assert sr.check_doc("XTTS-v2 appears here")["ok"] is False
    assert sr.check_doc("XTTS-v2 (Coqui CPML, non-commercial)")["ok"] is False
    report = sr.check_doc("XTTS-v2 (Coqui CPML, non-commercial)")
    assert next(c for c in report["checks"] if c["check"] == "license_xtts")["ok"]


# -- CLI ---------------------------------------------------------------------
def test_cli_pass_exit_zero_and_report_structure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = _write_real(tmp_path)
    assert sr.main(["--check", "--doc", str(doc)]) == 0
    report, err = _report_and_err(capsys)
    assert set(report) == {
        "ok",
        "offline",
        "baseline_date",
        "doc",
        "checks",
        "drift",
        "live",
    }
    assert report["ok"] is True
    assert report["offline"] is True
    assert report["live"] == []
    assert set(report["checks"][0]) == {"check", "ok", "detail"}
    assert "spec_refresh: PASS" in err


def test_cli_drift_exit_three(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "spec.md"
    doc.write_text(_real_text().replace("Remotion", "Rendy"), encoding="utf-8")
    assert sr.main(["--check", "--doc", str(doc)]) == 3
    report, err = _report_and_err(capsys)
    assert report["ok"] is False
    assert any("license_remotion" in line for line in report["drift"])
    assert "spec_refresh: FAIL" in err


def test_cli_missing_doc_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.md"
    assert sr.main(["--check", "--doc", str(missing)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read doc" in captured.err


def test_cli_invalid_utf8_doc_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "binary.md"
    doc.write_bytes(b"\xff\xfe not markdown")
    assert sr.main(["--doc", str(doc)]) == 2
    assert "cannot read doc" in capsys.readouterr().err


def test_cli_out_writes_same_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = _write_real(tmp_path)
    out = tmp_path / "nested" / "spec_report.json"
    assert sr.main(["--check", "--doc", str(doc), "--out", str(out)]) == 0
    printed = _report_and_err(capsys)[0]
    assert json.loads(out.read_text(encoding="utf-8")) == printed


def test_no_network_without_fetch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = _write_real(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("urlopen must not be called without --fetch")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    assert sr.main(["--check", "--doc", str(doc)]) == 0
    assert _report_and_err(capsys)[0]["live"] == []


# -- advisory live probes ----------------------------------------------------
def test_fetch_success_is_advisory_and_uses_timeout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = _write_real(tmp_path)
    payloads = {
        "https://support.google.com/youtube/answer/6013276": b"<html>2026</html>",
        "https://www.remotion.dev/pricing": b"<html>$0.01/render</html>",
    }
    calls: list[tuple[str, float]] = []

    def fake_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        calls.append((url, float(timeout)))
        return io.BytesIO(payloads[url])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert sr.main(["--check", "--doc", str(doc), "--fetch", "--timeout", "4.5"]) == 0
    report = _report_and_err(capsys)[0]
    assert report["ok"] is True
    assert report["offline"] is False
    assert len(report["live"]) == 2
    assert all(item["ok"] and item["marker_found"] for item in report["live"])
    assert len(calls) == 2
    assert all(timeout == 4.5 for _, timeout in calls)


def test_fetch_failure_never_fatal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = _write_real(tmp_path)

    def offline_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        raise OSError("network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", offline_urlopen)
    assert sr.main(["--check", "--doc", str(doc), "--fetch"]) == 0
    report = _report_and_err(capsys)[0]
    assert report["ok"] is True
    assert report["offline"] is True
    assert all(
        not item["ok"] and not item["marker_found"] and "OSError" in item["detail"]
        for item in report["live"]
    )


def test_fetch_marker_absent_is_still_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = _write_real(tmp_path)

    def unrelated_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        return io.BytesIO(b"<html>no expected markers</html>")

    monkeypatch.setattr(urllib.request, "urlopen", unrelated_urlopen)
    assert sr.main(["--check", "--doc", str(doc), "--fetch"]) == 0
    report = _report_and_err(capsys)[0]
    assert report["offline"] is False
    assert all(item["ok"] and not item["marker_found"] for item in report["live"])


def test_fetch_live_returns_one_entry_per_source_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        raise RuntimeError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", broken_urlopen)
    live = sr.fetch_live(2.0)
    assert len(live) == len(sr.LIVE_SOURCES)
    assert [item["url"] for item in live] == [url for url, _ in sr.LIVE_SOURCES]
    assert all(item["detail"].startswith("RuntimeError") for item in live)
