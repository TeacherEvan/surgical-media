#!/usr/bin/env python3
"""fetch_scene_assets.py — per-beat licensed imagery acquisition.

The v3.1 flow fetched ONE query for the whole video, then asset_wire round-
robined those few plates across every scene. A ten-beat video about a subject
with distinct angles is still visually wrong. This tool derives a focused
query for each scene (explicit ``visual.query``, else the most informative
words of its narration, else the board subject), de-duplicates them, and
calls ``fetch_assets.py`` for each into a single shared manifest (its manifest
merge is already multi-query safe).

    python3 scripts/fetch_scene_assets.py --input script.spoken.json \
        --out-dir assets --count 3 --subject "emperor penguin"
    python3 scripts/tts_align.py ... --assets-manifest assets/manifest.json

Network is only touched in the real run. ``--dry-run`` prints the query plan
and is what the offline tests exercise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import fetch_assets


def _scene_query(scene: dict[str, Any], subject: str) -> str:
    """Explicit art direction wins; otherwise take content words from narration.

    Keeps proper nouns and the rarest words (informative for image search)
    rather than the first N tokens, which are usually connective tissue.
    """
    visual = scene.get("visual")
    visual = visual if isinstance(visual, dict) else {}
    explicit = str(visual.get("query", "")).strip()
    if explicit:
        return explicit
    text = f"{subject} {scene.get('narration', '')}"
    words = [
        w for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text) if w.lower() not in _STOP
    ]
    # Preserve original order, but rank by rarity across the text so
    # "emperor penguin" survives and "watch/arrives" drop out.
    freq: dict[str, int] = {}
    for w in words:
        freq[w.lower()] = freq.get(w.lower(), 0) + 1
    ranked = sorted(words, key=lambda w: (freq[w.lower()], len(w)), reverse=True)
    seen: set[str] = set()
    picked: list[str] = []
    for w in ranked:
        if w.lower() not in seen:
            seen.add(w.lower())
            picked.append(w)
        if len(picked) == 4:
            break
    return " ".join(picked) or subject


_STOP = frozenset(
    [
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
        "scene",
        "beat",
        "video",
        "watch",
        "see",
        "look",
        "now",
        "next",
        "here",
        "there",
        "people",
        "thing",
        "things",
        "something",
        "first",
        "last",
    ]
)


def derive_queries(data: dict[str, Any], subject: str = "") -> list[dict[str, str]]:
    """Return [{scene_id, query}] with duplicates collapsed case-insensitively."""
    scenes = [s for s in data.get("scenes", []) if isinstance(s, dict)]
    subj = subject or str(data.get("subject", ""))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, scene in enumerate(scenes):
        sid = str(scene.get("scene_id", f"scene_{i + 1:02d}"))
        query = _scene_query(scene, subj)
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"scene_id": sid, "query": query})
    return out


def fetch_all(
    queries: list[dict[str, str]],
    out_dir: Path,
    count: int,
    min_width: int,
    timeout: float,
    dry_run: bool,
    fallback: str = "",
) -> int:
    """Fetch each distinct query into the shared manifest; 0 on any success.

    A beat-specific query that returns nothing is retried once with the broad
    board subject, so the scene gets a *different* relevant plate from the
    pool instead of round-robining the single hero image.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    for item in queries:
        query = item["query"]
        print(f"fetch_scene_assets: [{item['scene_id']}] {query!r}")
        rc = fetch_assets.download_assets(
            query, out_dir, count, min_width, timeout, dry_run
        )
        if rc != 0 and fallback and fallback.strip().lower() != query.strip().lower():
            print(
                f"fetch_scene_assets: [{item['scene_id']}] retrying with subject {fallback!r}",
                file=sys.stderr,
            )
            rc = fetch_assets.download_assets(
                fallback, out_dir, count, min_width, timeout, dry_run
            )
        if rc == 0:
            ok += 1
        else:
            print(
                f"fetch_scene_assets: no imagery for {item['scene_id']!r} "
                f"({query!r}) — that beat will fall back to round-robin",
                file=sys.stderr,
            )
    if not dry_run and ok == 0:
        print("fetch_scene_assets: every query failed", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", required=True, type=Path, help="Beat script or storyboard JSON"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("assets"))
    parser.add_argument("--count", type=int, default=3, help="Plates per query")
    parser.add_argument("--min-width", type=int, default=800)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--subject", default="")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the query plan, no network"
    )
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
            raise TypeError(f"{args.input}: expected an object with scenes[]")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"fetch_scene_assets: {exc}", file=sys.stderr)
        return 2
    queries = derive_queries(data, args.subject)
    if not queries:
        print("fetch_scene_assets: no scenes to fetch", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(queries, indent=2, ensure_ascii=False))
        return 0
    return fetch_all(
        queries,
        args.out_dir,
        args.count,
        args.min_width,
        args.timeout,
        args.dry_run,
        fallback=str(data.get("subject", args.subject) or args.subject),
    )


if __name__ == "__main__":
    raise SystemExit(main())
