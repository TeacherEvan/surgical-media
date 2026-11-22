#!/usr/bin/env python3
"""style_apply.py — apply the executable 7-style matrix to a draft board.

``pipeline_preflight.py`` validates the contract; this script *writes* it into a
storyboard: style/platform presets, caption and pacing budgets, per-scene
archetypes (including the hybrid tonal arc), the retention-safe intro window,
and outro scaffolding (credit tag + CTA placeholder). It never invents factual
content — placeholders are explicit and reported.

    python3 scripts/style_apply.py --intake intake.json --board draft.json \
        --out storyboard.json --report style_changes.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import platform_presets
from pipeline_preflight import CTA_RE

HYBRID_ROTATION = [
    "code_report",
    "geometry_rig",
    "doc_essay",
    "code_report",
    "doc_essay",
]


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return data


def _rescale_timing(scene: dict[str, Any], old: float, new: float) -> None:
    """Keep word/SFX timestamps inside a scene whose duration was clamped."""
    if old <= 0:
        return
    ratio = new / old
    for word in scene.get("words", []):
        if isinstance(word, dict):
            for key in ("start", "end"):
                if key in word:
                    word[key] = round(float(word[key]) * ratio, 3)
    for event in scene.get("sfx_events", []):
        if isinstance(event, dict) and "t_sec" in event:
            event["t_sec"] = round(float(event["t_sec"]) * ratio, 3)


def _change(changes: list[dict[str, str]], path: str, before: Any, after: Any) -> None:
    changes.append({"path": path, "before": str(before), "after": str(after)})


def apply_style(
    board: dict[str, Any], intake: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return a styled copy of ``board`` and a reviewable change list."""
    out: dict[str, Any] = json.loads(json.dumps(board))
    changes: list[dict[str, str]] = []

    style = out.setdefault("style", {})
    if not isinstance(style, dict):
        style = {}
        out["style"] = style
    if style.get("preset") != intake["style_preset"]:
        _change(changes, "style/preset", style.get("preset"), intake["style_preset"])
        style["preset"] = intake["style_preset"]

    platform = out.setdefault("platform", {})
    if not isinstance(platform, dict):
        platform = {}
        out["platform"] = platform
    preset_name = intake["platform_preset"]
    preset = platform_presets.PRESETS.get(preset_name, {})
    for key, value in (
        ("preset", preset_name),
        ("caption_style", preset.get("caption_style", "editorial")),
        ("hook_max_sec", preset.get("hook_max_sec", 3.0)),
        ("beat_max_sec", preset.get("beat_max_sec", 3.0)),
    ):
        if platform.get(key) != value:
            _change(changes, f"platform/{key}", platform.get(key), value)
            platform[key] = value

    fmt = out.setdefault("format", {})
    if not isinstance(fmt, dict):
        fmt = {}
        out["format"] = fmt
    for key, value in intake["format"].items():
        if fmt.get(key) != value:
            _change(changes, f"format/{key}", fmt.get(key), value)
            fmt[key] = value

    scenes = out.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("board must contain a non-empty scenes[]")

    hybrid = intake.get("style") == "all_of_the_above"
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        want = (
            HYBRID_ROTATION[i % len(HYBRID_ROTATION)] if hybrid else intake["archetype"]
        )
        if scene.get("archetype") != want:
            _change(changes, f"scenes/{i}/archetype", scene.get("archetype"), want)
            scene["archetype"] = want

        if i == 0:
            lo = float(intake["intro"]["min_sec"])
            hi = float(intake["intro"]["max_sec"])
            duration = float(scene.get("duration_sec", 0.0))
            if duration < lo - 0.01 or duration > hi + 0.01:
                new = round((lo + hi) / 2.0, 3)
                _rescale_timing(scene, duration, new)
                _change(changes, f"scenes/{i}/duration_sec", duration, new)
                scene["duration_sec"] = new

    last = scenes[-1]
    if not isinstance(last, dict):
        raise TypeError("last scene must be an object")
    elements = last.setdefault("elements", [])
    if not isinstance(elements, list):
        elements = []
        last["elements"] = elements
    has_credits = any(
        isinstance(e, dict)
        and (e.get("type") == "source_tag" or bool(e.get("attribution")))
        for e in elements
    )
    if not has_credits:
        tag = {
            "type": "source_tag",
            "text": "Source: <fill from CREDITS.md>",
            "corner": "bl",
        }
        elements.append(tag)
        _change(changes, "scenes/-1/elements/+source_tag", "missing", tag["text"])

    narration = str(last.get("narration", ""))
    element_text = " ".join(
        str(e.get("text", "")) for e in elements if isinstance(e, dict)
    )
    if not CTA_RE.search(f"{narration} {element_text}"):
        updated = f"{narration} [CTA: follow/subscribe]".strip()
        _change(changes, "scenes/-1/narration", narration, updated)
        last["narration"] = updated

    # Durations changed above: recompute start_sec or the audio master (built
    # from the timeline) drifts against the frames. assign_start_times only
    # fills missing values, so clear the stale ones first.
    original_starts = [
        scene.get("start_sec") for scene in scenes if isinstance(scene, dict)
    ]
    cursor = 0.0
    new_starts: list[float] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        start = round(cursor, 3)
        scene["start_sec"] = start
        new_starts.append(start)
        cursor = start + float(scene.get("duration_sec", 0.0))
    if original_starts != new_starts:
        _change(changes, "scenes/*/start_sec", original_starts, new_starts)
    return out, changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        intake = _load_json(args.intake)
        board = _load_json(args.board)
        styled, changes = apply_style(board, intake)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(styled, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(changes, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"style_apply: {exc}", file=sys.stderr)
        return 2
    print(f"style_apply: {len(changes)} change(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
