#!/usr/bin/env python3
"""threejs_bridge.py — Python subprocess bridge to the optional Three.js WebGL renderer.

Invokes ``node scripts/threejs/runner.mjs`` with list-form argv and a hard
timeout, writing ``frame_0001.png..frame_NNNN.png`` plus ``anchor_tracks.json``
into ``plate_dir`` — the exact same on-disk plate contract as
``blender_runner.py``.

Any failure (missing runtime, non-zero exit, timeout) logs a warning to stderr
and returns ``None`` so ``render_engine.py`` falls back cleanly to
``software_3d_projection.py``. Never raises during a render.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import scene_router
from scene_router import CAMERA_3D_DEFAULTS


def threejs_adapter_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize a board ``scene_spec`` for ``scripts/threejs/runner.mjs``.

    Fills camera defaults from :data:`scene_router.CAMERA_3D_DEFAULTS` so
    underspecified scenes match ``software_3d_projection.py`` and
    ``blender_runner.py`` identically. Never mutates ``spec``.
    """
    cam = spec.get("camera_3d") or {}
    return {
        "category": spec.get("category"),
        "transparent_bg": bool(spec.get("transparent_bg", False)),
        "lighting_preset": spec.get("lighting_preset", "cyber_studio_volumetric"),
        "explode_factor": spec.get("explode_factor", 1.0),
        "boolean_cutaway": bool(spec.get("boolean_cutaway", False)),
        "anchors_3d": spec.get("anchors_3d", []),
        "params": spec.get("params", {}),
        "camera_3d": {
            "focal_length_mm": cam.get(
                "focal_length_mm", CAMERA_3D_DEFAULTS["focal_length_mm"]
            ),
            "fstop": cam.get("fstop", CAMERA_3D_DEFAULTS["fstop"]),
            "radius_start": cam.get("radius_start", CAMERA_3D_DEFAULTS["radius_start"]),
            "radius_end": cam.get("radius_end", CAMERA_3D_DEFAULTS["radius_end"]),
            "azimuth_start_deg": cam.get(
                "azimuth_start_deg", CAMERA_3D_DEFAULTS["azimuth_start_deg"]
            ),
            "azimuth_end_deg": cam.get(
                "azimuth_end_deg", CAMERA_3D_DEFAULTS["azimuth_end_deg"]
            ),
            "elevation_deg": cam.get(
                "elevation_deg", CAMERA_3D_DEFAULTS["elevation_deg"]
            ),
        },
    }


def prerender_threejs_scene(
    scene_id: str,
    spec: dict[str, Any],
    plate_dir: Path,
    spec_path: Path,
    width: int,
    height: int,
    fps: int,
    n_frames: int,
    probe: dict[str, Any],
    *,
    timeout: int = 240,
) -> Path | None:
    """Pre-render a single scene_spec via headless Three.js; return ``plate_dir`` or ``None``."""
    node_bin = str(probe.get("node_binary") or "node")
    browser_bin = str(probe.get("browser_binary") or "")
    three_mod = str(probe.get("three_module") or "")
    runner = str(probe.get("runner_script") or (SCRIPT_DIR / "threejs" / "runner.mjs"))

    if not browser_bin or not three_mod:
        print(
            f"render_engine: warning — threejs probe incomplete for scene {scene_id!r}; "
            "software fallback",
            file=sys.stderr,
        )
        return None

    try:
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(
            json.dumps(threejs_adapter_spec(spec)),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                node_bin,
                runner,
                "--spec",
                str(spec_path),
                "--out-dir",
                str(plate_dir),
                "--width",
                str(width),
                "--height",
                str(height),
                "--fps",
                str(fps),
                "--frames",
                str(n_frames),
                "--browser",
                browser_bin,
                "--three-module",
                three_mod,
            ],
            check=False,
            timeout=timeout,
            capture_output=True,
        )
    except Exception as exc:  # noqa: BLE001 — timeout/OSError → software fallback
        print(
            f"render_engine: warning — threejs pre-render for scene {scene_id!r} "
            f"errored ({exc}); software fallback",
            file=sys.stderr,
        )
        return None

    if result.returncode != 0:
        tail = (result.stderr or b"").decode(errors="replace")[-800:]
        print(
            f"render_engine: warning — threejs pre-render for scene {scene_id!r} "
            f"exited {result.returncode}; software fallback\n{tail}",
            file=sys.stderr,
        )
        return None

    return plate_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check or invoke the optional headless Three.js 3D backend."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Probe Node.js, headless Chromium, and local three.module.js; exit 0 if ready, 2 otherwise.",
    )
    args = parser.parse_args()
    if args.check:
        probe = scene_router.probe_threejs_environment()
        print(json.dumps(probe, indent=2))
        return 0 if probe.get("available") else 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
