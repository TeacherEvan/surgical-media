"""Offline unit & CLI tests for scripts/tool_probe.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tool_probe


def test_probe_env_keys_returns_booleans_and_never_exposes_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-super-secret-value-12345"
    monkeypatch.setenv("FAL_KEY", secret)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = tool_probe.probe_env_keys()
    assert isinstance(result, dict)
    assert result["FAL_KEY"] is True
    assert result["TAVILY_API_KEY"] is False
    assert all(isinstance(v, bool) for v in result.values())
    assert secret not in json.dumps(result)


def test_probe_local_modules_and_binary_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mods = tool_probe.probe_local_modules()
    assert set(mods) == {"voice_local", "stt_local", "render"}
    for group in mods.values():
        assert all(isinstance(v, bool) for v in group.values())

    monkeypatch.setattr(
        tool_probe.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    bins = tool_probe.probe_binary_tools()
    assert bins["ffmpeg"] == "/usr/bin/ffmpeg"
    assert bins["ffprobe"] == "/usr/bin/ffprobe"
    assert bins["gst"] is None


def test_probe_playwright_browsers_and_comfyui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    pw_cache = fake_home / ".cache" / "ms-playwright"
    (pw_cache / "chromium_headless_shell-1155").mkdir(parents=True)
    (pw_cache / "chromium_1155").mkdir(parents=True)
    (pw_cache / "firefox_100").mkdir(parents=True)

    monkeypatch.setattr(tool_probe.Path, "home", classmethod(lambda cls: fake_home))
    assert tool_probe.probe_playwright_browsers() == [
        "chromium_1155",
        "chromium_headless_shell-1155",
    ]

    monkeypatch.setenv("COMFYUI_ADDRESS_PORT", "127.0.0.1:8188")
    assert tool_probe.probe_comfyui() is True


def test_probe_cuda_gpu_present_missing_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_probe.shutil, "which", lambda _name: None)
    assert tool_probe.probe_cuda_gpu()["nvidia_smi"] is False

    monkeypatch.setattr(tool_probe.shutil, "which", lambda _name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        tool_probe.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a[0], 0, stdout="NVIDIA RTX 4090, 550.54\n", stderr=""
        ),
    )
    present = tool_probe.probe_cuda_gpu()
    assert present["nvidia_smi"] is True
    assert present["gpus"] == ["NVIDIA RTX 4090, 550.54"]

    def _raise(*_a: Any, **_kw: Any) -> Any:
        raise subprocess.SubprocessError("timeout")

    monkeypatch.setattr(tool_probe.subprocess, "run", _raise)
    errored = tool_probe.probe_cuda_gpu()
    assert errored["nvidia_smi"] is True
    assert errored["gpus"] == []


def test_run_schema_and_missing_ffprobe_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tool_probe,
        "probe_blender",
        lambda: {"available": False, "version": None, "binary": None},
    )
    monkeypatch.setattr(
        tool_probe,
        "probe_threejs",
        lambda: {
            "available": False,
            "node_version": None,
            "browser_binary": None,
            "reason": "disabled",
        },
    )
    monkeypatch.setattr(
        tool_probe,
        "probe_binary_tools",
        lambda: {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": None, "gst": None},
    )
    report = tool_probe.run()
    assert report["tool_probe_version"] == tool_probe.PROBE_VERSION
    assert {"visual", "voice", "research", "render", "warnings"} <= set(report)
    assert any("ffprobe" in w for w in report["warnings"])


def test_cli_stdout_and_out_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample: dict[str, Any] = {
        "tool_probe_version": 1,
        "visual": {},
        "voice": {},
        "research": {},
        "render": {},
        "warnings": [],
    }
    monkeypatch.setattr(tool_probe, "run", lambda: sample)

    assert tool_probe.main([]) == 0
    assert json.loads(capsys.readouterr().out) == sample

    out_file = tmp_path / "sub" / "capabilities.json"
    assert tool_probe.main(["--out", str(out_file)]) == 0
    assert json.loads(out_file.read_text(encoding="utf-8")) == sample
