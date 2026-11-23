#!/usr/bin/env python3
"""style_lint.py — advisory "anti-slop" + retention linter for storyboards.

Heuristics (not taste certification; a human contact-sheet review is the real
gate — see ``contact_sheet.py``). Report-only by default; ``--strict`` exits 1 on
any finding. Rules:

- ``off_palette``      colours far from the board's ``style.palette`` (needs a style)
- ``hue_sprawl``       >3 distinct saturated hues in one scene
- ``glow_overuse``     >3 ``glow: true`` elements in one scene
- ``centered_hero``    largest element dead-centre in 3+ consecutive scenes
- ``default_font``     no ``style.type`` and no ``font_family`` anywhere
- ``flat_motion``      most 2D scenes have no camera move (no depth/drift)
- ``single_easing``    4+ camera moves all using one easing
- ``no_hook``          platform preset: first scene has no text/captions/words
- ``long_hold``        platform preset: scene longer than 2x ``beat_max_sec``
- ``aspect_mismatch``  ``format`` aspect differs from the platform preset's
- ``unsourced_claim``  ``newsroom_clean``: quote/chart/stat scene with no
                       ``source_tag``/``attribution``; ``image`` without
                       ``attribution``
- ``synth_pad_enabled``    ``audio.pad: true`` with synthetic tonal ``pad_style``
- ``tonal_sfx_overuse``    tonal SFX (chime/confirm/soft_chime/error_buzz) over VO or >2 total
- ``synth_sfx_used``       procedural SFX without a real recorded ``wav`` file
- ``opaque_text_box``      ``quote_card``/``kinetic_captions`` with opaque dark box (alpha >= 0.85)
- ``text_obstructs_visual`` ``quote_card`` overlapping an image/chart/map/3D visual stage (>= 25%)
- ``no_subject_imagery``   image-first: no scene shows the subject (photo/SVG/map/
                           mockup/3D) and no ``meta.visual_intent`` opt-out
- ``low_visual_coverage``  fewer than 60% of scenes carry subject imagery
- ``placeholder_visual``   generic archetype filler (``placeholder: true``) still on
                           screen — wire licensed plates via ``asset_wire.py``
- ``unused_assets``        ``--manifest``: fetched plates never referenced by any
                           ``image`` element (fetched-but-never-shown)
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canvas import classify_aspect
from composition import centeredness
from platform_presets import PRESETS, resolve_platform
from storyboard import assign_start_times
from style import resolve_style

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
TEXT_ELEMENTS = {"kinetic_captions", "typewriter_text", "quote_card", "hud_badge"}
CLAIM_ELEMENTS = {"quote_card", "scaling_chart"}
Finding = dict[str, str]


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _walk_colors(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, str):
        if _HEX.match(node):
            found.append(node[:7].upper())
    elif isinstance(node, list):
        for v in node:
            found.extend(_walk_colors(v))
    elif isinstance(node, dict):
        for v in node.values():
            found.extend(_walk_colors(v))
    return found


def _dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5)


def _f(rule: str, scene: str, msg: str) -> Finding:
    return {"rule": rule, "scene": scene, "message": msg}


def _largest_box_center_score(
    scene: dict[str, Any], w: float, h: float
) -> float | None:
    best: tuple[float, float] | None = None
    for el in scene.get("elements", []) or []:
        box = el.get("box") if isinstance(el, dict) else None
        if isinstance(box, list) and len(box) == 4:
            b = tuple(float(v) for v in box)
            area = abs((b[2] - b[0]) * (b[3] - b[1]))
            if best is None or area > best[0]:
                best = (area, centeredness(b, w, h))
    return None if best is None else best[1]


def _check_scene_palette_and_glow(
    scenes: list[dict[str, Any]], palette: list[tuple[int, int, int]]
) -> list[Finding]:
    findings: list[Finding] = []
    for scene in scenes:
        sid = str(scene.get("scene_id", "?"))
        elements = [e for e in scene.get("elements", []) or [] if isinstance(e, dict)]
        colors = _walk_colors(elements)
        if palette:
            off = sorted(
                {
                    c
                    for c in colors
                    if min(
                        _dist(_rgb(c), p)
                        for p in palette + [(0, 0, 0), (255, 255, 255)]
                    )
                    > 70
                }
            )
            if len(off) > 3:
                findings.append(
                    _f(
                        "off_palette",
                        sid,
                        f"{len(off)} off-palette colours, e.g. {off[:3]}",
                    )
                )
        hues = set()
        for c in set(colors):
            r, g, b = (v / 255.0 for v in _rgb(c))
            hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
            if ss > 0.55 and vv > 0.35:
                hues.add(int(hh * 12) % 12)
        if len(hues) > 3:
            findings.append(
                _f("hue_sprawl", sid, f"{len(hues)} distinct saturated hues")
            )
        glows = sum(1 for e in elements if e.get("glow") is True)
        if glows > 3:
            findings.append(_f("glow_overuse", sid, f"{glows} glowing elements"))
    return findings


def _check_motion_and_framing(
    scenes: list[dict[str, Any]],
    raw_scenes: list[dict[str, Any]],
    style: dict[str, Any],
    w: float,
    h: float,
) -> list[Finding]:
    findings: list[Finding] = []
    run = 0
    for scene in scenes:
        score = _largest_box_center_score(scene, w, h)
        run = run + 1 if score is not None and score < 0.12 else 0
        if run == 3:
            findings.append(
                _f(
                    "centered_hero",
                    str(scene.get("scene_id", "?")),
                    "hero centred in 3+ consecutive scenes",
                )
            )
    has_font = bool((style.get("type") or {}).get("display")) or any(
        isinstance(e, dict) and e.get("font_family")
        for s in scenes
        for e in s.get("elements", []) or []
    )
    if not has_font:
        findings.append(
            _f(
                "default_font",
                "*",
                "no style.type and no font_family — default font only",
            )
        )
    flat_candidates = [s for s in raw_scenes if "scene_spec" not in s]
    if len(flat_candidates) >= 3 and not style.get("motion"):
        still = [s for s in flat_candidates if not s.get("camera")]
        if len(still) * 2 > len(flat_candidates):
            findings.append(
                _f(
                    "flat_motion",
                    "*",
                    f"{len(still)}/{len(flat_candidates)} 2D scenes have no camera move (add style.motion or camera)",
                )
            )
    eases = [
        str((s.get("camera") or {}).get("easing", "ease_out_expo"))
        for s in scenes
        if s.get("camera")
    ]
    if len(eases) >= 4 and len(set(eases)) == 1:
        findings.append(
            _f("single_easing", "*", f"all {len(eases)} camera moves use {eases[0]!r}")
        )
    return findings


def _check_platform_rules(
    scenes: list[dict[str, Any]], plat: dict[str, Any], w: float, h: float
) -> list[Finding]:
    if not plat:
        return []
    findings: list[Finding] = []
    preset = PRESETS.get(str(plat.get("preset", "")), {})
    if scenes:
        first = scenes[0]
        has_text = bool(first.get("words")) or any(
            isinstance(e, dict) and e.get("type") in TEXT_ELEMENTS
            for e in first.get("elements", []) or []
        )
        if not has_text:
            findings.append(
                _f(
                    "no_hook",
                    str(first.get("scene_id", "?")),
                    "first scene has no text/captions — state the hook on frame 0",
                )
            )
    beat = float(plat.get("beat_max_sec", 0) or 0)
    if beat:
        for scene in scenes:
            dur = float(scene.get("duration_sec", 0))
            if dur > 2 * beat:
                findings.append(
                    _f(
                        "long_hold",
                        str(scene.get("scene_id", "?")),
                        f"{dur:.1f}s hold > 2x beat budget ({beat:g}s)",
                    )
                )
    want = preset.get("aspect")
    if want and classify_aspect(int(w), int(h)) != want:
        findings.append(
            _f(
                "aspect_mismatch",
                "*",
                f"format is {classify_aspect(int(w), int(h))}, preset expects {want}",
            )
        )
    return findings


def _check_newsroom_sources(
    scenes: list[dict[str, Any]], style_preset: str, plat: dict[str, Any]
) -> list[Finding]:
    if style_preset != "newsroom_clean" and not plat.get("require_sources"):
        return []
    findings: list[Finding] = []
    for scene in scenes:
        sid = str(scene.get("scene_id", "?"))
        elements = [e for e in scene.get("elements", []) or [] if isinstance(e, dict)]
        claims = [e for e in elements if e.get("type") in CLAIM_ELEMENTS]
        cited = any(e.get("type") == "source_tag" for e in elements) or any(
            e.get("type") == "quote_card" and str(e.get("attribution", "")).strip()
            for e in elements
        )
        if claims and not cited:
            findings.append(
                _f(
                    "unsourced_claim",
                    sid,
                    "claim element without a source_tag/attribution",
                )
            )
        for e in elements:
            if e.get("type") == "image" and not str(e.get("attribution", "")).strip():
                findings.append(_f("unsourced_claim", sid, "image without attribution"))
    return findings


_TONAL_SFX = frozenset({"chime", "confirm", "soft_chime", "error_buzz"})
_VISUAL_STAGE_TYPES = frozenset(
    {"image", "svg", "scaling_chart", "map", "system_architecture"}
)


def _check_audio_and_overlays(
    board: dict[str, Any], raw_scenes: list[dict[str, Any]], w: float, h: float
) -> list[Finding]:
    findings: list[Finding] = []
    audio = board.get("audio")
    if isinstance(audio, dict) and (
        (
            audio.get("pad") is True
            and str(audio.get("pad_style", "room_tone")) in {"drone", "pastel_harp"}
        )
        or audio.get("allow_synth_pad") is True
        or audio.get("allow_synth_sfx") is True
    ):
        findings.append(
            _f(
                "synth_pad_enabled",
                "*",
                f"synthetic audio enabled (pad_style={audio.get('pad_style')!r})",
            )
        )

    total_tonal_sfx = 0
    for scene in raw_scenes:
        sid = str(scene.get("scene_id", "?"))
        has_vo = bool(scene.get("vo_wav")) or bool(
            str(scene.get("narration", "")).strip()
        )
        proc_evs = [
            ev
            for ev in (scene.get("sfx_events") or [])
            if isinstance(ev, dict)
            and ev.get("sfx") != "trauma"
            and not str(ev.get("wav", "")).strip()
        ]
        tonal_in_scene = [ev for ev in proc_evs if ev.get("sfx") in _TONAL_SFX]
        non_tonal_in_scene = [ev for ev in proc_evs if ev.get("sfx") not in _TONAL_SFX]
        total_tonal_sfx += len(tonal_in_scene)
        if has_vo and tonal_in_scene:
            findings.append(
                _f(
                    "tonal_sfx_overuse",
                    sid,
                    f"tonal SFX {[e.get('sfx') for e in tonal_in_scene]} over narration",
                )
            )
        if non_tonal_in_scene:
            findings.append(
                _f(
                    "synth_sfx_used",
                    sid,
                    f"procedural synth SFX {[e.get('sfx') for e in non_tonal_in_scene]} without real wav file; omit or supply real sfx_events[].wav",
                )
            )

        elements = [e for e in (scene.get("elements") or []) if isinstance(e, dict)]
        visual_boxes: list[tuple[float, float, float, float]] = []
        if isinstance(scene.get("scene_spec"), dict) and scene.get("scene_spec"):
            visual_boxes.append((w * 0.15, h * 0.15, w * 0.85, h * 0.75))
        for el in elements:
            etype = el.get("type")
            if etype in _VISUAL_STAGE_TYPES:
                raw_b = el.get("box")
                if isinstance(raw_b, list) and len(raw_b) == 4:
                    bx0, by0, bx1, by1 = (float(v) for v in raw_b)
                elif etype == "image":
                    bx0, by0, bx1, by1 = 0.0, 0.0, w, h
                else:
                    continue
                if etype == "image" and el.get("fit") == "backdrop_blur":
                    bh = by1 - by0
                    visual_boxes.append((bx0, by0 + 0.15 * bh, bx1, by0 + 0.85 * bh))
                else:
                    visual_boxes.append((bx0, by0, bx1, by1))

        for el in elements:
            etype = el.get("type")
            if etype == "quote_card":
                fill = el.get("fill")
                if (
                    fill not in (None, "", "none")
                    and float(el.get("alpha", 0.58)) >= 0.85
                ):
                    findings.append(
                        _f(
                            "opaque_text_box",
                            sid,
                            "quote_card sets opaque fill (alpha >= 0.85)",
                        )
                    )
                raw_qb = el.get("box")
                if isinstance(raw_qb, list) and len(raw_qb) == 4:
                    qx0, qy0, qx1, qy1 = (float(v) for v in raw_qb)
                else:
                    qx0, qy0, qx1, qy1 = w * 0.16, h * 0.52, w * 0.84, h * 0.78
                q_area = max(0.0, qx1 - qx0) * max(0.0, qy1 - qy0)
                if q_area > 0.0:
                    for vx0, vy0, vx1, vy1 in visual_boxes:
                        inter = max(0.0, min(qx1, vx1) - max(qx0, vx0)) * max(
                            0.0, min(qy1, vy1) - max(qy0, vy0)
                        )
                        if inter / q_area >= 0.25:
                            findings.append(
                                _f(
                                    "text_obstructs_visual",
                                    sid,
                                    "quote_card overlaps visual/photo stage (>= 25%)",
                                )
                            )
                            break
            elif etype == "kinetic_captions":
                bg_c = el.get("bg_color")
                if (
                    bg_c not in (None, "", "none")
                    and float(el.get("bg_alpha", 0.52)) >= 0.85
                ):
                    findings.append(
                        _f(
                            "opaque_text_box",
                            sid,
                            "kinetic_captions sets opaque bg_color (bg_alpha >= 0.85)",
                        )
                    )
    if total_tonal_sfx > 2:
        findings.append(
            _f(
                "tonal_sfx_overuse",
                "*",
                f"{total_tonal_sfx} tonal SFX across board (max 2)",
            )
        )
    return findings


def _check_subject_imagery(
    raw: dict[str, Any],
    scenes: list[dict[str, Any]],
    manifest_path: Path | None,
) -> list[Finding]:
    """Image-first rules: the subject must be on screen, filler must go."""
    from asset_wire import load_manifest
    from storyboard import (
        MIN_VISUAL_COVERAGE,
        VISUAL_INTENTS,
        scene_has_subject_visual,
    )

    findings: list[Finding] = []
    meta = raw.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    plated = sum(1 for s in scenes if scene_has_subject_visual(s))
    exempt = meta.get("visual_intent") in VISUAL_INTENTS
    if not plated and not exempt:
        findings.append(
            _f(
                "no_subject_imagery",
                "*",
                "no scene shows the subject (photo/SVG/map/mockup/3D) — fetch "
                "licensed imagery and wire it (asset_wire.py), or declare "
                "meta.visual_intent for genuine abstract work",
            )
        )
    elif scenes and not exempt and plated / len(scenes) < MIN_VISUAL_COVERAGE:
        findings.append(
            _f(
                "low_visual_coverage",
                "*",
                f"only {plated}/{len(scenes)} scenes carry subject imagery "
                f"(< {MIN_VISUAL_COVERAGE:.0%}) — one hero plate cannot carry "
                "a whole video; wire per-beat plates",
            )
        )
    for scene in scenes:
        sid = str(scene.get("scene_id", "?"))
        filler = [
            str(e.get("type"))
            for e in scene.get("elements", []) or []
            if isinstance(e, dict) and e.get("placeholder") is True
        ]
        if filler:
            findings.append(
                _f(
                    "placeholder_visual",
                    sid,
                    f"generic archetype filler on screen ({', '.join(filler)}) — "
                    "wire a licensed subject plate (asset_wire.py)",
                )
            )
    if manifest_path is not None:
        assets = load_manifest(manifest_path)
        shown: set[str] = set()
        for scene in scenes:
            for el in scene.get("elements", []) or []:
                if isinstance(el, dict) and el.get("type") == "image":
                    shown.add(Path(str(el.get("src", ""))).name)
        unused = [str(a.get("file")) for a in assets if str(a.get("file")) not in shown]
        if unused:
            findings.append(
                _f(
                    "unused_assets",
                    "*",
                    f"{len(unused)} fetched plate(s) never shown: {unused[:3]}",
                )
            )
    return findings


def lint_board(raw: dict[str, Any], manifest_path: Path | None = None) -> list[Finding]:
    board = assign_start_times(raw)  # @refs + style/platform defaults resolved
    fmt = board.get("format") or {}
    w, h = float(fmt.get("width", 1280)), float(fmt.get("height", 720))
    scenes = [s for s in board.get("scenes", []) if isinstance(s, dict)]
    raw_scenes = [s for s in raw.get("scenes", []) if isinstance(s, dict)]
    style = (
        resolve_style(raw.get("style")) if isinstance(raw.get("style"), dict) else {}
    )
    _style_block = raw.get("style")
    raw_style = _style_block if isinstance(_style_block, dict) else {}
    style_preset = str(raw_style.get("preset") or style.get("preset") or "")
    plat = (
        resolve_platform(raw.get("platform"))
        if isinstance(raw.get("platform"), dict)
        else {}
    )
    palette = [
        _rgb(v[:7])
        for v in (style.get("palette") or {}).values()
        if isinstance(v, str) and _HEX.match(v)
    ]
    return [
        *_check_scene_palette_and_glow(scenes, palette),
        *_check_motion_and_framing(scenes, raw_scenes, style, w, h),
        *_check_platform_rules(scenes, plat, w, h),
        *_check_newsroom_sources(scenes, style_preset, plat),
        *_check_audio_and_overlays(board, raw_scenes, w, h),
        *_check_subject_imagery(raw, scenes, manifest_path),
    ]


def score(findings: list[Finding]) -> int:
    return max(0, 100 - 8 * len(findings))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("boards", nargs="+", type=Path)
    ap.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="assets/manifest.json — also flag fetched plates never shown (unused_assets)",
    )
    args = ap.parse_args(argv)
    report: dict[str, Any] = {}
    for path in args.boards:
        try:
            findings = lint_board(
                json.loads(path.read_text(encoding="utf-8")), args.manifest
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"style_lint: cannot lint {path}: {exc}", file=sys.stderr)
            return 2
        report[str(path)] = {"score": score(findings), "findings": findings}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, rep in report.items():
            print(
                f"{name}: score {rep['score']}/100, {len(rep['findings'])} finding(s)"
            )
            for f in rep["findings"]:
                print(f"  [{f['rule']}] {f['scene']}: {f['message']}")
    bad = any(r["findings"] for r in report.values())
    return 1 if (args.strict and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
