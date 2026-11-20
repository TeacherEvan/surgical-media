#!/usr/bin/env python3
"""publish_kit.py — publishing checklist + metadata draft from a storyboard.

Writes ``publish_kit.md``: title/description draft (from ``meta`` + scene VO text),
YouTube-style chapters (long-form only), asset credits from an
``assets/manifest.json`` (``fetch_assets.py``), AI-disclosure wording and a
pre-publish policy checklist. Optional ``--thumbnails DIR`` ranks existing scene
PNGs by luminance contrast to suggest a thumbnail candidate (a heuristic —
review by eye).

This is a *drafting aid*: no tool can guarantee monetisation approval. Platform
policies (YouTube reused/inauthentic content + altered/synthetic disclosure,
TikTok AI-generated content labels, Meta AI info labels) change — verify the
current wording before publishing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageStat
from platform_presets import resolve_platform
from storyboard import assign_start_times

POLICY_LINKS = {
    "YouTube — disclosing altered or synthetic content": "https://support.google.com/youtube/answer/14328491",
    "YouTube — inauthentic / reused content (YPP)": "https://support.google.com/youtube/answer/1311392",
    "TikTok — AI-generated content labels": "https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content",
}


def fmt_ts(sec: float) -> str:
    s = round(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def scene_text(scene: dict[str, Any]) -> str:
    words = scene.get("words") or []
    return " ".join(
        str(w.get("word", "")) for w in words if isinstance(w, dict)
    ).strip()


def chapters(board: dict[str, Any], min_sec: float = 10.0) -> list[tuple[str, str]]:
    """Chapters satisfying YouTube's rules: start at 0:00, >=3 entries, >=10s each."""
    out: list[tuple[float, str]] = []
    for scene in board.get("scenes", []):
        start = float(scene.get("start_sec", 0.0))
        title = (
            str(scene.get("title") or scene.get("scene_id", ""))
            .replace("_", " ")
            .strip()
            .title()
        )
        if (
            out
            and start - out[-1][0] < min_sec
            and float(scene.get("duration_sec", 0)) < min_sec
        ):
            continue  # merge into the previous chapter only when this one is short too
        out.append((start, title))
    if len(out) < 3:
        return []
    out[0] = (0.0, out[0][1])
    return [(fmt_ts(t), name) for t, name in out]


def pick_thumbnail(thumb_dir: Path) -> tuple[Path, float] | None:
    best: tuple[Path, float] | None = None
    for p in sorted(thumb_dir.glob("*.png")):
        try:
            with Image.open(p) as im:
                contrast = ImageStat.Stat(im.convert("L")).stddev[0]
        except OSError:
            continue
        if best is None or contrast > best[1]:
            best = (p, contrast)
    return best


def credits_from_manifest(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        str(a["attribution"]) for a in data.get("assets", []) if a.get("attribution")
    ]


def build_kit(
    raw: dict[str, Any],
    manifest: Path | None = None,
    thumbs: Path | None = None,
) -> str:
    board = assign_start_times(raw)
    meta = board.get("meta", {})
    plat = (
        resolve_platform(raw.get("platform"))
        if isinstance(raw.get("platform"), dict)
        else {}
    )
    title = str(meta.get("title", "Untitled"))
    spoken = " ".join(t for t in (scene_text(s) for s in board.get("scenes", [])) if t)
    lines = [f"# Publish kit — {title}", ""]
    lines += ["## Title & description (draft — edit)", f"**Title:** {title}", ""]
    lines += [
        spoken[:300] + ("…" if len(spoken) > 300 else "")
        if spoken
        else "_No VO text in the board; write a description._",
        "",
    ]
    if plat.get("preset") == "youtube_long" or plat.get("preset") is None:
        ch = chapters(board)
        if ch:
            lines += ["## Chapters"] + [f"{ts} {name}" for ts, name in ch] + [""]
    cr = credits_from_manifest(manifest)
    lines += ["## Credits"]
    lines += (
        [f"- {c}" for c in cr]
        if cr
        else [
            "- _No third-party assets recorded. If any were used, add their credits._"
        ]
    )
    lines += [
        "",
        "## AI / synthetic-content disclosure",
        (
            "If realistic synthetic voice, people, places or events were generated, use the platform's "
            "disclosure toggle and say so in the description. Suggested line:"
        ),
        "> This video was made with AI-assisted tools (visuals/voice generated). Facts are sourced in-frame.",
        "",
    ]
    if thumbs and thumbs.is_dir():
        pick = pick_thumbnail(thumbs)
        if pick:
            lines += [
                "## Thumbnail candidate",
                f"`{pick[0].name}` (luminance contrast {pick[1]:.1f}) — heuristic only; review by eye.",
                "",
            ]
    lines += [
        "## Pre-publish checklist",
        "- [ ] Original value added (commentary, structure, visuals) — not just reuploaded or templated content",
        "- [ ] Every factual claim has an on-screen source; opinion is labelled as opinion",
        "- [ ] No fabricated quotes, footage or real-person likeness presented as real",
        "- [ ] Music/fonts/images are licensed for monetised use; credits above are complete",
        "- [ ] AI disclosure toggle set where required",
        "- [ ] Captions inside platform safe zones; hook readable on frame 0",
        "",
        "## Policy references (verify current wording before publishing)",
    ]
    lines += [f"- [{name}]({url})" for name, url in POLICY_LINKS.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write publish_kit.md from a storyboard")
    ap.add_argument("storyboard", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("publish_kit.md"))
    ap.add_argument("--manifest", type=Path, default=None, help="assets/manifest.json")
    ap.add_argument("--thumbnails", type=Path, default=None, help="dir of scene PNGs")
    args = ap.parse_args(argv)
    try:
        board = json.loads(args.storyboard.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"publish_kit: cannot read storyboard: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(
        build_kit(board, args.manifest, args.thumbnails), encoding="utf-8"
    )
    print(f"publish_kit: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
