#!/usr/bin/env python3
"""style.py — the style bible: one palette/type/material/light/grade/motion source.

A storyboard may carry an optional top-level ``style`` block::

    "style": {"preset": "soft_clay", "palette": {"accent": "#A65A38"}}

``preset`` names a JSON file in ``assets/styles/``; any inline keys override the
preset (palette merges per-role, other sections merge per-key). Anywhere a
colour string appears in the board, ``"@role"`` (e.g. ``"@accent"``) is replaced
with the resolved palette hex by :func:`apply_style` — a pure, deterministic
pre-pass, so painters, the Three.js bridge and Blender all see plain hex.

Stdlib only. Without a ``style`` block, :func:`apply_style` is a no-op.
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any

STYLES_DIR = Path(__file__).resolve().parent.parent / "assets" / "styles"

PALETTE_ROLES = ("ground", "ink", "accent", "accent2", "shadow", "highlight")
STYLE_SECTIONS = ("palette", "type", "material", "light", "grade", "motion")
VALID_MATERIALS = {"clay", "paper", "glass", "metal", "flat", "neon"}
VALID_MOTION_FEELS = {"calm", "punchy"}
# mirrors storyboard.VALID_EASINGS (parity pinned by tests/test_style.py)
VALID_EASES = {
    "linear",
    "ease_out_expo",
    "ease_in_out_cubic",
    "ease_in_out_sine",
    "ease_out_back",
    "spring_pop",
}
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
_REF_RE = re.compile(r"^@([a-z0-9_]+)$")


def list_presets() -> list[str]:
    if not STYLES_DIR.is_dir():
        return []
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


def load_preset(name: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError(f"invalid style preset name {name!r}")
    path = STYLES_DIR / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"unknown style preset {name!r}; available: {list_presets()}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"style preset {name!r} must be a JSON object")  # noqa: TRY004
    return data


def resolve_style(style: dict[str, Any] | None) -> dict[str, Any]:
    """Merge preset + inline overrides into one concrete style dict."""
    if not style:
        return {}
    merged: dict[str, Any] = {}
    preset = style.get("preset")
    if preset:
        merged = copy.deepcopy(load_preset(str(preset)))
    for key, value in style.items():
        if key == "preset":
            continue
        if key in STYLE_SECTIONS and isinstance(value, dict):
            section = merged.setdefault(key, {})
            section.update(value)
        else:
            merged[key] = value
    return merged


def _walk(node: Any, palette: dict[str, str]) -> Any:
    if isinstance(node, str):
        m = _REF_RE.match(node)
        if m and m.group(1) in palette:
            return palette[m.group(1)]
        return node
    if isinstance(node, list):
        return [_walk(v, palette) for v in node]
    if isinstance(node, dict):
        return {k: _walk(v, palette) for k, v in node.items()}
    return node


def kelvin_to_hex(kelvin: float) -> str:
    """Approximate black-body colour (Tanner Helland fit), clamped to 1500-12000 K."""
    k = max(1500.0, min(12000.0, float(kelvin))) / 100.0
    if k <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(k) - 161.1195681661
    else:
        r = 329.698727446 * ((k - 60) ** -0.1332047592)
        g = 288.1221695283 * ((k - 60) ** -0.0755148492)
    if k >= 66:
        b = 255.0
    elif k <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(k - 10) - 305.0447927307
    r, g, b = (max(0, min(255, round(c))) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def scene_style_light(resolved: dict[str, Any]) -> dict[str, Any]:
    """Light/ground colours for 3D backends derived from palette + colour temperature."""
    pal = resolved.get("palette") or {}
    light = resolved.get("light") or {}
    out: dict[str, Any] = {}
    if light.get("key_temp_k") is not None:
        out["key_hex"] = kelvin_to_hex(light["key_temp_k"])
    if light.get("fill_temp_k") is not None:
        out["fill_hex"] = kelvin_to_hex(light["fill_temp_k"])
    if pal.get("highlight"):
        out["rim_hex"] = pal["highlight"][:7]
    if pal.get("ground"):
        out["bg_hex"] = pal["ground"][:7]
    if light.get("shadow_softness") is not None:
        out["shadow_softness"] = light["shadow_softness"]
    return out


def motion_camera(motion: dict[str, Any]) -> dict[str, Any]:
    """Default 2D world-camera move for a motion feel (calm drift vs punchy push)."""
    drift = float(motion.get("drift", 0.02))
    punchy = motion.get("feel") == "punchy"
    zoom_end = 1.0 + (0.08 if punchy else 0.0) + drift * 2.0
    default_ease = "ease_out_expo" if punchy else "ease_in_out_cubic"
    return {
        "zoom_start": 1.0,
        "zoom_end": round(min(zoom_end, 1.25), 4),
        "easing": str(motion.get("ease", default_ease)),
    }


def apply_style(board: dict[str, Any]) -> dict[str, Any]:
    """Return a board with ``@role`` colour refs resolved and ``style`` made concrete.

    No ``style`` block → the board is returned unchanged.
    """
    raw = board.get("style")
    if not isinstance(raw, dict):
        return board
    resolved = resolve_style(raw)
    palette = {
        k: v
        for k, v in (resolved.get("palette") or {}).items()
        if isinstance(v, str) and _HEX_RE.match(v)
    }
    out = {k: _walk(v, palette) for k, v in board.items() if k != "style"}
    out["style"] = resolved
    sl = scene_style_light(resolved)
    if sl:
        for scene in out.get("scenes", []) or []:
            spec = scene.get("scene_spec") if isinstance(scene, dict) else None
            if isinstance(spec, dict) and "style_light" not in spec:
                scene["scene_spec"] = {**spec, "style_light": dict(sl)}
    motion = resolved.get("motion")
    if isinstance(motion, dict) and motion:
        cam = motion_camera(motion)
        for scene in out.get("scenes", []) or []:
            # explicit camera / 3D-spec scenes keep their authored move
            if (
                isinstance(scene, dict)
                and "camera" not in scene
                and "scene_spec" not in scene
            ):
                scene["camera"] = dict(cam)
    return out


def validate_style(style: Any, errors: list[str]) -> None:
    """Append human-readable problems with a ``style`` block to ``errors``."""
    if style is None:
        return
    if not isinstance(style, dict):
        errors.append("style must be an object")
        return
    unknown = set(style) - {"preset", *STYLE_SECTIONS}
    if unknown:
        errors.append(f"style has unknown keys: {sorted(unknown)}")
    preset = style.get("preset")
    if preset is not None:
        try:
            load_preset(str(preset))
        except ValueError as exc:
            errors.append(f"style.preset: {exc}")
    try:
        resolved = resolve_style(style)
    except (ValueError, json.JSONDecodeError):
        return
    palette = resolved.get("palette") or {}
    if not isinstance(palette, dict):
        errors.append("style.palette must be an object")
        palette = {}
    for role, value in palette.items():
        if role not in PALETTE_ROLES:
            errors.append(
                f"style.palette.{role}: unknown role (allowed {PALETTE_ROLES})"
            )
        elif not isinstance(value, str) or not _HEX_RE.match(value):
            errors.append(f"style.palette.{role} must be '#RRGGBB[AA]'")
    mat = (resolved.get("material") or {}).get("family")
    if mat is not None and mat not in VALID_MATERIALS:
        errors.append(f"style.material.family must be one of {sorted(VALID_MATERIALS)}")
    feel = (resolved.get("motion") or {}).get("feel")
    if feel is not None and feel not in VALID_MOTION_FEELS:
        errors.append(f"style.motion.feel must be one of {sorted(VALID_MOTION_FEELS)}")
    ease = (resolved.get("motion") or {}).get("ease")
    if ease is not None and ease not in VALID_EASES:
        errors.append(f"style.motion.ease must be one of {sorted(VALID_EASES)}")
    grade = resolved.get("grade") or {}
    for key in ("grain", "vignette", "halation"):
        v = grade.get(key)
        if v is not None and not (
            isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0
        ):
            errors.append(f"style.grade.{key} must be a number in [0, 1]")
    unresolved = _find_unresolved_refs(
        {k: v for k, v in style.items() if k != "preset"}, set(palette)
    )
    errors.extend(unresolved)


def _find_unresolved_refs(node: Any, roles: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(node, str):
        m = _REF_RE.match(node)
        if m and m.group(1) not in roles:
            found.append(f"colour ref {node!r} has no matching style.palette role")
    elif isinstance(node, list):
        for v in node:
            found.extend(_find_unresolved_refs(v, roles))
    elif isinstance(node, dict):
        for v in node.values():
            found.extend(_find_unresolved_refs(v, roles))
    return found


def find_board_unresolved_refs(board: dict[str, Any]) -> list[str]:
    """Scenes using ``@role`` colours with no/insufficient style palette."""
    resolved = (
        resolve_style(board.get("style"))
        if isinstance(board.get("style"), dict)
        else {}
    )
    roles = set((resolved.get("palette") or {}).keys())
    body = {k: v for k, v in board.items() if k != "style"}
    return sorted(set(_find_unresolved_refs(body, roles)))
