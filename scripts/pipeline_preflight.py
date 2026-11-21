#!/usr/bin/env python3
"""pipeline_preflight.py — executable intake, style mapping and structure gate.

Turns the prose parts of the v3.0.0 pipeline into code:

* intake mode resolves Time + Style + Platform into a validated ``intake.json``
  (locked format, style preset, archetype, cadence, intro/outro contract);
* board mode checks a storyboard against that intake — schema validity, format,
  style/platform blocks, topic-matched intro and outro, duration cap, and a
  sourced research brief (originality gate).

Stdlib-only. Exit 0 = pass, 2 = bad invocation, 3 = a check failed.

    python3 scripts/pipeline_preflight.py --time 60 --style comedic \
        --platform tiktok --title "..." --intake-out intake.json
    python3 scripts/pipeline_preflight.py --board storyboard.json \
        --intake intake.json --brief investigation.json --json preflight.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import storyboard

STYLE_SPECS: dict[str, dict[str, Any]] = {
    "comedic": {
        "preset": "punchy_pop",
        "archetype": "geometry_rig",
        "cadence": [0.8, 1.5],
        "intro_kind": "hook",
        "outro_kind": "callback",
    },
    "serious": {
        "preset": "newsroom_clean",
        "archetype": "doc_essay",
        "cadence": [2.5, 4.0],
        "intro_kind": "cold_open",
        "outro_kind": "summary",
    },
    "formal": {
        "preset": "newsroom_clean",
        "archetype": "doc_essay",
        "cadence": [3.0, 5.0],
        "intro_kind": "titled_cold_open",
        "outro_kind": "credit_roll",
    },
    "catchy": {
        "preset": "tech_blueprint",
        "archetype": "code_report",
        "cadence": [0.6, 1.2],
        "intro_kind": "kinetic_stamp",
        "outro_kind": "loop",
    },
    "poetic": {
        "preset": "soft_clay",
        "archetype": "doc_essay",
        "cadence": [3.0, 6.0],
        "intro_kind": "evocative_image",
        "outro_kind": "lingering_frame",
    },
    "artistic": {
        "preset": "risograph",
        "archetype": "mixed",
        "cadence": [1.8, 3.0],
        "intro_kind": "vector_reveal",
        "outro_kind": "motif_resolve",
    },
    "all_of_the_above": {
        "preset": "punchy_pop",
        "archetype": "mixed",
        "cadence": [0.6, 4.0],
        "intro_kind": "fused_hook",
        "outro_kind": "style_payoff",
        "arc": [
            "catchy hook",
            "comedic beats",
            "serious/formal evidence",
            "catchy data",
            "poetic/artistic payoff",
        ],
    },
}

PLATFORMS: dict[str, dict[str, Any]] = {
    "youtube_long": {
        "preset": "youtube_long",
        "width": 1920,
        "height": 1080,
        "max_sec": 3600.0,
        "short_form": False,
    },
    "shorts": {
        "preset": "shorts_tiktok_reels",
        "width": 1080,
        "height": 1920,
        "max_sec": 180.0,
        "short_form": True,
    },
    "facebook_reels": {
        "preset": "shorts_tiktok_reels",
        "width": 1080,
        "height": 1920,
        "max_sec": 90.0,
        "short_form": True,
    },
    "facebook_feed": {
        "preset": "square",
        "width": 1440,
        "height": 1800,
        "max_sec": 240.0,
        "short_form": False,
    },
    "tiktok": {
        "preset": "shorts_tiktok_reels",
        "width": 1080,
        "height": 1920,
        "max_sec": 600.0,
        "short_form": True,
    },
}

CTA_RE = re.compile(
    r"\b(subscribe|follow|link|watch|next|share|comment|like|see\s+more|read\s+more)\b",
    re.IGNORECASE,
)
CREDIT_ELEMENTS = {"source_tag"}


def build_intake(
    time_sec: float,
    style: str,
    platform: str,
    title: str = "",
    fps: int = 30,
) -> dict[str, Any]:
    """Resolve the three mandatory inputs into a validated intake contract."""
    style_key = style.strip().lower().replace(" ", "_").replace("-", "_")
    if style_key not in STYLE_SPECS:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(STYLE_SPECS)}")
    if platform not in PLATFORMS:
        raise ValueError(
            f"unknown platform {platform!r}; choose from {sorted(PLATFORMS)}"
        )
    if time_sec <= 0:
        raise ValueError("--time must be positive")
    plat = PLATFORMS[platform]
    if time_sec > plat["max_sec"]:
        raise ValueError(
            f"{time_sec:g}s exceeds {platform} cap of {plat['max_sec']:g}s"
        )
    spec = STYLE_SPECS[style_key]
    intro_min, intro_max = (0.5, 3.0) if plat["short_form"] else (3.0, 10.0)
    return {
        "time_sec": float(time_sec),
        "style": style_key,
        "platform": platform,
        "title": title,
        "format": {
            "width": plat["width"],
            "height": plat["height"],
            "fps": fps,
        },
        "platform_preset": plat["preset"],
        "style_preset": spec["preset"],
        "archetype": spec["archetype"],
        "cadence_sec": list(spec["cadence"]),
        "intro": {
            "kind": spec["intro_kind"],
            "min_sec": intro_min,
            "max_sec": intro_max,
        },
        "outro": {
            "kind": spec["outro_kind"],
            "cta": True,
            "credits": True,
            "loop": bool(plat["short_form"]),
        },
        "max_duration_sec": plat["max_sec"],
        "safe_mode": "strict",
        "originality_required": True,
        **({"arc": list(spec["arc"])} if "arc" in spec else {}),
    }


def _scene_text(scene: dict[str, Any]) -> str:
    parts: list[str] = [str(scene.get("narration", ""))]
    for element in scene.get("elements", []):
        if isinstance(element, dict):
            for key in ("text", "attribution"):
                if key in element:
                    parts.append(str(element[key]))
    return " ".join(parts)


def _has_credits(scene: dict[str, Any]) -> bool:
    for element in scene.get("elements", []):
        if not isinstance(element, dict):
            continue
        if element.get("type") in CREDIT_ELEMENTS or element.get("attribution"):
            return True
    return False


def check_intro(
    scenes: list[dict[str, Any]], intro: dict[str, Any]
) -> tuple[bool, str]:
    """First scene must be a topic-matched hook/cold-open, not a logo bumper."""
    if not scenes:
        return False, "no scenes"
    first = scenes[0]
    duration = float(first.get("duration_sec", 0.0))
    lo, hi = float(intro["min_sec"]), float(intro["max_sec"])
    if not (lo - 0.01 <= duration <= hi + 0.01):
        return False, f"first scene {duration:g}s outside intro window {lo:g}-{hi:g}s"
    if not _scene_text(first).strip():
        return False, "first scene has no hook text/narration"
    return True, f"{intro['kind']} {duration:g}s inside {lo:g}-{hi:g}s"


def check_outro(
    scenes: list[dict[str, Any]], outro: dict[str, Any]
) -> tuple[bool, str]:
    """Last scene must carry both a CTA and an on-screen credit signal."""
    if not scenes:
        return False, "no scenes"
    last = scenes[-1]
    text = _scene_text(last)
    cta = bool(CTA_RE.search(text))
    credits = _has_credits(last)
    details = [f"cta={cta}", f"credits={credits}"]
    if outro.get("loop") and re.search(r"loop|again|back", text, re.IGNORECASE):
        details.append("loop=yes")
    ok = cta and credits
    return ok, ", ".join(details)


def check_brief(brief: dict[str, Any]) -> tuple[bool, str]:
    """5-point originality gate needs ≥3 sourced, claim-ID'd facts."""
    facts = brief.get("facts")
    if not isinstance(facts, list):
        return False, "brief has no facts[]"
    usable = [
        f
        for f in facts
        if isinstance(f, dict)
        and re.fullmatch(r"claim-[0-9a-f]{8}", str(f.get("claim_id", "")))
        and str(f.get("source", "")).strip()
    ]
    if len(usable) < 3:
        return False, f"only {len(usable)} sourced claim-ID facts (need 3)"
    return True, f"{len(usable)} sourced claim-ID facts"


def check_board(
    board: dict[str, Any], intake: dict[str, Any], brief: dict[str, Any]
) -> dict[str, Any]:
    """Run every structure check; return a JSON-serialisable report."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    errors = storyboard.validate_storyboard(board)
    add("storyboard_valid", not errors, "; ".join(errors[:3]) if errors else "OK")

    fmt = board.get("format", {})
    want = intake["format"]
    fmt_ok = (
        fmt.get("width") == want["width"]
        and fmt.get("height") == want["height"]
        and fmt.get("fps") == want["fps"]
    )
    add(
        "format_matches_intake",
        fmt_ok,
        f"{fmt.get('width')}x{fmt.get('height')}@{fmt.get('fps')} "
        f"vs {want['width']}x{want['height']}@{want['fps']}",
    )

    style_block = board.get("style") or {}
    platform_block = board.get("platform") or {}
    add(
        "style_preset_matches",
        style_block.get("preset") == intake["style_preset"],
        f"{style_block.get('preset')!r} vs {intake['style_preset']!r}",
    )
    add(
        "platform_preset_matches",
        platform_block.get("preset") == intake["platform_preset"],
        f"{platform_block.get('preset')!r} vs {intake['platform_preset']!r}",
    )

    scenes = board.get("scenes") or []
    intro_ok, intro_detail = check_intro(scenes, intake["intro"])
    add("topic_matched_intro", intro_ok, intro_detail)
    outro_ok, outro_detail = check_outro(scenes, intake["outro"])
    add("payoff_outro", outro_ok, outro_detail)

    total = storyboard.total_duration(board) if board.get("scenes") else 0.0
    cap = float(intake["max_duration_sec"])
    add("duration_within_cap", 0 < total <= cap, f"{total:.2f}s / cap {cap:g}s")

    brief_ok, brief_detail = check_brief(brief)
    add("originality_brief", brief_ok, brief_detail)

    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "checks": checks,
        "intake": intake,
        "total_duration_sec": total,
    }


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--time", type=float)
    parser.add_argument("--style")
    parser.add_argument("--platform", choices=sorted(PLATFORMS))
    parser.add_argument("--title", default="")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--intake-out", type=Path)
    parser.add_argument("--board", type=Path)
    parser.add_argument("--intake", type=Path)
    parser.add_argument("--brief", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.intake_out is not None:
            if args.time is None or not args.style or not args.platform:
                parser.error(
                    "--time, --style and --platform are required for intake mode"
                )
            intake = build_intake(
                args.time, args.style, args.platform, args.title, args.fps
            )
            args.intake_out.parent.mkdir(parents=True, exist_ok=True)
            args.intake_out.write_text(
                json.dumps(intake, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"pipeline_preflight: intake written to {args.intake_out}")
            return 0

        if args.board is None or args.intake is None or args.brief is None:
            parser.error("--board, --intake and --brief are required for board mode")
        board = _load_json(args.board)
        intake = _load_json(args.intake)
        brief = _load_json(args.brief)
        report = check_board(board, intake, brief)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"pipeline_preflight: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.json_path is not None:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(payload, encoding="utf-8")
    if report["ok"]:
        print("pipeline_preflight: PASS", file=sys.stderr)
        return 0
    failed = [c["check"] for c in report["checks"] if not c["ok"]]
    print(f"pipeline_preflight: FAIL — {', '.join(failed)}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
