#!/usr/bin/env python3
"""asset_wire.py — wire licensed subject imagery into a storyboard.

Closes the loop between ``fetch_assets.py`` (downloads + manifest) and the
render. Image-first is the default: every scene that carries no subject
visual of its own (photo/SVG/map/comedy mockup/3D scene_spec) gets a
licensed plate from the manifest, generic archetype filler flagged
``placeholder: true`` is removed, and the manifest attribution travels
with the image. Scenes that opt out via ``visual.kind`` (svg/3d/procedural)
or already show the subject are left untouched.

Assignment is deterministic: assets are scored by keyword overlap with the
scene narration + ``visual.query`` + the board subject; each scene takes
the best unused plate, falling back to round-robin reuse when the pool is
smaller than the scene count. Pure functions + a thin CLI; tests run
offline with synthetic manifests.

    python3 scripts/asset_wire.py --board storyboard.json \
        --manifest assets/manifest.json --out storyboard.wired.json \
        --report wire_report.json [--subject "emperor penguin"]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from storyboard import scene_has_subject_visual

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "has",
        "have",
        "been",
        "were",
        "they",
        "this",
        "that",
        "with",
        "from",
        "what",
        "when",
        "where",
        "which",
        "their",
        "there",
        "about",
        "into",
        "than",
        "then",
        "them",
        "these",
        "some",
        "would",
        "could",
        "should",
        "will",
        "just",
        "like",
        "over",
        "such",
        "also",
        "more",
        "most",
        "other",
        "only",
        "very",
        "here",
        "how",
        "why",
        "who",
        "its",
        "his",
        "she",
        "him",
        "did",
        "does",
        "doing",
        "during",
        "each",
        "every",
        "both",
        "few",
        "because",
        "until",
        "while",
        "against",
        "between",
        "through",
        "before",
        "after",
        "above",
        "below",
        "again",
        "once",
        "file",
        "photo",
        "image",
        "img",
        "jpg",
        "jpeg",
        "png",
        "webp",
        "unknown",
        "author",
        "untitled",
    }
)
OPT_OUT_KINDS = frozenset({"svg", "3d", "procedural"})
# 9:16 credit line sits ABOVE the caption block (platform preset puts
# kinetic_captions at y_anchor≈0.6 → block top ≈1079 on a 1920px canvas).
# Keeps the credit inside the safe box without colliding with captions or
# the bottom platform chrome (see references/storyboard-guide.md).
PORTRAIT_CREDIT_Y = 1060.0


def tokens(text: str) -> set[str]:
    """Lowercase content words (len > 2, stopwords stripped)."""
    return {
        t
        for t in _TOKEN_RE.findall(str(text).lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Manifest assets[] or [] — missing/corrupt manifests warn, never crash."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"asset_wire: cannot read manifest {path}: {exc}", file=sys.stderr)
        return []
    if not isinstance(data, dict):
        print(f"asset_wire: manifest {path} is not an object", file=sys.stderr)
        return []
    assets = [a for a in data.get("assets", []) if isinstance(a, dict)]
    return [a for a in assets if str(a.get("file", "")).strip()]


def brief_assets(brief: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Turn brief.visual_assets into manifest-shaped entries (with provenance)."""
    if not isinstance(brief, dict):
        return []
    out: list[dict[str, Any]] = []
    for a in brief.get("visual_assets") or []:
        if not isinstance(a, dict) or not str(a.get("file", "")).strip():
            continue
        item = dict(a)
        item.setdefault("query", str(brief.get("subject", "")))
        out.append(item)
    return out


def anchor_for_scene(brief: dict[str, Any] | None, index: int) -> str:
    """The research brief's visual anchor for a beat, by claim_index or order."""
    if not isinstance(brief, dict):
        return ""
    anchors = [a for a in brief.get("visual_anchors") or [] if isinstance(a, dict)]
    for a in anchors:
        if int(a.get("claim_index", -1)) == index:
            return str(a.get("primitive", ""))
    return str(anchors[index].get("primitive", "")) if index < len(anchors) else ""


def asset_tokens(asset: dict[str, Any]) -> set[str]:
    return tokens(
        " ".join(str(asset.get(k, "")) for k in ("title", "creator", "source", "query"))
    )


def score_asset(asset: dict[str, Any], scene_text: str) -> int:
    """Keyword overlap between a plate's metadata and the scene's subject."""
    return len(asset_tokens(asset) & tokens(scene_text))


def _scene_text(scene: dict[str, Any], subject: str) -> str:
    visual = scene.get("visual")
    visual = visual if isinstance(visual, dict) else {}
    parts = [
        str(scene.get("narration", "")),
        str(visual.get("query", "")),
        str(visual.get("note", "")),
        subject,
    ]
    return " ".join(parts)


def pick_asset(
    assets: list[dict[str, Any]],
    used: set[str],
    scene_text: str,
    cursor: int,
) -> tuple[dict[str, Any] | None, bool]:
    """Best unused plate by keyword score; round-robin reuse when exhausted.

    Returns (asset, reused). Ties break on manifest order (deterministic).
    """
    if not assets:
        return None, False
    unused = [a for a in assets if str(a.get("file")) not in used]
    if unused:
        best = max(unused, key=lambda a: score_asset(a, scene_text))
        return best, False
    return assets[cursor % len(assets)], True


def image_element(
    asset: dict[str, Any],
    *,
    manifest_dir: Path,
    board_dir: Path,
    width: int,
    height: int,
    fit: str | None = None,
    attribution: str | None = None,
) -> dict[str, Any]:
    """A full-bleed subject plate with Ken Burns drift and a safe credit line.

    Portrait canvases default to ``backdrop_blur`` so landscape plates stay
    whole on 9:16; landscape/square default to ``cover``. ``src`` is stored
    relative to the board file so the bundle stays portable.
    """
    file_name = str(asset.get("file", ""))
    abs_path = (manifest_dir / file_name).resolve()
    try:
        src = Path(os.path.relpath(abs_path, board_dir.resolve())).as_posix()
    except ValueError:  # different drives on Windows — keep absolute
        src = str(abs_path)
    portrait = height > width * 1.2
    chosen = fit or ("backdrop_blur" if portrait else "cover")
    credit = (
        attribution if attribution is not None else str(asset.get("attribution", ""))
    )
    el: dict[str, Any] = {
        "type": "image",
        "src": src,
        "box": [0, 0, width, height],
        "fit": chosen,
        "kb_zoom": 1.08,
        "fade_in_sec": 0.6,
    }
    if credit:
        el["attribution"] = credit
        if portrait:
            el["attribution_y"] = PORTRAIT_CREDIT_Y
    return el


def _insert_plate(scene: dict[str, Any], plate: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop placeholder filler, keep background as a load-failure fallback,
    insert the plate before any text/caption layers."""
    elements = [
        e
        for e in (scene.get("elements") or [])
        if isinstance(e, dict) and e.get("placeholder") is not True
    ]
    out: list[dict[str, Any]] = []
    inserted = False
    for el in elements:
        if not inserted and el.get("type") != "background":
            out.append(plate)
            inserted = True
        out.append(el)
    if not inserted:
        out.append(plate)
    return out


def wire_board(
    board: dict[str, Any],
    assets: list[dict[str, Any]],
    *,
    manifest_dir: Path,
    board_dir: Path,
    subject: str = "",
    brief: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (wired copy, per-scene report). Never mutates the input board.

    Report actions: ``wired`` (plate assigned), ``explicit`` (visual.image),
    ``kept`` (already shows the subject), ``opt-out`` (visual.kind),
    ``reused`` (pool exhausted), ``no-assets`` (nothing to wire).
    """
    out: dict[str, Any] = json.loads(json.dumps(board))
    report: list[dict[str, Any]] = []
    fmt = out.get("format")
    fmt = fmt if isinstance(fmt, dict) else {}
    width = int(fmt.get("width", 1920))
    height = int(fmt.get("height", 1080))
    # Brief assets join the pool (manifest wins on duplicate filenames — it
    # carries verified dimensions and license provenance).
    known = {Path(str(a.get("file", ""))).name for a in assets}
    pool = list(assets) + [
        a for a in brief_assets(brief) if Path(str(a.get("file"))).name not in known
    ]
    used: set[str] = set()
    cursor = 0
    for scene_index, scene in enumerate(out.get("scenes", [])):
        if not isinstance(scene, dict):
            continue
        sid = str(scene.get("scene_id", "?"))
        visual = scene.get("visual")
        visual = visual if isinstance(visual, dict) else {}
        kind = str(visual.get("kind", "photo"))
        if scene_has_subject_visual(scene):
            report.append({"scene_id": sid, "action": "kept"})
            continue
        if kind in OPT_OUT_KINDS:
            report.append({"scene_id": sid, "action": "opt-out", "kind": kind})
            continue
        fit = visual.get("fit")
        fit = str(fit) if fit else None
        explicit = str(visual.get("image", "")).strip()
        anchor = anchor_for_scene(brief, scene_index)
        scene_text = _scene_text(scene, f"{subject} {anchor}".strip())
        if explicit:
            match = next(
                (
                    a
                    for a in pool
                    if str(a.get("file")) == Path(explicit).name
                    or str(manifest_dir / str(a.get("file"))) == explicit
                ),
                None,
            )
            credit = visual.get("attribution")
            if match is not None:
                plate = image_element(
                    match,
                    manifest_dir=manifest_dir,
                    board_dir=board_dir,
                    width=width,
                    height=height,
                    fit=fit,
                    attribution=str(credit) if credit is not None else None,
                )
            else:
                # explicit path is board-relative (or absolute) — keep verbatim
                plate = image_element(
                    {"file": explicit, "attribution": str(credit or "")},
                    manifest_dir=board_dir,
                    board_dir=board_dir,
                    width=width,
                    height=height,
                    fit=fit,
                )
                plate["src"] = explicit
            scene["elements"] = _insert_plate(scene, plate)
            used.add(str((match or {}).get("file", explicit)))
            report.append(
                {
                    "scene_id": sid,
                    "action": "explicit",
                    "src": plate["src"],
                    "attributed": bool(plate.get("attribution")),
                    **({"anchor": anchor} if anchor else {}),
                }
            )
            continue
        asset, reused = pick_asset(pool, used, scene_text, cursor)
        cursor += 1
        if asset is None:
            report.append({"scene_id": sid, "action": "no-assets"})
            continue
        plate = image_element(
            asset,
            manifest_dir=manifest_dir,
            board_dir=board_dir,
            width=width,
            height=height,
            fit=fit,
        )
        scene["elements"] = _insert_plate(scene, plate)
        used.add(str(asset.get("file")))
        report.append(
            {
                "scene_id": sid,
                "action": "reused" if reused else "wired",
                "src": plate["src"],
                "score": score_asset(asset, scene_text),
                **({"anchor": anchor} if anchor else {}),
            }
        )
    return out, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--brief",
        type=Path,
        default=None,
        help="investigation_brief.json — use visual_anchors as scene queries "
        "and visual_assets as an additional plate pool",
    )
    parser.add_argument(
        "--subject", default="", help="Board subject used for keyword matching"
    )
    args = parser.parse_args(argv)
    try:
        board = json.loads(args.board.read_text(encoding="utf-8"))
        if not isinstance(board, dict):
            raise TypeError(f"{args.board}: expected a JSON object")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"asset_wire: {exc}", file=sys.stderr)
        return 2
    assets = load_manifest(args.manifest)
    brief: dict[str, Any] | None = None
    if args.brief is not None:
        try:
            loaded = json.loads(args.brief.read_text(encoding="utf-8"))
            brief = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            print(f"asset_wire: cannot read brief {args.brief}: {exc}", file=sys.stderr)
            return 2
    if not assets and not brief_assets(brief):
        print(
            "asset_wire: manifest and brief have no assets — run fetch_assets.py first",
            file=sys.stderr,
        )
        return 2
    wired, report = wire_board(
        board,
        assets,
        manifest_dir=args.manifest.resolve().parent,
        board_dir=args.out.resolve().parent,
        subject=args.subject,
        brief=brief,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(wired, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    wired_n = sum(1 for r in report if r["action"] in ("wired", "explicit", "reused"))
    print(
        f"asset_wire: {wired_n}/{len(report)} scene(s) carry subject imagery → {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
