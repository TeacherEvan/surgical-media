#!/usr/bin/env python3
"""Assemble projects/on_children/storyboard.json from audio-locked timed_draft.json."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def restore_punctuation(
    narration: str, words: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Re-attach original literary punctuation onto measured edge-tts WordBoundary tokens."""
    orig = narration.split()
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    out = [dict(w) for w in words]
    if len(orig) == len(out):
        for o, w in zip(orig, out):
            if norm(o) == norm(str(w["word"])):
                w["word"] = o
        return out
    # Fallback greedy alignment if edge-tts split a contraction
    oi = 0
    for w in out:
        wn = norm(str(w["word"]))
        if oi < len(orig) and norm(orig[oi]) == wn:
            w["word"] = orig[oi]
            oi += 1
    return out


# Shared editorial pastel caption style (Cormorant Garamond SemiBold on frosted linen mist)
def pastel_captions(
    *,
    y_anchor: float = 0.855,
    size: int = 33,
    bg_alpha: float = 0.78,
) -> dict[str, Any]:
    return {
        "type": "kinetic_captions",
        "font_family": "serif",
        "bold": True,
        "size": size,
        "ink_color": "#3C3028",
        "dim_color": "#9B8E82",
        "accent": "#A65A38",
        "bg_color": "#FCF8F2",
        "bg_alpha": bg_alpha,
        "bg_outline": "#DFD1BF",
        "bg_radius": 18.0,
        "stroke_color": "none",
        "stroke_width": 0.0,
        "active_stroke_width": 0.0,
        "pop_scale": 0.035,
        "line_height": 1.32,
        "max_width_frac": 0.84,
        "y_anchor": y_anchor,
    }


def main() -> None:
    timed = json.loads((HERE / "timed_draft.json").read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {sc["scene_id"]: sc for sc in timed["scenes"]}

    def rel_vo(sc: dict[str, Any]) -> str:
        # Path relative to storyboard.json directory
        p = Path(sc["vo_wav"])
        return f"audio/{p.name}"

    def words_for(sid: str) -> list[dict[str, Any]]:
        sc = by_id[sid]
        return restore_punctuation(str(sc["narration"]), list(sc["words"]))

    scenes: list[dict[str, Any]] = [
        # 1. Opening Title — sunlit linen + botanical watercolor garland + Cormorant Garamond
        {
            "scene_id": "01_opening_title",
            "archetype": "mixed",
            "duration_sec": 4.0,
            "silent_beat": True,
            "fade_in_sec": 1.2,
            "fade_out_sec": 0.0,
            "fade_color": "#FAF5EC",
            "camera": {
                "zoom_start": 1.0,
                "zoom_end": 1.03,
                "pan_x": 0.5,
                "pan_y": 0.5,
                "easing": "ease_in_out_sine",
            },
            "elements": [
                {
                    "type": "background",
                    "gradient": ["#FCF8F1", "#F5E7DA", "#EAEFE9"],
                    "direction": "diagonal",
                    "soft_glows": [
                        {
                            "x": 0.28,
                            "y": 0.30,
                            "radius": 0.42,
                            "color": "#F7DED0",
                            "alpha": 0.42,
                            "drift_x": 0.03,
                            "drift_y": -0.02,
                        },
                        {
                            "x": 0.74,
                            "y": 0.72,
                            "radius": 0.45,
                            "color": "#D9E6DA",
                            "alpha": 0.40,
                            "drift_x": -0.03,
                            "drift_y": 0.02,
                        },
                    ],
                    "vignette_color": "#E2D5C5",
                    "vignette_strength": 0.22,
                },
                {
                    "type": "svg",
                    "src": "svg/botanical_garland.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "fade",
                    "fade_in_sec": 1.1,
                },
                {
                    "type": "quote_card",
                    "box": [240, 235, 1040, 485],
                    "quote": "On Children",
                    "attribution": "from The Prophet  ·  Kahlil Gibran",
                    "attribution_prefix": "",
                    "align": "center",
                    "show_quote_mark": False,
                    "fill": "none",
                    "outline": "none",
                    "ink_color": "#3C3028",
                    "dim_color": "#7D6E62",
                    "font_family": "serif",
                    "attribution_family": "serif_italic",
                    "bold": True,
                    "size": 76,
                    "attribution_size": 30,
                    "reveal_start": 0.08,
                    "reveal_end": 0.55,
                    "slide_px": 18.0,
                },
            ],
            "sfx_events": [{"t_sec": 0.35, "sfx": "soft_chime", "intensity": 0.30}],
        },
        # 2. Three.js 3D World #1 — Blossom Stream ("Your children are not your children...")
        {
            "scene_id": "02_lifes_longing",
            "archetype": "mixed",
            "backend": "threejs_3d",
            "narration": by_id["02_lifes_longing"]["narration"],
            "duration_sec": by_id["02_lifes_longing"]["duration_sec"],
            "vo_wav": rel_vo(by_id["02_lifes_longing"]),
            "words": words_for("02_lifes_longing"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.90,
            "scene_spec": {
                "category": "external_asset_3d",
                "lighting_preset": "clean_product_softbox",
                "camera_3d": {
                    "mode": "orbit",
                    "focal_length_mm": 40,
                    "radius_start": 7.4,
                    "radius_end": 6.4,
                    "azimuth_start_deg": -16.0,
                    "azimuth_end_deg": 10.0,
                    "elevation_deg": 11.0,
                },
                "params": {
                    "threejs_script": "scenes_3d/blossom_stream.mjs",
                    "camera_target": [0.0, 2.8, 0.45],
                    "exposure": 1.00,
                    "bloom_strength": 0.14,
                    "bloom_radius": 0.55,
                    "bloom_threshold": 0.88,
                },
            },
            "elements": [
                {
                    "type": "svg",
                    "src": "svg/corner_filigree.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                },
                pastel_captions(),
            ],
            "sfx_events": [],
        },
        # 3. SVG 2.0 Botanical Watercolor — Two Currents ("They come through you...")
        {
            "scene_id": "03_through_you",
            "archetype": "mixed",
            "narration": by_id["03_through_you"]["narration"],
            "duration_sec": by_id["03_through_you"]["duration_sec"],
            "vo_wav": rel_vo(by_id["03_through_you"]),
            "words": words_for("03_through_you"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.90,
            "camera": {
                "zoom_start": 1.0,
                "zoom_end": 1.03,
                "pan_x": 0.52,
                "pan_y": 0.46,
                "easing": "ease_in_out_sine",
            },
            "elements": [
                {
                    "type": "background",
                    "gradient": ["#F6F8F3", "#EAEFE7", "#F7ECE1"],
                    "direction": "vertical",
                    "soft_glows": [
                        {
                            "x": 0.68,
                            "y": 0.28,
                            "radius": 0.36,
                            "color": "#FCE8CB",
                            "alpha": 0.45,
                            "drift_x": 0.03,
                            "drift_y": -0.02,
                        },
                        {
                            "x": 0.24,
                            "y": 0.62,
                            "radius": 0.40,
                            "color": "#D4E3D6",
                            "alpha": 0.36,
                            "drift_x": 0.02,
                            "drift_y": 0.02,
                        },
                    ],
                },
                {
                    "type": "svg",
                    "src": "svg/two_currents_meadow.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                    "scale_start": 1.0,
                    "scale_end": 1.035,
                },
                pastel_captions(),
            ],
            "sfx_events": [],
        },
        # 4. SVG 2.0 Botanical Wreath & Floating Seeds ("You may give them your love...")
        {
            "scene_id": "04_love_not_thoughts",
            "archetype": "mixed",
            "narration": by_id["04_love_not_thoughts"]["narration"],
            "duration_sec": by_id["04_love_not_thoughts"]["duration_sec"],
            "vo_wav": rel_vo(by_id["04_love_not_thoughts"]),
            "words": words_for("04_love_not_thoughts"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.90,
            "camera": {
                "zoom_start": 1.0,
                "zoom_end": 1.045,
                "pan_x": 0.5,
                "pan_y": 0.45,
                "easing": "ease_in_out_sine",
            },
            "elements": [
                {
                    "type": "background",
                    "gradient": ["#FDF8F2", "#F7E6DC", "#EFE4E0"],
                    "direction": "radial",
                    "soft_glows": [
                        {
                            "x": 0.50,
                            "y": 0.40,
                            "radius": 0.40,
                            "color": "#FFF6E6",
                            "alpha": 0.55,
                            "drift_x": 0.02,
                            "drift_y": -0.01,
                        },
                        {
                            "x": 0.78,
                            "y": 0.24,
                            "radius": 0.34,
                            "color": "#E6DDF0",
                            "alpha": 0.38,
                            "drift_x": -0.03,
                            "drift_y": 0.02,
                        },
                    ],
                    "vignette_color": "#E3D2C4",
                    "vignette_strength": 0.18,
                },
                {
                    "type": "svg",
                    "src": "svg/botanical_wreath_seeds.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                    "scale_start": 0.98,
                    "scale_end": 1.03,
                },
                pastel_captions(),
            ],
            "sfx_events": [],
        },
        # 5. Three.js 3D World #2 — The House of Tomorrow ("You may house their bodies...")
        {
            "scene_id": "05_house_of_tomorrow",
            "archetype": "mixed",
            "backend": "threejs_3d",
            "narration": by_id["05_house_of_tomorrow"]["narration"],
            "duration_sec": by_id["05_house_of_tomorrow"]["duration_sec"],
            "vo_wav": rel_vo(by_id["05_house_of_tomorrow"]),
            "words": words_for("05_house_of_tomorrow"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.95,
            "scene_spec": {
                "category": "external_asset_3d",
                "lighting_preset": "clean_product_softbox",
                "camera_3d": {
                    "mode": "dolly",
                    "focal_length_mm": 40,
                    "radius_start": 8.2,
                    "radius_end": 5.8,
                    "azimuth_start_deg": -5.0,
                    "azimuth_end_deg": -5.0,
                    "elevation_deg": 7.5,
                },
                "params": {
                    "threejs_script": "scenes_3d/house_of_tomorrow.mjs",
                    "camera_target": [0.0, 4.8, 0.85],
                    "exposure": 1.00,
                    "bloom_strength": 0.17,
                    "bloom_radius": 0.56,
                    "bloom_threshold": 0.86,
                },
            },
            "elements": [
                {
                    "type": "svg",
                    "src": "svg/corner_filigree.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                },
                pastel_captions(size=31),
            ],
            "sfx_events": [{"t_sec": 4.8, "sfx": "soft_chime", "intensity": 0.22}],
        },
        # 6. Three.js 3D World #3 — River Going Forward ("You may strive to be like them...")
        {
            "scene_id": "06_life_goes_forward",
            "archetype": "mixed",
            "backend": "threejs_3d",
            "narration": by_id["06_life_goes_forward"]["narration"],
            "duration_sec": by_id["06_life_goes_forward"]["duration_sec"],
            "vo_wav": rel_vo(by_id["06_life_goes_forward"]),
            "words": words_for("06_life_goes_forward"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.90,
            "scene_spec": {
                "category": "external_asset_3d",
                "lighting_preset": "clean_product_softbox",
                "camera_3d": {
                    "mode": "orbit",
                    "focal_length_mm": 42,
                    "radius_start": 7.6,
                    "radius_end": 6.4,
                    "azimuth_start_deg": 18.0,
                    "azimuth_end_deg": -10.0,
                    "elevation_deg": 20.0,
                },
                "params": {
                    "threejs_script": "scenes_3d/river_of_tomorrow.mjs",
                    "camera_target": [0.0, 3.8, 0.0],
                    "exposure": 1.00,
                    "bloom_strength": 0.14,
                    "bloom_radius": 0.52,
                    "bloom_threshold": 0.87,
                },
            },
            "elements": [
                {
                    "type": "svg",
                    "src": "svg/corner_filigree.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                },
                pastel_captions(size=32),
            ],
            "sfx_events": [],
        },
        # 7. Three.js 3D World #4A — The Living Bow Drawing ("You are the bows...")
        {
            "scene_id": "07_living_bow",
            "archetype": "mixed",
            "backend": "threejs_3d",
            "narration": by_id["07_living_bow"]["narration"],
            "duration_sec": by_id["07_living_bow"]["duration_sec"],
            "vo_wav": rel_vo(by_id["07_living_bow"]),
            "words": words_for("07_living_bow"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.90,
            "scene_spec": {
                "category": "external_asset_3d",
                "lighting_preset": "clean_product_softbox",
                "camera_3d": {
                    "mode": "orbit",
                    "focal_length_mm": 42,
                    "radius_start": 8.4,
                    "radius_end": 7.5,
                    "azimuth_start_deg": -22.0,
                    "azimuth_end_deg": -6.0,
                    "elevation_deg": 9.0,
                },
                "params": {
                    "threejs_script": "scenes_3d/living_bow.mjs",
                    "phase": "draw",
                    "camera_target": [-0.35, 0.0, -0.15],
                    "exposure": 1.02,
                    "bloom_strength": 0.18,
                    "bloom_radius": 0.55,
                    "bloom_threshold": 0.86,
                },
            },
            "elements": [
                {
                    "type": "svg",
                    "src": "svg/corner_filigree.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                },
                pastel_captions(),
            ],
            "sfx_events": [{"t_sec": 0.4, "sfx": "soft_chime", "intensity": 0.24}],
        },
        # 8. Three.js 3D World #4B — Living Arrows Soaring ("The archer sees the mark...")
        {
            "scene_id": "08_infinite_mark",
            "archetype": "mixed",
            "backend": "threejs_3d",
            "narration": by_id["08_infinite_mark"]["narration"],
            "duration_sec": by_id["08_infinite_mark"]["duration_sec"],
            "vo_wav": rel_vo(by_id["08_infinite_mark"]),
            "words": words_for("08_infinite_mark"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.85,
            "scene_spec": {
                "category": "external_asset_3d",
                "lighting_preset": "clean_product_softbox",
                "camera_3d": {
                    "mode": "orbit",
                    "focal_length_mm": 40,
                    "radius_start": 8.8,
                    "radius_end": 9.6,
                    "azimuth_start_deg": -10.0,
                    "azimuth_end_deg": 14.0,
                    "elevation_deg": 10.0,
                },
                "params": {
                    "threejs_script": "scenes_3d/living_bow.mjs",
                    "phase": "flight",
                    "camera_target": [2.2, 0.0, 0.40],
                    "exposure": 1.02,
                    "bloom_strength": 0.20,
                    "bloom_radius": 0.55,
                    "bloom_threshold": 0.86,
                },
            },
            "elements": [
                {
                    "type": "svg",
                    "src": "svg/corner_filigree.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                },
                pastel_captions(size=31),
            ],
            "sfx_events": [],
        },
        # 9. SVG 2.0 Gilded Bow & Olive Emblem ("Let your bending... be for gladness")
        {
            "scene_id": "09_gladness_bow",
            "archetype": "mixed",
            "narration": by_id["09_gladness_bow"]["narration"],
            "duration_sec": by_id["09_gladness_bow"]["duration_sec"],
            "vo_wav": rel_vo(by_id["09_gladness_bow"]),
            "words": words_for("09_gladness_bow"),
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "transition": "dissolve",
            "transition_sec": 0.95,
            "camera": {
                "zoom_start": 1.0,
                "zoom_end": 1.035,
                "pan_x": 0.5,
                "pan_y": 0.44,
                "easing": "ease_in_out_sine",
            },
            "elements": [
                {
                    "type": "background",
                    "gradient": ["#FCF7EF", "#F5E2D6", "#E5ECE6"],
                    "direction": "diagonal",
                    "soft_glows": [
                        {
                            "x": 0.50,
                            "y": 0.38,
                            "radius": 0.38,
                            "color": "#FFF6E3",
                            "alpha": 0.52,
                            "drift_x": 0.02,
                            "drift_y": -0.02,
                        },
                        {
                            "x": 0.22,
                            "y": 0.70,
                            "radius": 0.38,
                            "color": "#D9E7DC",
                            "alpha": 0.38,
                            "drift_x": 0.03,
                            "drift_y": 0.0,
                        },
                    ],
                    "vignette_color": "#E2D2C2",
                    "vignette_strength": 0.20,
                },
                {
                    "type": "svg",
                    "src": "svg/stable_bow_emblem.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                    "scale_start": 0.97,
                    "scale_end": 1.02,
                },
                pastel_captions(size=31),
            ],
            "sfx_events": [{"t_sec": 0.5, "sfx": "soft_chime", "intensity": 0.24}],
        },
        # 10. Quiet Epilogue Signature — dissolving smoothly & fading out to warm linen
        {
            "scene_id": "10_epilogue",
            "archetype": "mixed",
            "duration_sec": 4.2,
            "silent_beat": True,
            "fade_in_sec": 0.0,
            "fade_out_sec": 1.8,
            "fade_color": "#FAF5EC",
            "transition": "dissolve",
            "transition_sec": 1.0,
            "camera": {
                "zoom_start": 1.0,
                "zoom_end": 1.02,
                "pan_x": 0.5,
                "pan_y": 0.5,
                "easing": "ease_in_out_sine",
            },
            "elements": [
                {
                    "type": "background",
                    "gradient": ["#FCF8F1", "#F5E9DD", "#ECEFE9"],
                    "direction": "radial",
                    "soft_glows": [
                        {
                            "x": 0.5,
                            "y": 0.46,
                            "radius": 0.44,
                            "color": "#FFF6E6",
                            "alpha": 0.48,
                        }
                    ],
                    "vignette_color": "#E4D7C8",
                    "vignette_strength": 0.20,
                },
                {
                    "type": "svg",
                    "src": "svg/epilogue_olive.svg",
                    "box": [0, 0, 1280, 720],
                    "reveal": "none",
                },
                {
                    "type": "quote_card",
                    "box": [260, 295, 1020, 470],
                    "quote": "Kahlil Gibran",
                    "attribution": "The Prophet, 1923",
                    "attribution_prefix": "",
                    "align": "center",
                    "show_quote_mark": False,
                    "fill": "none",
                    "outline": "none",
                    "ink_color": "#3C3028",
                    "dim_color": "#807063",
                    "font_family": "serif",
                    "attribution_family": "serif_italic",
                    "bold": False,
                    "size": 56,
                    "attribution_size": 28,
                    "reveal_start": 0.05,
                    "reveal_end": 0.45,
                    "slide_px": 12.0,
                },
            ],
            "sfx_events": [{"t_sec": 0.3, "sfx": "soft_chime", "intensity": 0.26}],
        },
    ]

    board = {
        "meta": {
            "title": "On Children — Kahlil Gibran",
            "author": "Kahlil Gibran (The Prophet, 1923)",
            "seed": 19230101,
        },
        "format": {"width": 1280, "height": 720, "fps": 30},
        "scenes": scenes,
        "audio": {
            "pad": True,
            "pad_style": "pastel_harp",
            "pad_level": 0.145,
            "duck_depth": 0.62,
            "sample_rate": 48000,
        },
    }

    out = HERE / "storyboard.json"
    out.write_text(json.dumps(board, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(scenes)} scenes)")


if __name__ == "__main__":
    main()
