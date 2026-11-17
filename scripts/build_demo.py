#!/usr/bin/env python3
"""build_demo.py — regenerate examples/tri_archetype_storyboard.json.

Deterministic: same output every run. No TTS, no network — narration is
embedded as syllable-weighted word timestamps so kinetic captions render in
offline demos. The three scenes showcase geometry_rig, doc_essay and
code_report.
"""

from __future__ import annotations

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUT = SCRIPT_DIR.parent / "examples" / "tri_archetype_storyboard.json"

FPS = 30
W, H = 1280, 720


def words(text: str, start: float, dur: float) -> list[dict]:
    """Scene-relative karaoke words (local seconds into the scene)."""
    import sys

    sys.path.insert(0, str(SCRIPT_DIR))
    from tts_align import align_words

    return align_words(text, dur)


S1_NARR = "Numbers do not lie. Watch the spiral lock on."
S2_NARR = "Every order of magnitude arrives faster than the last."
S3_NARR = "The balancer held. The pool did not. Five hundred, zero, three."


def main() -> None:
    board = {
        "meta": {
            "title": "Surgical Media — Three Archetypes",
            "author": "surgical-media",
            "seed": 20261118,
        },
        "format": {"width": W, "height": H, "fps": FPS},
        "scenes": [
            {
                "scene_id": "geom_lock",
                "archetype": "geometry_rig",
                "narration": S1_NARR,
                "duration_sec": 4.2,
                "start_sec": 0.0,
                "fade_in_sec": 0.3,
                "fade_out_sec": 0.3,
                "camera": {
                    "zoom_start": 1.0,
                    "zoom_end": 1.18,
                    "pan_x": 0.5,
                    "pan_y": 0.5,
                    "easing": "ease_out_expo",
                    "shake_amplitude_px": 0.0,
                },
                "elements": [
                    {"type": "background", "color": "#050508"},
                    {
                        "type": "tesseract",
                        "cx": 990,
                        "cy": 210,
                        "size": 78,
                        "phase": 0.4,
                    },
                    {"type": "phi_divider", "box": [280, 250, 1000, 440]},
                    {
                        "type": "stick_rig",
                        "x": 640,
                        "y": 672,
                        "height": 300,
                        "reach_to": [640, 345],
                        "reach_side": "right",
                    },
                    {"type": "hud_badge", "text": "01 · GOLDEN RATIO", "corner": "tl"},
                    {"type": "kinetic_captions"},
                ],
                "words": words(S1_NARR, 0.0, 4.2),
                "sfx_events": [
                    {"t_sec": 0.15, "sfx": "whoosh", "intensity": 0.7},
                    {"t_sec": 3.15, "sfx": "chime", "intensity": 1.0},
                ],
            },
            {
                "scene_id": "doc_curve",
                "archetype": "doc_essay",
                "narration": S2_NARR,
                "duration_sec": 5.0,
                "start_sec": 4.2,
                "fade_in_sec": 0.3,
                "fade_out_sec": 0.3,
                "camera": {
                    "zoom_start": 1.0,
                    "zoom_end": 1.0,
                    "pan_x": 0.5,
                    "pan_y": 0.5,
                    "easing": "ease_in_out_cubic",
                },
                "elements": [
                    {"type": "background", "color": "#0A0E17"},
                    {"type": "grid", "spacing": 72, "color": "#131B2E"},
                    {
                        "type": "scaling_chart",
                        "box": [96, 120, 1184, 470],
                        "exponent": 4.35,
                        "odometer_from": 1.0,
                        "odometer_to": 500.0,
                        "accent": "#38BDF8",
                        "label": "FRONTIER COMPUTE",
                    },
                    {
                        "type": "quote_card",
                        "box": [150, 470, 1130, 610],
                        "quote": "Capability is compounding faster than our benchmarks can move.",
                        "attribution": "field note",
                    },
                    {"type": "hud_badge", "text": "02 · SCALING LAWS", "corner": "tl"},
                    {"type": "kinetic_captions"},
                ],
                "words": words(S2_NARR, 4.2, 5.0),
                "sfx_events": [
                    {"t_sec": 0.9, "sfx": "pop", "intensity": 0.6},
                    {"t_sec": 2.3, "sfx": "pop", "intensity": 0.8},
                    {"t_sec": 3.8, "sfx": "confirm", "intensity": 0.9},
                ],
            },
            {
                "scene_id": "code_cascade",
                "archetype": "code_report",
                "narration": S3_NARR,
                "duration_sec": 5.2,
                "start_sec": 9.2,
                "fade_in_sec": 0.3,
                "fade_out_sec": 0.4,
                "camera": {
                    "zoom_start": 1.0,
                    "zoom_end": 1.06,
                    "pan_x": 0.5,
                    "pan_y": 0.46,
                    "easing": "ease_in_out_cubic",
                    "shake_amplitude_px": 11.0,
                },
                "elements": [
                    {"type": "background", "color": "#0D1117"},
                    {
                        "type": "system_architecture",
                        "cascade_start": 1.35,
                        "cascade_step": 0.55,
                        "nodes": [
                            {
                                "id": "lb",
                                "label": "L7 LOAD BALANCER",
                                "x": 320,
                                "y": 215,
                                "role": "source",
                            },
                            {
                                "id": "ex1",
                                "label": "EXCHANGE-EU-1",
                                "x": 880,
                                "y": 105,
                                "role": "exchange",
                            },
                            {
                                "id": "ex2",
                                "label": "EXCHANGE-EU-2",
                                "x": 880,
                                "y": 230,
                                "role": "exchange",
                            },
                            {
                                "id": "ex3",
                                "label": "EXCHANGE-EU-3",
                                "x": 880,
                                "y": 355,
                                "role": "exchange",
                            },
                        ],
                    },
                    {
                        "type": "code_terminal",
                        "box": [90, 430, 1190, 590],
                        "title": "health-check.log",
                        "lines": [
                            {"text": "GET /api/health → 200 (12ms)", "kind": "normal"},
                            {
                                "text": "lb upstream pool: 14/14 healthy",
                                "kind": "normal",
                            },
                            {
                                "text": "tls handshake timeout ex1 eu-west",
                                "kind": "del",
                            },
                            {"text": "upstream pool: 13/14 healthy", "kind": "normal"},
                            {
                                "text": "tls handshake timeout ex2 eu-west",
                                "kind": "del",
                            },
                            {
                                "text": "503 Service Unavailable — circuit open",
                                "kind": "del",
                            },
                        ],
                    },
                    {"type": "hud_badge", "text": "03 · CASCADE", "corner": "tl"},
                    {"type": "kinetic_captions"},
                ],
                "words": words(S3_NARR, 9.2, 5.2),
                "sfx_events": [
                    {"t_sec": 0.2, "sfx": "type_click", "intensity": 0.8},
                    {"t_sec": 1.35, "sfx": "type_click", "intensity": 1.0},
                    {"t_sec": 1.9, "sfx": "error_buzz", "intensity": 0.6},
                    {"t_sec": 2.45, "sfx": "error_buzz", "intensity": 0.8},
                    {"t_sec": 3.0, "sfx": "error_buzz", "intensity": 1.0},
                    {"t_sec": 3.0, "sfx": "trauma", "intensity": 0.9},
                ],
            },
        ],
        "audio": {
            "pad": True,
            "pad_level": 0.05,
            "duck_depth": 0.72,
            "sample_rate": 48000,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(board, indent=2), encoding="utf-8")
    total = sum(sc["duration_sec"] for sc in board["scenes"])
    print(
        f"wrote {OUT} — {len(board['scenes'])} scenes, {total:.1f}s @ {W}x{H} {FPS}fps"
    )


if __name__ == "__main__":
    main()
