#!/usr/bin/env python3
"""tool_probe.py — probe the host environment for surgical-media capabilities.

Emits a machine-readable ``capabilities.json`` (default: stdout) so hosts and
the "Director Matrix" workflow (genre-specific visual scripts) can auto-select
the highest usable adapter tier. Stdlib-only, offline, exit 0 on success.

Detected areas (all presence-only — values of API keys are never emitted, so
the report is safe to paste into issues or logs):

- ``visual.paint`` — always-on tiers: ``fetch_assets.py`` stock + built-in
  2D painters; ``vision_paid`` (FAL — cloud image/video generation, when a
  key is present).
- ``visual.gpu`` — nvidia-smi presence + CUDA devices env.
- ``visual.blender`` / ``visual.threejs`` — reuse the scene_router probes.
- ``voice`` — local STT/TTS modules and binaries; cloud providers when keys
  present. Local TTS: piper, kokoro, f5-tts, chatterbox, whisper (stt).
- ``research`` — Tavily / Perplexity / Brave / NewsAPI / Exa presence.

Format written per run: {"tool_probe_version": 1, "visual": ...,
"voice": ..., "research": ..., "render": ..., "warnings": [...]}.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROBE_VERSION = 1

_ENV_KEYS = {
    # voice
    "ELEVENLABS_API_KEY",
    "CARTESIA_API_KEY",
    "OPENAI_TTS_API_KEY",
    "KOKORO_API_KEY",
    "KOKORO_TTS_API_KEY",
    # image/video gen via FAL (fal.ai)
    "FAL_KEY",
    # video gen
    "RUNWAY_API_KEY",
    "KLING_API_KEY",
    # STT
    "DEEPGRAM_API_KEY",
    "ASSEMBLY_API_KEY",
    # research
    "TAVILY_API_KEY",
    "PERPLEXITY_API_KEY",
    "BRAVE_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "NEWSAPI_API_KEY",
    "SERPAPI_API_KEY",
    "EXA_API_KEY",
    # generic gateway (has OSS usage via MATONAI etc.)
    "GEMINI_API_KEY",
}

_PY_MODULES = {
    "voice_local": (
        "kokoro",
        "f5_tts",
        "chatterbox_tts",
        "piper_tts",
        "edge_tts",
        "whisper",
    ),
    "stt_local": ("whisper", "faster_whisper", "vosk"),
    "render": ("playwright",),
}


def _find_spec(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def probe_env_keys() -> dict[str, bool]:
    """Report presence of each curated provider key (never the value)."""
    return {key: os.environ.get(key) not in (None, "") for key in sorted(_ENV_KEYS)}


def probe_local_modules() -> dict[str, dict[str, bool]]:
    return {
        key: {name: _find_spec(name) for name in names}
        for key, names in _PY_MODULES.items()
    }


def probe_cuda_gpu() -> dict[str, Any]:
    info: dict[str, Any] = {"nvidia_smi": shutil.which("nvidia-smi") is not None}
    if info["nvidia_smi"]:
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version",
                    "--format=csv,noheader",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            info["gpus"] = [
                line.strip() for line in out.stdout.splitlines() if line.strip()
            ]
        except (OSError, subprocess.SubprocessError):
            info["gpus"] = []
    info["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES")
    return info


def probe_playwright_browsers() -> list[str]:
    cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.is_dir():
        return []
    return sorted(
        (Path(p).name for p in cache.glob("chromium_*") if Path(p).is_dir()),
        key=str,
    )


def probe_blender() -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import scene_router

    out = scene_router._probe_blender_environment_uncached()
    return {
        "available": out.get("available", False),
        "version": out.get("version"),
        "binary": out.get("binary"),
    }


def probe_threejs() -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import scene_router

    out = scene_router._probe_threejs_environment_uncached()
    return {
        "available": out.get("available", False),
        "node_version": out.get("node_version"),
        "browser_binary": out.get("browser_binary"),
        "reason": out.get("reason"),
    }


def _which(names: tuple[str, ...]) -> dict[str, Any]:
    return {name: shutil.which(name) is not None for name in names}


def probe_binary_tools() -> dict[str, Any]:
    return {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "gst": shutil.which("gst-launch-1.0"),
    }


def probe_comfyui() -> bool:
    port = os.environ.get("COMFYUI_ADDRESS_PORT")
    if port:
        return True
    return _find_spec("comfyui") or _find_spec("comfy")


def run() -> dict[str, Any]:
    """Probe and return the capabilities report."""
    blender = probe_blender()
    threejs = probe_threejs()
    tts: dict[str, Any] = {
        "modules": probe_local_modules(),
        "binaries": _which(
            (
                "piper",
                "kokoro",
                "whisper",
                "faster_whisper",
                "edge_tts",
                "tts",
                "openai",
                "node",
            )
        ),
    }
    env_keys = probe_env_keys()
    tts["cloud_providers"] = {
        name: env_keys.get(key, False)
        for name, key in (
            ("elevenlabs", "ELEVENLABS_API_KEY"),
            ("cartesia", "CARTESIA_API_KEY"),
            ("kokoro", "KOKORO_API_KEY"),
        )
        if env_keys.get(key)
    }
    stt_providers = {
        name: env_keys.get(key, False)
        for name, key in (
            ("deepgram", "DEEPGRAM_API_KEY"),
            ("assemblyai", "ASSEMBLY_API_KEY"),
        )
        if env_keys.get(key)
    }
    tts["stt_cloud"] = stt_providers
    voice_cast_supported = True  # schema: "voices" map — tts_align per-scene override

    visual: dict[str, Any] = {
        "tiers": {
            "t0_stock_and_procedural": True,
            "t1_local_3d_photogrammetry": blender["available"] or threejs["available"],
            "t2_cloud_image_video_gen": bool(env_keys.get("FAL_KEY")),
        },
        "gpu": probe_cuda_gpu(),
        "blender": blender,
        "threejs": threejs,
        "comfyui_env": probe_comfyui(),
        "fetch_assets": True,
    }

    render: dict[str, Any] = {
        "playwright": _find_spec("playwright"),
        "playwright_browsers": probe_playwright_browsers(),
        "ffmpeg_paths": probe_binary_tools(),
    }

    research: dict[str, Any] = {
        name: env_keys.get(key, False)
        for name, key in (
            ("tavily", "TAVILY_API_KEY"),
            ("perplexity", "PERPLEXITY_API_KEY"),
            ("brave", "BRAVE_API_KEY"),
            ("newsapi", "NEWSAPI_API_KEY"),
            ("serpapi", "SERPAPI_API_KEY"),
            ("exa", "EXA_API_KEY"),
        )
        if env_keys.get(key)
    }

    warnings: list[str] = []
    if not render["ffmpeg_paths"]["ffprobe"]:
        warnings.append(
            "ffprobe missing — render_engine QC gate and verify_output will fail"
        )
    if not visual["tiers"]["t1_local_3d_photogrammetry"]:
        warnings.append(
            "no local Blender/Three.js — scene_router will use Pillow/svg/manim"
        )
    if not tts["modules"]["voice_local"]["kokoro"] and not tts["cloud_providers"]:
        warnings.append(
            "no local TTS found; edge-tts or a cloud voice provider is expected"
        )

    return {
        "tool_probe_version": PROBE_VERSION,
        "visual": visual,
        "voice": tts,
        "research": research,
        "render": render,
        "voice_cast_supported": voice_cast_supported,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe host tools for surgical-media")
    parser.add_argument(
        "--out", type=Path, default=None, help="Write JSON to this file"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Print nothing (only exit code)"
    )
    args = parser.parse_args(argv)

    data = run()
    text = json.dumps(data, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if not args.quiet:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
