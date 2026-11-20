#!/usr/bin/env python3
"""monetization_gate.py — ad-safety, license-allowlist, and retention gates.

Pure-python checks (no render):

- ``assets_license_allowlist`` — every entry of ``assets/manifest.json``
  carries a commercial license in ``LICENSE_ALLOWLIST`` (or AI-generated) and
  a non-empty ``attribution``. Hard-blocks ``by-nc*``/``by-nd*``/``pd``/
  ``all-rights-reserved``/``unknown``/missing — monetized output may not use
  non-commercial or right-restricting stock for reuse of paid visuals.
- ``asset_files_exist`` — ``image`` elements have an existing ``src`` file on
  disk (or a base64 ``data`` payload).
- ``adversarial_safe_phrasing`` — script narration avoids unverifiable factual
  claims and defamation triggers; writes ``allegedly``/``according to``
  style rewrites. Loaded from ``script_path`` (script.schema.json) or from
  board narration strings.
- ``retention_static_hold`` — no scene holds a static frame past the
  platform-specific threshold (3 s Shorts @9:16, 6 s long @16:9) unless the
  scene moves (camera/typewriter/pulse) or carries dynamic SFX events.

Wire into ``verify_output.verify_mp4`` via ``monetization=`` to fail the
export on ERRORs. CLI: ``python3 scripts/monetization_gate.py --board ...``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
MANIFEST_DEFAULT = REPO / "assets" / "manifest.json"

# Commercial-safe allowlist for monetized social output. CC-BY-SA applies to
# share-alike outputs; CC-BY and PDM are commercial-remixable; AI-generated
# assets are allowed and disclose via publish_kit.
LICENSE_ALLOWLIST = {"cc0", "pdm", "by", "by-sa", "ai-generated"}

# Adversarial-phrasing triggers (consumers: political/news narrations).
_ADVERSARIAL_TRIGGERS: tuple[tuple[str, str, str], ...] = (
    (
        "fabricated_quote",
        r"(?i)\b(he|she|they|one)\s+(?:said|claimed|admitted|quoted)\s*,?\s*[\"\']?[\w ]{4,90}",
        'attributed speech with no named source — rewrite as "according to SOURCE, on DATE"',
    ),
    (
        "unverified_defamation",
        r"(?i)\b(cover-up|secretly|hidden agenda|obviously fake|blown up|conspiracy)\b",
        "defamation/conspiracy language — neutral phrasing: 'according to the record' or 'appears to have been'",
    ),
    (
        "medical_claim",
        r"(?i)\b(cure|kill|secret cure|proven to cure)\b[^.]{0,60}\b(glue|them|so they|you)\b",
        'unverified medical claim — name the source, use "some reports say"',
    ),
    (
        "election_fabrication",
        r"(?i)\b(the result was stolen|was canceled|was influenced|swept in millions)\b",
        'unverified election claim — attribution: "allegedly"/"claims to have"/"according to the audit"',
    ),
    (
        "no_source_experimental",
        r"(?i)\b(experts say|studies show)\b[^.]{0,60}(confirmed|proved|slammed|exact figures)\b",
        "unverified expert claim — pin the citation name/date, avoid invented precision",
    ),
)

_RULES_MOVING_TYPES = frozenset(
    {
        "orb_pulse",
        "dot_field",
        "orbit_ring",
        "equalizer",
        "leader_arrow",
        "typewriter_text",
    }
)
STATIC_HOLD_THRESHOLD = {"9:16": 3.0, "16:9": 6.0, "1:1": 5.0}


def _issue(
    rule: str, detail: str, severity: str, scene: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {"rule": rule, "severity": severity, "detail": detail}
    if scene:
        out["scene"] = scene
    return out


def _license_ok(entry: dict[str, Any]) -> bool:
    lic = str(entry.get("license", "")).strip().lower()
    if lic.startswith(("by-nc", "by-nd")) or lic == "pd":
        return False
    return lic in LICENSE_ALLOWLIST


def check_assets_license_allowlist(
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """ERROR per manifest entry whose license is not commercial-safe/attributed."""
    issues: list[dict[str, Any]] = []
    path = Path(manifest_path) if manifest_path else MANIFEST_DEFAULT
    if not path.is_file():
        return issues
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [
            _issue("assets_license_allowlist", f"manifest unreadable: {path}", "ERROR")
        ]
    for entry in manifest.get("assets", []) if isinstance(manifest, dict) else []:
        if not isinstance(entry, dict):
            continue
        lic = str(entry.get("license", "")).strip().lower()
        if not _license_ok(entry):
            issues.append(
                _issue(
                    "assets_license_allowlist",
                    f"{entry.get('src', 'unnamed')}: license {lic!r} not in allowlist {sorted(LICENSE_ALLOWLIST)} "
                    "(non-commercial or right-restricting reuse cannot be monetized)",
                    "ERROR",
                )
            )
        if (
            not str(entry.get("attribution", "")).strip()
            and entry.get("license") not in LICENSE_ALLOWLIST
        ):
            issues.append(
                _issue(
                    "assets_license_allowlist",
                    f"{entry.get('src', 'unnamed')}: missing required attribution",
                    "ERROR",
                )
            )
    return issues


def check_asset_files_exist(
    board: dict[str, Any], board_path: Path | None
) -> list[dict[str, Any]]:
    """ERROR for ``image`` elements whose ``src`` file is missing (no data URI)."""
    issues: list[dict[str, Any]] = []
    base = Path(board_path).parent if board_path else REPO
    scenes = board.get("scenes", []) if isinstance(board, dict) else []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for el in scene.get("elements", []) or []:
            if not isinstance(el, dict) or el.get("type") != "image":
                continue
            src = str(el.get("src", "")).strip()
            if src and el.get("data") is None and not (base / src).is_file():
                issues.append(
                    _issue(
                        "asset_files_exist",
                        f"image src missing on disk: {src}",
                        "ERROR",
                        scene.get("scene_id"),
                    )
                )
    return issues


def _narration_texts(script: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for raw in script.get("scenes", []) or []:
        if isinstance(raw, dict):
            for key in ("narration", "narration_text"):
                text = str(raw.get(key) or "").strip()
                if text:
                    out.append(text)
            title = str(raw.get("title") or "").strip()
            if title:
                out.append(title)
    meta = script.get("meta") or {}
    if isinstance(meta, dict):
        title = str(meta.get("title", "")).strip()
        if title:
            out.append(title)
    return out


def adversarial_safe_phrasing(script: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan script narration for unverifiable claims / defamation triggers."""
    issues: list[dict[str, Any]] = []
    for text in _narration_texts(script):
        hay = text.lower()
        for rule, pattern, hint in _ADVERSARIAL_TRIGGERS:
            match = re.search(pattern, hay)
            if match:
                issues.append(
                    _issue(
                        rule,
                        f"{hay[match.start() : match.end()].strip()!r} — {hint}",
                        "ERROR",
                    )
                )
    # dedupe identical findings
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for issue in issues:
        key = (issue["rule"], issue["detail"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _scene_moves(scene: dict[str, Any]) -> bool:
    camera = scene.get("camera") or {}
    zoom_moved = float(camera.get("zoom_start", 1.0) or 1.0) != float(
        camera.get("zoom_end", 1.0) or 1.0
    )
    orbit = (
        str(camera.get("mode", "zoom")) != "static" and camera.get("mode") is not None
    )
    return (
        bool(scene.get("sfx_events"))
        or zoom_moved
        or bool(orbit)
        or any(
            isinstance(el, dict) and str(el.get("type", "")) in _RULES_MOVING_TYPES
            for el in scene.get("elements", []) or []
        )
        or bool(scene.get("transition"))
    )


def retention_static_hold(
    board: dict[str, Any], thresholds: dict[str, float] | None = None
) -> list[dict[str, Any]]:
    """Error when a static scene holds past the platform-specific budget."""
    issues: list[dict[str, Any]] = []
    th = dict(STATIC_HOLD_THRESHOLD if thresholds is None else thresholds)
    for scene in board.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        try:
            duration = float(scene.get("duration_sec", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0
        fmt = board.get("format") or {}
        w, h = float(fmt.get("width", 0)), float(fmt.get("height", 0))
        aspect = "16:9"
        if w and h:
            aspect = "9:16" if h > w else ("1:1" if abs(w - h) < 10 else "16:9")
        limit = th.get(aspect, STATIC_HOLD_THRESHOLD.get("16:9", 6.0))
        if duration > limit and not _scene_moves(scene):
            issues.append(
                _issue(
                    "retention_static_hold",
                    f"scene {scene.get('scene_id')!r} holds {duration:.1f}s @{aspect} without motion/SFX "
                    f"(budget {limit:.1f}s); add a camera move, typewriter, pulse, or SFX",
                    "ERROR",
                    scene.get("scene_id"),
                )
            )
    return issues


def check_board_monetization(
    board: dict[str, Any],
    board_path: Path | None = None,
    manifest_path: Path | None = None,
    script_path: Path | None = None,
) -> dict[str, Any]:
    """Aggregate every monetization gate over a board. ``issues`` are ERRORs."""
    issues: list[dict[str, Any]] = []
    issues += check_assets_license_allowlist(manifest_path)
    issues += check_asset_files_exist(board, board_path)
    script: dict[str, Any] = {}
    if script_path is not None:
        try:
            script = json.loads(Path(script_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue("script_unreadable", str(exc), "ERROR"))
        else:
            issues += adversarial_safe_phrasing(script)
    elif board.get("narration"):
        issues += adversarial_safe_phrasing(board)
    issues += retention_static_hold(board)
    ok = all(issue["severity"] != "ERROR" for issue in issues)
    return {"ok": ok, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monetization/ad-safety gates")
    parser.add_argument("--board", type=Path, required=True, help="storyboard.json")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    parser.add_argument(
        "--script", type=Path, default=None, help="script.json (narration scans)"
    )
    parser.add_argument(
        "--json", type=Path, default=None, help="write JSON report here"
    )
    args = parser.parse_args(argv)

    try:
        board = json.loads(args.board.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"monetization_gate: cannot read board: {exc}", file=sys.stderr)
        return 2

    report = check_board_monetization(
        board,
        board_path=args.board,
        manifest_path=args.manifest,
        script_path=args.script,
    )
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        print(
            "monetization_gate: FAIL — "
            + ", ".join(
                i["rule"] for i in report["issues"] if i["severity"] == "ERROR"
            ),
            file=sys.stderr,
        )
        return 1
    print("monetization_gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
