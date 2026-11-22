"""Unit tests for monetization_gate (license firewall, phrasing scan, pacing)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import verify_output
from monetization_gate import (
    LICENSE_ALLOWLIST,
    adversarial_safe_phrasing,
    check_asset_files_exist,
    check_assets_license_allowlist,
    check_board_monetization,
    retention_static_hold,
)


def _manifest(tmp_path, entries):
    path = tmp_path / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"assets": entries}), encoding="utf-8")
    return path


def _board(scenes, fmt=(1920, 1080)):
    return {
        "format": {"width": fmt[0], "height": fmt[1], "fps": 30},
        "scenes": scenes,
    }


def _scene(duration=5.0, elements=None, scene_id="s1"):
    return {
        "scene_id": scene_id,
        "archetype": "mixed",
        "duration_sec": duration,
        "elements": elements or [{"type": "background", "color": "#0D1117"}],
    }


# ---------------------------------------------------------------------------
# license allowlist
# ---------------------------------------------------------------------------


def test_allowlist_blocks_noncommercial(tmp_path):
    for lic in ("by-nc", "by-nc-sa", "by-nd", "pd"):
        manifest = _manifest(tmp_path, [{"src": "a.jpg", "license": lic}])
        issues = check_assets_license_allowlist(manifest)
        assert issues and issues[0]["severity"] == "ERROR", lic


def test_allowlist_passes_commercial(tmp_path):
    for lic in sorted(LICENSE_ALLOWLIST):
        entry = {"file": "a.jpg", "license": lic}
        if lic in ("by", "by-sa"):
            entry["attribution"] = "Jane Photographer"
        manifest = _manifest(tmp_path / lic, [entry])
        assert check_assets_license_allowlist(manifest) == [], lic


def test_license_by_requires_attribution(tmp_path):
    for lic in ("by", "by-sa"):
        manifest = _manifest(tmp_path / lic, [{"file": "a.jpg", "license": lic}])
        issues = check_assets_license_allowlist(manifest)
        assert issues and issues[0]["severity"] == "ERROR"
        assert "a.jpg" in issues[0]["detail"]


def test_license_pd_is_blocked(tmp_path):
    manifest = _manifest(tmp_path, [{"src": "a.jpg", "license": "pd"}])
    assert check_assets_license_allowlist(manifest)


def test_allowlist_missing_manifest_is_ok(tmp_path):
    assert check_assets_license_allowlist(tmp_path / "missing.json") == []


# ---------------------------------------------------------------------------
# asset file existence
# ---------------------------------------------------------------------------


def test_asset_files_exist_catches_missing(tmp_path):
    board = _board([_scene(elements=[{"type": "image", "src": "assets/missing.jpg"}])])
    issues = check_asset_files_exist(board, tmp_path / "b.json")
    assert issues and issues[0]["severity"] == "ERROR"


def test_asset_files_exist_ok_when_present(tmp_path):
    src = tmp_path / "a.jpg"
    src.write_bytes(b"x")
    board = _board([_scene(elements=[{"type": "image", "src": "a.jpg"}])])
    assert check_asset_files_exist(board, tmp_path / "b.json") == []


# ---------------------------------------------------------------------------
# adversarial phrasing
# ---------------------------------------------------------------------------


def _script(narrations):
    return {"scenes": [{"narration": n} for n in narrations]}


def test_fabricated_quote_trigger():
    issues = adversarial_safe_phrasing(
        _script(["He said, 'of course it works' — experts claim they verified."])
    )
    assert any(i["rule"] == "fabricated_quote" for i in issues), issues


def test_election_fabrication_trigger():
    issues = adversarial_safe_phrasing(
        _script(["The result was stolen in 2 million votes."])
    )
    assert any(i["rule"] == "election_fabrication" for i in issues), issues


def test_clean_narration_passes():
    issues = adversarial_safe_phrasing(
        _script(["According to the audit of 2024, the bridge was rebuilt."])
    )
    assert issues == []


# ---------------------------------------------------------------------------
# retention static hold
# ---------------------------------------------------------------------------


def test_static_hold_warns_on_9_16_at_3s_budget():
    board = _board([_scene(duration=4.0)], fmt=(1080, 1920))
    assert any(
        i["rule"] == "retention_static_hold" for i in retention_static_hold(board)
    )


def test_static_hold_ok_when_moving():
    board = _board(
        [
            _scene(
                duration=4.0,
                elements=[{"type": "typewriter_text", "text": "x", "x": 1, "y": 1}],
            )
        ],
        fmt=(1080, 1920),
    )
    assert retention_static_hold(board) == []


def test_static_hold_ok_16_9_at_6s_budget():
    board = _board([_scene(duration=6.0)], fmt=(1920, 1080))
    assert retention_static_hold(board) == []


# ---------------------------------------------------------------------------
# board aggregation + verify_output integration
# ---------------------------------------------------------------------------


def test_check_board_monetization_ok_for_clean_board():
    board = _board(
        [_scene(duration=4.0, elements=[{"type": "typewriter_text", "text": "hi"}])]
    )
    report = check_board_monetization(board)
    assert report["ok"] is True
    assert report["issues"] == []


def test_check_board_monetization_fails_on_static_hold():
    board = _board([_scene(duration=4.0)], fmt=(1080, 1920))
    report = check_board_monetization(board)
    assert report["ok"] is False
    assert any(i["severity"] == "ERROR" for i in report["issues"])


def test_verify_output_appends_monetization_checks(monkeypatch, tmp_path):
    fake_probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 320,
                "height": 180,
                "r_frame_rate": "30/1",
                "duration": "1.0",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "duration": "1.0",
            },
        ],
        "format": {"duration": "1.0"},
    }
    mp4 = tmp_path / "dummy.mp4"
    mp4.write_bytes(b"fake")
    monkeypatch.setattr(verify_output, "_ffprobe_json", lambda path: fake_probe)
    report = verify_output.verify_mp4(
        mp4,
        monetization={
            "ok": False,
            "issues": [
                {
                    "rule": "assets_license_allowlist",
                    "severity": "ERROR",
                    "detail": "by-nc not allowed",
                    "scene": None,
                }
            ],
        },
    )
    assert not report["ok"]
    assert any(
        c["check"] == "assets_license_allowlist" and c["ok"] is False
        for c in report["checks"]
    )
