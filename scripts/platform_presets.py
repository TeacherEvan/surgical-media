"""platform_presets.py — platform-native presets (captions, hook/pacing budgets, aspect).

Optional top-level ``platform`` block::

    "platform": {"preset": "shorts_tiktok_reels", "caption_style": "sticker"}

:func:`apply_platform` fills *defaults only* on ``kinetic_captions`` elements
(explicit element keys always win) using the resolved style palette:

- ``sticker``   — big, heavy-stroked, no backing pill, word pop; short-form look.
- ``editorial`` — serif/regular weight on a soft translucent card; essay look.
- ``none``      — leave captions exactly as authored.

The numeric ``hook_max_sec`` / ``beat_max_sec`` budgets are *advisory* inputs for
``style_lint.py`` (retention heuristics), not render constraints.
"""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "shorts_tiktok_reels": {
        "aspect": "9:16",
        "caption_style": "sticker",
        "hook_max_sec": 3.0,
        "beat_max_sec": 3.0,
        "max_total_sec": 180.0,
        "loop_ending": True,
    },
    "youtube_long": {
        "aspect": "16:9",
        "caption_style": "editorial",
        "hook_max_sec": 8.0,
        "beat_max_sec": 8.0,
        "max_total_sec": 3600.0,
        "loop_ending": False,
    },
    "square": {
        "aspect": "1:1",
        "caption_style": "sticker",
        "hook_max_sec": 3.0,
        "beat_max_sec": 4.0,
        "max_total_sec": 180.0,
        "loop_ending": True,
    },
}
CAPTION_STYLES = {"sticker", "editorial", "none"}
_FAMILY_BY_FONT = {
    "inter": "sans",
    "cormorantgaramond": "serif",
    "jetbrainsmono": "mono",
}


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    s = value.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def mix_hex(a: str, b: str, t: float) -> str:
    """Linear blend of two ``#RRGGBB`` colours (t=0 → a, t=1 → b)."""
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    mixed = [round(x + (y - x) * t) for x, y in zip(ra, rb)]
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def font_family(font_name: str | None, default: str = "sans") -> str:
    if not font_name:
        return default
    return _FAMILY_BY_FONT.get(str(font_name).lower().replace(" ", ""), default)


def resolve_platform(block: dict[str, Any] | None) -> dict[str, Any]:
    if not block:
        return {}
    out = dict(PRESETS.get(str(block.get("preset", "")), {}))
    out.update({k: v for k, v in block.items() if k != "preset"})
    if block.get("preset"):
        out["preset"] = block["preset"]
    return out


def validate_platform(block: Any, errors: list[str]) -> None:
    if block is None:
        return
    if not isinstance(block, dict):
        errors.append("platform must be an object")
        return
    unknown = set(block) - {"preset", "caption_style", "hook_max_sec", "beat_max_sec"}
    if unknown:
        errors.append(f"platform has unknown keys: {sorted(unknown)}")
    preset = block.get("preset")
    if preset is not None and preset not in PRESETS:
        errors.append(f"platform.preset must be one of {sorted(PRESETS)}")
    cs = block.get("caption_style")
    if cs is not None and cs not in CAPTION_STYLES:
        errors.append(f"platform.caption_style must be one of {sorted(CAPTION_STYLES)}")
    for key in ("hook_max_sec", "beat_max_sec"):
        v = block.get(key)
        if v is not None and not (
            isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 <= v <= 600
        ):
            errors.append(f"platform.{key} must be a number in [0.5, 600]")


def caption_defaults(
    kind: str, style: dict[str, Any], width: int, height: int
) -> dict[str, Any]:
    """Default ``kinetic_captions`` keys for a caption style under a resolved style."""
    pal = style.get("palette") or {}
    ink = pal.get("ink", "#FFFFFF")
    ground = pal.get("ground", "#000000")
    accent = pal.get("accent", "#FFD700")
    shadow = pal.get("shadow", "#000000")
    types = style.get("type") or {}
    portrait = height > width
    if kind == "sticker":
        size = round(height * (0.034 if portrait else 0.052))
        return {
            "font_family": font_family(types.get("display"), "sans"),
            "bold": True,
            "size": size,
            "y_anchor": 0.60 if portrait else 0.84,
            "ink_color": ink,
            "accent": accent,
            "dim_color": mix_hex(ground, ink, 0.38),
            "bg_color": "none",
            "stroke_color": shadow,
            "stroke_width": round(size * 0.10, 2),
            "active_stroke_width": round(size * 0.13, 2),
            "pop_scale": 0.14,
            "max_width_frac": 0.9 if portrait else 0.8,
        }
    if kind == "editorial":
        size = round(height * (0.028 if portrait else 0.034))
        return {
            "font_family": font_family(types.get("body"), "serif"),
            "bold": False,
            "size": size,
            "ink_color": ink,
            "accent": accent,
            "dim_color": mix_hex(ground, ink, 0.45),
            "bg_color": ground,
            "bg_alpha": 0.82,
            "bg_outline": mix_hex(ground, ink, 0.18),
            "bg_radius": 16.0,
            "stroke_color": "none",
            "stroke_width": 0.0,
            "pop_scale": 0.05,
        }
    return {}


def apply_platform(board: dict[str, Any]) -> dict[str, Any]:
    """Return a board with platform caption defaults filled in (input untouched)."""
    block = board.get("platform")
    if not isinstance(block, dict):
        return board
    plat = resolve_platform(block)
    kind = str(plat.get("caption_style", "none"))
    out = {k: v for k, v in board.items()}
    out["platform"] = plat
    if kind == "none" or kind not in CAPTION_STYLES:
        return out
    fmt = board.get("format") or {}
    width, height = int(fmt.get("width", 1280)), int(fmt.get("height", 720))
    defaults = caption_defaults(kind, board.get("style") or {}, width, height)
    scenes = []
    for scene in board.get("scenes", []) or []:
        if not isinstance(scene, dict) or not scene.get("elements"):
            scenes.append(scene)
            continue
        new_scene = dict(scene)
        new_scene["elements"] = [
            {**defaults, **el}
            if isinstance(el, dict) and el.get("type") == "kinetic_captions"
            else el
            for el in scene["elements"]
        ]
        scenes.append(new_scene)
    out["scenes"] = scenes
    return out
