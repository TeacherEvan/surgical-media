#!/usr/bin/env python3
"""storyboard.py — stdlib storyboard validation & timing helpers.

Hand-rolled (no jsonschema dependency) so the renderer can hard-fail fast on
malformed boards with precise, line-addressable messages. The JSON Schema in
schemas/storyboard.schema.json is the normative contract; this validator
mirrors it for runtime use and error reporting.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VALID_ARCHETYPES = {"geometry_rig", "doc_essay", "code_report", "mixed"}
VALID_FPS = {24, 25, 30, 50, 60}
VALID_EASINGS = {
    "linear",
    "ease_out_expo",
    "ease_in_out_cubic",
    "ease_in_out_sine",
    "ease_out_back",
    "spring_pop",
}
VALID_SFX = {"pop", "whoosh", "chime", "type_click", "error_buzz", "confirm", "trauma"}
KNOWN_ELEMENTS = {
    "background",
    "grid",
    "hud_badge",
    "scaling_chart",
    "phi_divider",
    "tesseract",
    "system_architecture",
    "code_terminal",
    "quote_card",
    "kinetic_captions",
    "stick_rig",
    "image",
}
MIN_DIM, MAX_DIM = 160, 3840

VALID_BACKENDS = {"auto", "blender_hybrid", "blender_3d", "canvas_2d", "manim_math"}
VALID_3D_CATEGORIES = {
    "exploded_hardware_3d",
    "orbital_or_field_3d",
    "network_topology_3d",
    "rigid_body_physics_3d",
    "mathematical_manifold_3d",
    "external_asset_3d",
}
IMPLEMENTED_3D_CATEGORIES = {"exploded_hardware_3d", "orbital_or_field_3d"}
VALID_BLENDER_ENGINES = {"AUTO_EEVEE", "CYCLES"}
VALID_LIGHTING_PRESETS = {"cyber_studio_volumetric", "clean_product_softbox"}
VALID_CAMERA_MODES = {"orbit"}
ANCHOR_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
ACCENT_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# (key, lo, hi) numeric ranges for scene_spec.camera_3d — mirrors the schema.
_CAMERA_3D_RANGES = (
    ("focal_length_mm", 10.0, 200.0),
    ("fstop", 1.0, 32.0),
    ("radius_start", 0.5, 100.0),
    ("radius_end", 0.5, 100.0),
    ("azimuth_start_deg", -360.0, 360.0),
    ("azimuth_end_deg", -360.0, 360.0),
    ("elevation_deg", -90.0, 90.0),
)


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def lint_storyboard(data: Any, board_dir: Path | None = None) -> list[str]:
    """Non-fatal advisories: unknown elements, missing VO stems, risky boxes."""
    warnings: list[str] = []
    if not isinstance(data, dict):
        return warnings
    fmt = data.get("format", {})
    w = fmt.get("width") if isinstance(fmt, dict) else None
    h = fmt.get("height") if isinstance(fmt, dict) else None
    for i, scene in enumerate(data.get("scenes", []) or []):
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id", f"#{i}")
        for el in scene.get("elements", []) or []:
            if not isinstance(el, dict):
                continue
            etype = el.get("type")
            if etype and etype not in KNOWN_ELEMENTS:
                warnings.append(
                    f"scene {sid!r}: unknown element type {etype!r} (will render as no-op)"
                )
            box = el.get("box")
            if (
                isinstance(box, list)
                and len(box) == 4
                and isinstance(w, int)
                and isinstance(h, int)
            ):
                x0, y0, x1, y1 = [float(v) for v in box]
                if x1 < 0 or y1 < 0 or x0 > w or y0 > h:
                    warnings.append(
                        f"scene {sid!r}: element {etype!r} box lies fully outside the canvas"
                    )
        if scene.get("backend") == "manim_math":
            warnings.append(
                f"scene {sid!r}: backend 'manim_math' routes to canvas_2d fallback "
                "(manim deliberately out of scope)"
            )
        vo = scene.get("vo_wav")
        if vo:
            path = Path(vo)
            if not path.is_absolute() and board_dir is not None:
                path = board_dir / vo
            if not path.is_file():
                warnings.append(f"scene {sid!r}: vo_wav not found: {path}")
    return warnings


def validate_storyboard(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]

    meta = data.get("meta")
    if not isinstance(meta, dict) or not str(meta.get("title", "")).strip():
        errors.append("meta.title is required (non-empty string)")

    fmt = data.get("format")
    if not isinstance(fmt, dict):
        errors.append("format object is required (width, height, fps)")
    else:
        w, h, fps = fmt.get("width"), fmt.get("height"), fmt.get("fps")
        if not isinstance(w, int) or not MIN_DIM <= w <= MAX_DIM:
            errors.append(f"format.width must be an integer in [{MIN_DIM}, {MAX_DIM}]")
        if not isinstance(h, int) or not MIN_DIM <= h <= MAX_DIM:
            errors.append(f"format.height must be an integer in [{MIN_DIM}, {MAX_DIM}]")
        if fps not in VALID_FPS:
            errors.append(f"format.fps must be one of {sorted(VALID_FPS)}")

    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("scenes must be a non-empty array")
        return errors

    for i, scene in enumerate(scenes):
        where = f"scenes[{i}]"
        if not isinstance(scene, dict):
            errors.append(f"{where} must be an object")
            continue
        sid = scene.get("scene_id", f"#{i}")
        where = f"scene {sid!r}"

        if not str(scene.get("scene_id", "")).strip():
            errors.append(f"{where}: scene_id is required")
        if scene.get("archetype") not in VALID_ARCHETYPES:
            errors.append(
                f"{where}: archetype must be one of {sorted(VALID_ARCHETYPES)}"
            )
        dur = scene.get("duration_sec")
        if not isinstance(dur, (int, float)) or not (0.0 < float(dur) <= 600.0):
            errors.append(f"{where}: duration_sec must be in (0, 600]")
        if "start_sec" in scene and (
            not isinstance(scene["start_sec"], (int, float)) or scene["start_sec"] < 0
        ):
            errors.append(f"{where}: start_sec must be >= 0")

        cam = scene.get("camera")
        if cam is not None:
            if not isinstance(cam, dict):
                errors.append(f"{where}: camera must be an object")
            else:
                for key in ("zoom_start", "zoom_end"):
                    if key in cam and not (1.0 <= float(cam[key]) <= 10.0):
                        errors.append(f"{where}: camera.{key} must be in [1.0, 10.0]")
                for key in ("pan_x", "pan_y"):
                    if key in cam and not (0.0 <= float(cam[key]) <= 1.0):
                        errors.append(
                            f"{where}: camera.{key} must be normalized to [0, 1]"
                        )
                if cam.get("easing", "ease_out_expo") not in VALID_EASINGS:
                    errors.append(
                        f"{where}: camera.easing must be one of {sorted(VALID_EASINGS)}"
                    )
                amp = cam.get("shake_amplitude_px", 0.0)
                if not (0.0 <= float(amp) <= 80.0):
                    errors.append(
                        f"{where}: camera.shake_amplitude_px must be in [0, 80]"
                    )

        backend = scene.get("backend")
        if backend is not None and backend not in VALID_BACKENDS:
            errors.append(f"{where}: backend must be one of {sorted(VALID_BACKENDS)}")

        spec = scene.get("scene_spec")
        if spec is not None:
            if not isinstance(spec, dict):
                errors.append(f"{where}: scene_spec must be an object")
            else:
                if spec.get("category") not in VALID_3D_CATEGORIES:
                    errors.append(
                        f"{where}: scene_spec.category must be one of "
                        f"{sorted(VALID_3D_CATEGORIES)}"
                    )
                elif spec.get("category") not in IMPLEMENTED_3D_CATEGORIES:
                    errors.append(
                        f"{where}: scene_spec.category {spec['category']!r} is not "
                        f"implemented; supported: {sorted(IMPLEMENTED_3D_CATEGORIES)}"
                    )
                be = spec.get("blender_engine")
                if be is not None and be not in VALID_BLENDER_ENGINES:
                    errors.append(
                        f"{where}: scene_spec.blender_engine must be one of "
                        f"{sorted(VALID_BLENDER_ENGINES)}"
                    )
                lp = spec.get("lighting_preset")
                if lp is not None and lp not in VALID_LIGHTING_PRESETS:
                    errors.append(
                        f"{where}: scene_spec.lighting_preset must be one of "
                        f"{sorted(VALID_LIGHTING_PRESETS)}"
                    )
                hud_title = spec.get("hud_title")
                if hud_title is not None and (
                    not isinstance(hud_title, str) or len(hud_title) > 96
                ):
                    errors.append(
                        f"{where}: scene_spec.hud_title must be a string of <= 96 chars"
                    )
                ef = spec.get("explode_factor")
                if ef is not None and (
                    not _is_num(ef) or not (0.0 <= float(ef) <= 5.0)
                ):
                    errors.append(
                        f"{where}: scene_spec.explode_factor must be a number in [0, 5]"
                    )
                bc = spec.get("boolean_cutaway")
                if bc is not None and not isinstance(bc, bool):
                    errors.append(
                        f"{where}: scene_spec.boolean_cutaway must be a boolean"
                    )
                tb = spec.get("transparent_bg")
                if tb is not None and not isinstance(tb, bool):
                    errors.append(
                        f"{where}: scene_spec.transparent_bg must be a boolean"
                    )
                params = spec.get("params")
                if params is not None and not isinstance(params, dict):
                    errors.append(f"{where}: scene_spec.params must be an object")

                camera_3d = spec.get("camera_3d")
                if camera_3d is not None:
                    if not isinstance(camera_3d, dict):
                        errors.append(
                            f"{where}: scene_spec.camera_3d must be an object"
                        )
                    else:
                        mode = camera_3d.get("mode")
                        if mode is not None and mode not in VALID_CAMERA_MODES:
                            errors.append(
                                f"{where}: scene_spec.camera_3d.mode must be one of "
                                f"{sorted(VALID_CAMERA_MODES)}"
                            )
                        for key, lo, hi in _CAMERA_3D_RANGES:
                            if key in camera_3d and (
                                not _is_num(camera_3d[key])
                                or not (lo <= float(camera_3d[key]) <= hi)
                            ):
                                errors.append(
                                    f"{where}: scene_spec.camera_3d.{key} must be a "
                                    f"number in [{lo}, {hi}]"
                                )

                anchors = spec.get("anchors_3d")
                if anchors is not None:
                    if not isinstance(anchors, list) or len(anchors) > 8:
                        errors.append(
                            f"{where}: scene_spec.anchors_3d must be an array of at most 8 items"
                        )
                    else:
                        for j, anchor in enumerate(anchors):
                            if not isinstance(anchor, dict):
                                errors.append(
                                    f"{where}: scene_spec.anchors_3d[{j}] must be an object"
                                )
                                continue
                            for req in ("anchor_id", "label", "metric", "local_pos"):
                                if req not in anchor:
                                    errors.append(
                                        f"{where}: scene_spec.anchors_3d[{j}].{req} is required"
                                    )
                            aid = anchor.get("anchor_id")
                            if aid is not None and (
                                not isinstance(aid, str) or not ANCHOR_ID_RE.match(aid)
                            ):
                                errors.append(
                                    f"{where}: scene_spec.anchors_3d[{j}].anchor_id must match "
                                    "^[a-z0-9_-]{1,64}$"
                                )
                            for text_key in ("label", "metric"):
                                tv = anchor.get(text_key)
                                if tv is not None and (
                                    not isinstance(tv, str) or len(tv) > 96
                                ):
                                    errors.append(
                                        f"{where}: scene_spec.anchors_3d[{j}].{text_key} "
                                        "must be a string of <= 96 chars"
                                    )
                            local_pos = anchor.get("local_pos")
                            if local_pos is not None and (
                                not isinstance(local_pos, list)
                                or len(local_pos) != 3
                                or not all(_is_num(v) for v in local_pos)
                            ):
                                errors.append(
                                    f"{where}: scene_spec.anchors_3d[{j}].local_pos must be "
                                    "an array of 3 numbers"
                                )
                            accent = anchor.get("accent_hex")
                            if accent is not None and not (
                                isinstance(accent, str) and ACCENT_HEX_RE.match(accent)
                            ):
                                errors.append(
                                    f"{where}: scene_spec.anchors_3d[{j}].accent_hex must "
                                    "match ^#[0-9A-Fa-f]{6}$"
                                )

        elements = scene.get("elements")
        if elements is None:
            if spec is None:
                errors.append(f"{where}: scene must have elements or scene_spec")
        elif not isinstance(elements, list) or not elements:
            errors.append(
                f"{where}: elements must be a non-empty array when present "
                "(omit the key entirely for scene_spec scenes)"
            )
        else:
            for j, el in enumerate(elements):
                if not isinstance(el, dict) or not str(el.get("type", "")).strip():
                    errors.append(f"{where}: elements[{j}] requires a non-empty 'type'")

        words = scene.get("words")
        if words is not None:
            if not isinstance(words, list):
                errors.append(f"{where}: words must be an array")
            else:
                for j, w in enumerate(words):
                    ok = (
                        isinstance(w, dict)
                        and isinstance(w.get("word"), str)
                        and w["word"]
                        and isinstance(w.get("start"), (int, float))
                        and isinstance(w.get("end"), (int, float))
                        and float(w["end"]) >= float(w["start"])
                    )
                    if not ok:
                        errors.append(
                            f"{where}: words[{j}] needs word/start/end with end >= start"
                        )

        for j, ev in enumerate(scene.get("sfx_events", []) or []):
            if not isinstance(ev, dict):
                errors.append(f"{where}: sfx_events[{j}] must be an object")
                continue
            if not isinstance(ev.get("t_sec"), (int, float)) or ev["t_sec"] < 0:
                errors.append(f"{where}: sfx_events[{j}].t_sec must be >= 0")
            if ev.get("sfx") not in VALID_SFX:
                errors.append(
                    f"{where}: sfx_events[{j}].sfx must be one of {sorted(VALID_SFX)}"
                )
            if (
                isinstance(dur, (int, float))
                and isinstance(ev.get("t_sec"), (int, float))
                and ev["t_sec"] > float(dur) + 1e-6
            ):
                errors.append(
                    f"{where}: sfx_events[{j}].t_sec ({ev['t_sec']}) exceeds scene duration"
                )

    return errors


def assign_start_times(data: dict) -> dict:
    """Fill missing start_sec by accumulating scene durations. Mutates a copy."""
    out = json.loads(json.dumps(data))
    cursor = 0.0
    for scene in out.get("scenes", []):
        if scene.get("start_sec") is None:
            scene["start_sec"] = round(cursor, 3)
        cursor = max(cursor, float(scene["start_sec"]) + float(scene["duration_sec"]))
    return out


def total_duration(data: dict) -> float:
    total = 0.0
    for scene in assign_start_times(data).get("scenes", []):
        total = max(total, float(scene["start_sec"]) + float(scene["duration_sec"]))
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a surgical-media storyboard."
    )
    parser.add_argument("storyboard", type=Path)
    parser.add_argument(
        "--assign-start-times",
        action="store_true",
        help="Print the board with sequential start_sec filled in.",
    )
    args = parser.parse_args()

    try:
        data = json.loads(args.storyboard.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL {args.storyboard}: {exc}", file=sys.stderr)
        return 2

    for warning in lint_storyboard(data, args.storyboard.parent):
        print(f"warn {warning}", file=sys.stderr)

    errors = validate_storyboard(data)
    for err in errors:
        print(f"FAIL {err}", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} error(s)", file=sys.stderr)
        return 1
    if args.assign_start_times:
        print(json.dumps(assign_start_times(data), indent=2))
    else:
        print(
            f"OK {args.storyboard} — {len(data.get('scenes', []))} scenes, "
            f"{total_duration(data):.2f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
