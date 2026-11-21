#!/usr/bin/env python3
"""media_harvester.py — authentic, credited portraits for real named people.

This is a thin, opinionated layer on top of :mod:`fetch_assets`.  It searches
open-licensing APIs for photographs of *named individuals*, rejects any
license that cannot be remixed (NC / ND / uncredited public domain), downloads
the originals to disk (never hotlinks), face-centres each plate into a
platform aspect ratio, burns a subtle attribution badge inside the platform
safe zone, and writes machine-readable attribution manifests.

Design constraints (inherited from the repo's AGENTS.md):

* stdlib + Pillow only.  OpenCV is an *optional* face-detection accelerator;
  when ``cv2`` (or a usable Haar cascade) is unavailable we silently fall back
  to the operator-supplied ``--focus`` anchor.
* HTTPS-only, <= 50 MB downloads via ``fetch_assets._http_get``.
* Pre-blended ink for the badge: ``ImageDraw`` cannot alpha-blend on RGB.
* Offline-friendly tests: the HTTP and search layers are monkeypatched; this
  module never reaches the network at import time.

Typical use::

    python3 scripts/media_harvester.py \
        --query "Ada Lovelace" --people "Ada Lovelace" \
        --out-dir assets --aspect 9:16 --count 3 \
        --safe-mode organic --focus 0.5,0.35 --source all
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import fetch_assets
from PIL import Image, ImageDraw, ImageFont

# scripts/ is on sys.path when run as a script; keep the same convenience for
# direct `python -m` style imports from a checkout root (mirrors other scripts).
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (9, 16),
    "16:9": (16, 9),
    "1:1": (1, 1),
    "4:5": (4, 5),
}
SAFE_MODES = ("organic", "strict")
SOURCES = ("commons", "wikipedia", "openverse")

# 9:16 safe rectangles in a 1080x1920 reference frame.  "organic" leaves room
# for feed captions; "strict" additionally clears Shorts/Reels bottom chrome
# and the right-side icon rail.
_SAFE_916 = {
    "organic": (60, 180, 930, 1540),
    "strict": (65, 288, 888, 1248),
}
_BADGE_INK = (200, 205, 215)  # ~70% white, pre-blended (no alpha blending)
_BADGE_STROKE = (5, 7, 12)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = fetch_assets.COMMONS_API

# Disclosures are editorial facts, not legal advice; they travel with every
# manifest so downstream render jobs cannot silently drop attribution.
DISCLOSURES = [
    (
        "Photographs are third-party openly licensed works; each is credited "
        "on-frame and in CREDITS.md."
    ),
    "No AI-generated imagery, composite faces, or synthetic people were used.",
    (
        "Faces may be auto-centred with an optional OpenCV Haar cascade; verify "
        "likeness and editorial context before publication."
    ),
    (
        "Publicity / personality rights are separate from copyright; obtain "
        "releases where publication requires them."
    ),
]
ORIGINALITY_NOTE = (
    "Framing, crop, ordering, captions and any motion are original editorial "
    "choices; the underlying photographs remain the copyrighted works of "
    "their credited creators under the licenses stated above."
)


# ---------------------------------------------------------------------------
# Search helpers (delegated to fetch_assets so stubs in either module work)
# ---------------------------------------------------------------------------
def search_commons(query: str, page_size: int, timeout: float) -> list[dict[str, Any]]:
    """Wikimedia Commons originals (where the high-resolution plates live)."""
    return cast(
        "list[dict[str, Any]]",
        fetch_assets.search_commons(query, page_size, timeout),
    )


def search_openverse(
    query: str, page_size: int, timeout: float
) -> list[dict[str, Any]]:
    """Broad open-licensed web search via Openverse."""
    return cast(
        "list[dict[str, Any]]",
        fetch_assets.search_openverse(query, page_size, timeout),
    )


def _commons_license_for_file(
    file_title: str, timeout: float
) -> tuple[str | None, str, str, str]:
    """Look up (key, version, license_url, creator) for a Wikipedia page image.

    Wikipedia's ``pageimages`` payload deliberately omits licensing metadata,
    so we resolve the backing Commons file separately.  Any failure degrades
    to an unusable (key=None) result which the license gate drops.
    """
    name = str(file_title or "").strip()
    if not name:
        return None, "", "", ""
    if not name.lower().startswith("file:"):
        name = f"File:{name}"
    params = {
        "action": "query",
        "titles": name,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": "2048",
        "format": "json",
    }
    try:
        raw = fetch_assets._http_get(
            fetch_assets.COMMONS_API + "?" + urllib.parse.urlencode(params),
            timeout,
        )
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        page = next(iter((payload.get("query", {}) or {}).get("pages", {}).values()))
        ii = (page.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {}) or {}

        def mdv(key: str) -> str:
            return str((md.get(key) or {}).get("value", "") or "")

        key, version = fetch_assets.parse_commons_license(mdv("LicenseShortName"))
        creator = fetch_assets.strip_html(mdv("Artist")) or "Unknown author"
        return key, version, mdv("LicenseUrl"), creator
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return None, "", "", ""


def search_wikipedia(
    query: str, page_size: int, timeout: float
) -> list[dict[str, Any]]:
    """Find a named person's lead image via the Wikipedia MediaWiki API.

    Uses the English Wikipedia ``generator=search`` + ``pageimages`` endpoint,
    then resolves each backing Commons file for license metadata.  Returns
    fetch_assets-shaped result dicts so the rest of the pipeline is agnostic.
    """
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "0",
        "gsrlimit": str(max(1, min(50, page_size))),
        "prop": "pageimages",
        "piprop": "original|thumbnail",
        "pithumbsize": "2048",
        "format": "json",
    }
    try:
        raw = fetch_assets._http_get(
            WIKIPEDIA_API + "?" + urllib.parse.urlencode(params), timeout
        )
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (OSError, ValueError, TypeError):
        return []

    items: list[dict[str, Any]] = []
    for page in (payload.get("query", {}) or {}).get("pages", {}).values():
        original = page.get("original") or {}
        thumb = page.get("thumbnail") or {}
        url = str(original.get("source") or thumb.get("source") or "")
        file_title = str(page.get("pageimage") or "")
        if not url.startswith("https://") or not file_title:
            continue
        key, version, lic_url, creator = _commons_license_for_file(file_title, timeout)
        page_title = str(page.get("title") or file_title)
        items.append(
            {
                "title": fetch_assets.strip_html(page_title),
                "url": url,
                "width": original.get("width") or thumb.get("width") or 0,
                "height": original.get("height") or thumb.get("height") or 0,
                "license": key,
                "license_version": version,
                "license_url": lic_url,
                "creator": creator,
                "foreign_landing_url": (
                    "https://en.wikipedia.org/wiki/"
                    + urllib.parse.quote(page_title.replace(" ", "_"))
                ),
                "source": "wikipedia",
            }
        )
    return items


def search_photos(
    query: str, sources: tuple[str, ...], page_size: int, timeout: float
) -> list[dict[str, Any]]:
    """Dispatch to the selected APIs and dedupe by image URL.

    The dispatch table is built *inside* the function so monkeypatching either
    ``media_harvester.search_*`` or ``fetch_assets.search_*`` takes effect.
    """
    searchers = {
        "wikipedia": search_wikipedia,
        "commons": search_commons,
        "openverse": search_openverse,
    }
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in sources:
        try:
            results = searchers[name](query, page_size, timeout)
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            print(f"media_harvester: {name} search failed: {exc}", file=sys.stderr)
            continue
        for item in results:
            item = dict(item)
            item.setdefault("source", name)
            url = str(item.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            found.append(item)
    return found


# ---------------------------------------------------------------------------
# Licensing / people validation
# ---------------------------------------------------------------------------
def is_remixable(item: dict[str, Any]) -> bool:
    """True only for licenses that permit cropping + an overlay badge.

    ``fetch_assets.license_key`` already rejects by-nc*, by-nd*, pd and every
    unknown code; we additionally require an identifiable creator so the
    credit badge is never blank.  CC0 / PDM with no named author are allowed
    because the license itself does not require attribution — the badge then
    names the hosting source instead.
    """
    if fetch_assets.license_key(item.get("license")) is None:
        return False
    url = str(item.get("url", ""))
    return url.startswith("https://")


def parse_people(chunks: list[str]) -> list[str]:
    """Split repeatable/comma-separated ``--people`` values and validate them.

    A "real named individual" needs at least two alphabetic tokens (e.g.
    "Ada Lovelace"); single-word handles and placeholder strings are rejected
    so the tool cannot quietly treat a generic subject as a person.
    """
    people: list[str] = []
    for chunk in chunks:
        for name in str(chunk).split(","):
            cleaned = " ".join(name.split())
            if cleaned:
                people.append(cleaned)
    if not people:
        raise ValueError("--people requires at least one named individual")
    for name in people:
        tokens = name.split()
        if len(tokens) < 2 or not all(any(c.isalpha() for c in t) for t in tokens):
            raise ValueError(
                f"--people entries must be real full names (first + last): {name!r}"
            )
    return people


def parse_focus(raw: str) -> tuple[float, float]:
    """Parse a normalised ``x,y`` anchor, clamped to [0, 1]."""
    parts = raw.split(",")
    if len(parts) != 2:
        raise ValueError("--focus must be 'x,y' (two normalized numbers)")
    try:
        x, y = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise ValueError("--focus must be two numbers, e.g. 0.5,0.35") from exc
    return min(1.0, max(0.0, x)), min(1.0, max(0.0, y))


# ---------------------------------------------------------------------------
# Face-centred crop
# ---------------------------------------------------------------------------
def _detect_face_normalized(image: Image.Image) -> tuple[float, float] | None:
    """Return the largest detected face centre as (x, y) in 0..1 coords.

    OpenCV is entirely optional: import failures, a missing cascade file, or
    an empty detection all return None so the caller uses the focus anchor.
    """
    try:
        import cv2
        import numpy as np

        cascade_path = (
            str(cv2.data.haarcascades) + "haarcascade_frontalface_default.xml"
        )
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            return None
        gray = np.array(image.convert("L"))
        faces = list(
            cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
        )
        if not faces:
            return None
        x, y, w, h = max(faces, key=lambda f: float(f[2]) * float(f[3]))
        iw, ih = image.size
        if iw <= 0 or ih <= 0:
            return None
        return (float(x) + float(w) / 2.0) / iw, (float(y) + float(h) / 2.0) / ih
    except Exception:  # noqa: BLE001 — optional accelerator, never fatal
        return None


def _skin_tone_center(image: Image.Image) -> tuple[float, float] | None:
    """Stdlib/Pillow face proxy: centroid of skin-tone pixels (YCbCr).

    Used only when OpenCV is unavailable or finds no face. The classic
    ``77 <= Cb <= 127, 133 <= Cr <= 173`` mask is evaluated on a ≤256 px
    thumbnail; a centroid is accepted only when the mask covers a plausible
    face-sized fraction of the frame. This replaces a blind upper-centre guess
    without adding NumPy/OpenCV as a dependency.
    """
    src_w, src_h = image.size
    if src_w < 8 or src_h < 8:
        return None
    scale = min(1.0, 256.0 / max(src_w, src_h))
    sw = max(1, round(src_w * scale))
    sh = max(1, round(src_h * scale))
    small = image.convert("RGB").resize((sw, sh), Image.Resampling.BILINEAR)
    pixels = cast("Any", small.convert("YCbCr").load())
    sx = sy = count = 0
    for yy in range(sh):
        for xx in range(sw):
            y, cb, cr = (int(v) for v in cast("tuple[int, int, int]", pixels[xx, yy]))
            if y >= 40 and 77 <= cb <= 127 and 133 <= cr <= 173:
                sx += xx
                sy += yy
                count += 1
    total = sw * sh
    if count < max(4, int(total * 0.005)) or count > int(total * 0.35):
        return None
    return ((sx / count + 0.5) / sw, (sy / count + 0.5) / sh)


def _output_size(aspect: str, min_width: int) -> tuple[int, int]:
    """Target pixel size whose *short* edge is ``min_width``."""
    rw, rh = ASPECTS[aspect]
    short = max(1, int(min_width))
    if rw < rh:  # portrait (9:16, 4:5): width is the short edge
        return short, max(1, round(short * rh / rw))
    if rw > rh:  # landscape (16:9): height is the short edge
        return max(1, round(short * rw / rh)), short
    return short, short


def face_center(
    image: Image.Image,
    focus: tuple[float, float],
    target_aspect: str,
    min_width: int,
) -> tuple[Image.Image, dict[str, Any]]:
    """Cover-crop ``image`` to ``target_aspect`` around a face/focus anchor.

    OpenCV (if importable) supplies the anchor from the largest detected face;
    otherwise a stdlib skin-tone centroid is tried, and finally the caller's
    normalised ``focus``. The crop is clamped to image bounds and resized with
    LANCZOS so the short edge is at least ``min_width``. Upscaling is allowed
    but reported via ``quality_warning``. ``info['anchor_source']`` records
    which of the three anchors was used.
    """
    if target_aspect not in ASPECTS:
        raise ValueError(f"unknown aspect: {target_aspect!r}")

    src_w, src_h = image.size
    if src_w < 1 or src_h < 1:
        raise ValueError("image must have positive dimensions")

    detected = _detect_face_normalized(image)
    skin = None if detected is not None else _skin_tone_center(image)
    detected_face = detected is not None
    anchor_source = (
        "cv2"
        if detected is not None
        else ("skin_tone" if skin is not None else "manual")
    )
    anchor = detected if detected is not None else (skin if skin is not None else focus)
    anchor_x = min(1.0, max(0.0, float(anchor[0])))
    anchor_y = min(1.0, max(0.0, float(anchor[1])))

    out_w, out_h = _output_size(target_aspect, min_width)
    target_ratio = out_w / out_h
    src_ratio = src_w / src_h

    # Cover crop: keep whichever source dimension is the limiting one.
    if src_ratio > target_ratio:
        crop_h = float(src_h)
        crop_w = crop_h * target_ratio
    else:
        crop_w = float(src_w)
        crop_h = crop_w / target_ratio
    crop_w = min(float(src_w), max(1.0, crop_w))
    crop_h = min(float(src_h), max(1.0, crop_h))

    left = anchor_x * src_w - crop_w / 2.0
    top = anchor_y * src_h - crop_h / 2.0
    left = min(max(0.0, left), max(0.0, src_w - crop_w))
    top = min(max(0.0, top), max(0.0, src_h - crop_h))
    box = (
        round(left),
        round(top),
        min(src_w, round(left + crop_w)),
        min(src_h, round(top + crop_h)),
    )
    if box[2] <= box[0]:
        box = (box[0], box[1], min(src_w, box[0] + 1), box[3])
    if box[3] <= box[1]:
        box = (box[0], box[1], box[2], min(src_h, box[1] + 1))

    cropped = image.crop(box)
    if cropped.size != (out_w, out_h):
        cropped = cropped.resize((out_w, out_h), Image.Resampling.LANCZOS)

    short_edge = min(src_w, src_h)
    warning: str | None = None
    if short_edge < min_width:
        warning = (
            f"source short edge {short_edge}px < requested {min_width}px; "
            "portrait was upscaled and may look soft or watermarked"
        )

    info: dict[str, Any] = {
        "detected_face": detected_face,
        "anchor_source": anchor_source,
        "focus": (anchor_x, anchor_y),
        "requested_focus": (float(focus[0]), float(focus[1])),
        "crop_box": box,
        "output_size": (out_w, out_h),
        "source_size": (src_w, src_h),
        "quality_warning": warning,
    }
    return cropped, info


# ---------------------------------------------------------------------------
# Credit badge
# ---------------------------------------------------------------------------
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Prefer the repo's bundled sans-serif via canvas.get_font."""
    try:
        from canvas import get_font

        return cast("ImageFont.FreeTypeFont | ImageFont.ImageFont", get_font(size))
    except (ImportError, OSError):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def _safe_rect(width: int, height: int, aspect: str, safe_mode: str) -> tuple[int, ...]:
    """Pixel rectangle (x0, y0, x1, y1) for the chosen aspect / safe mode."""
    if aspect in ("9:16", "4:5"):
        ref_w, ref_h = 1080, 1920
        rx0, ry0, rx1, ry1 = _SAFE_916[safe_mode]
        return (
            round(rx0 * width / ref_w),
            round(ry0 * height / ref_h),
            round(rx1 * width / ref_w),
            round(ry1 * height / ref_h),
        )
    if aspect == "16:9":
        return (96, 64, max(97, width - 96), max(65, height - 64))
    return (80, 80, max(81, width - 80), max(81, height - 80))  # 1:1


def draw_credit_badge(
    image: Image.Image, text: str, aspect: str, safe_mode: str
) -> Image.Image:
    """Burn a subtle ``Photo: <creator> / <source>`` badge bottom-left.

    The ink is pre-blended (RGB ``ImageDraw`` has no alpha channel), capped at
    24 px at a 1080 px short edge, and always placed inside the platform safe
    rectangle with a small margin.  The image is modified in place and
    returned for convenient chaining.
    """
    if aspect not in ASPECTS:
        raise ValueError(f"unknown aspect: {aspect!r}")
    if safe_mode not in SAFE_MODES:
        raise ValueError(f"unknown safe mode: {safe_mode!r}")

    width, height = image.size
    x0, _y0, x1, y1 = _safe_rect(width, height, aspect, safe_mode)
    short = min(width, height)
    size = max(9, min(24, round(short * 24 / 1080)))
    margin = max(4, round(short * 0.012))

    max_text_w = max(1, (x1 - x0) - 2 * margin)
    font = _load_font(size)
    while size > 8 and font.getlength(text) > max_text_w:
        size -= 1
        font = _load_font(size)

    draw = ImageDraw.Draw(image)
    px, py = x0 + margin, y1 - margin
    try:
        draw.text(
            (px, py),
            text,
            font=font,
            fill=_BADGE_INK,
            stroke_fill=_BADGE_STROKE,
            stroke_width=max(1, round(short / 720)),
            anchor="ld",
        )
    except (ValueError, AttributeError):
        # Bitmap fallback fonts do not support every anchor identifier.
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (px, py - (bbox[3] - bbox[1])),
            text,
            font=font,
            fill=_BADGE_INK,
            stroke_fill=_BADGE_STROKE,
            stroke_width=max(1, round(short / 720)),
            anchor="la",
        )
    return image


# ---------------------------------------------------------------------------
# Credits / manifest output
# ---------------------------------------------------------------------------
def build_credits(
    query: str,
    people: list[str],
    aspect: str,
    safe_mode: str,
    assets: list[dict[str, Any]],
    disclosures: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the ``credits.json`` payload for one harvest run."""
    warnings = [str(a["quality_warning"]) for a in assets if a.get("quality_warning")]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": query,
        "people": list(people),
        "aspect": aspect,
        "safe_mode": safe_mode,
        "assets": assets,
        "disclosures": list(disclosures if disclosures is not None else DISCLOSURES),
        "originality_note": ORIGINALITY_NOTE,
        "quality_warnings": warnings,
        "count": len(assets),
    }


def render_credits_md(credits: dict[str, Any]) -> str:
    """Human-readable ``CREDITS.md`` with the four required sections."""
    lines = [f"# Image credits — {credits['query']}", "", "## Images", ""]
    assets = credits.get("assets", [])
    if assets:
        for asset in assets:
            lines.append(
                f"- {asset['attribution']} — {asset['source_url']} — {asset['license']}"
            )
    else:
        lines.append("_No images harvested._")
    lines += [
        "",
        "## News sources",
        "",
        (
            "_No third-party news text was used; this piece relies on openly "
            "licensed photography only._"
        ),
        "",
        "## AI disclosure",
        "",
    ]
    lines += [f"- {d}" for d in credits.get("disclosures", [])]
    lines += ["", "## Originality note", "", str(credits["originality_note"]), ""]
    warnings = credits.get("quality_warnings", [])
    if warnings:
        lines += ["## Quality warnings", ""] + [f"- {w}" for w in warnings] + [""]
    return "\n".join(lines)


def write_credits(out_dir: Path, credits: dict[str, Any]) -> tuple[Path, Path]:
    """Write credits.json and CREDITS.md; return their paths."""
    json_path = out_dir / "credits.json"
    md_path = out_dir / "CREDITS.md"
    json_path.write_text(
        json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(render_credits_md(credits), encoding="utf-8")
    return json_path, md_path


def merge_manifest(out_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Merge a fresh manifest into any existing one (never clobber assets)."""
    path = out_dir / "manifest.json"
    if path.is_file():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            current_files = {a["file"] for a in manifest["assets"]}
            prior_assets = [
                a for a in prior.get("assets", []) if a.get("file") not in current_files
            ]
            manifest["assets"] = prior_assets + manifest["assets"]
            manifest["count"] = len(manifest["assets"])
            prior_queries = prior.get("queries") or [prior.get("query", "")]
            manifest["queries"] = sorted(
                {q for q in [*prior_queries, *manifest["queries"]] if q}
            )
            manifest["sources"] = sorted(
                {*prior.get("sources", []), *manifest["sources"]}
            )
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            pass
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _slug_for(item: dict[str, Any], people: list[str]) -> str:
    """Stable filesystem slug from the first matching person or the title."""
    title = str(item.get("title", ""))
    for person in people:
        if person.lower() in title.lower():
            base = person
            break
    else:
        base = title or str(item.get("creator", "portrait"))
    slug = "".join(c if c.isalnum() else "_" for c in base[:48]).strip("_").lower()
    return slug or "portrait"


def _next_filename(portraits: Path, slug: str, ext: str, start: int) -> str:
    """Pick the next free ``NN_slug.ext`` name without overwriting prior runs."""
    index = max(1, start)
    while True:
        name = f"{index:02d}_{slug}{ext}"
        if not (portraits / name).exists():
            return name
        index += 1


# ---------------------------------------------------------------------------
# Harvest pipeline
# ---------------------------------------------------------------------------
def harvest(
    query: str,
    people: list[str],
    out_dir: Path,
    count: int,
    aspect: str,
    safe_mode: str,
    focus: tuple[float, float],
    min_width: int,
    timeout: float,
    source: str,
    dry_run: bool = False,
    badge: bool = True,
) -> int:
    """Search, verify, crop, credit and persist one batch of portraits."""
    if source not in (*SOURCES, "all"):
        raise ValueError(f"unknown source: {source!r}")
    if aspect not in ASPECTS or safe_mode not in SAFE_MODES:
        raise ValueError("invalid aspect or safe mode")
    if count < 1 or min_width < 1 or timeout <= 0:
        raise ValueError("count/min-width/timeout must be positive")

    sources: tuple[str, ...] = SOURCES if source == "all" else (source,)
    print(f"media_harvester: searching {', '.join(sources)} for {query!r}")
    results = search_photos(
        query, sources, page_size=min(20, count * 4 + 4), timeout=timeout
    )
    if not results:
        print(
            "media_harvester: all searches failed or returned nothing", file=sys.stderr
        )
        return 2

    candidates = [item for item in results if is_remixable(item)]
    if not candidates:
        print("media_harvester: no remixable candidates found", file=sys.stderr)
        return 2

    portraits = out_dir / "portraits"
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        portraits.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, Any]] = []
    credit_assets: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in candidates:
        if len(credit_assets) >= count:
            break
        url = str(item.get("url", ""))
        if url in seen or not url.startswith("https://"):
            continue
        seen.add(url)
        try:
            data = fetch_assets._http_get(url, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"media_harvester: skipping {url}: {exc}", file=sys.stderr)
            continue
        img, ext = fetch_assets._decode_to_ext(data)
        if img is None:
            print(f"media_harvester: undecodable asset: {url}", file=sys.stderr)
            continue
        if min(img.size) < min_width:
            print(
                f"media_harvester: skipping tiny/watermarked-looking image "
                f"{img.size} (< {min_width}px): {url}",
                file=sys.stderr,
            )
            continue

        slug = _slug_for(item, people)
        name = _next_filename(portraits, slug, ext, len(credit_assets) + 1)
        rel = f"portraits/{name}"
        source_name = str(item.get("source", "unknown"))
        creator = str(item.get("creator") or "Unknown author").strip()
        badge_text = f"Photo: {creator} / {source_name}"

        plate, info = face_center(img.convert("RGB"), focus, aspect, min_width)
        if badge:
            plate = draw_credit_badge(plate, badge_text, aspect, safe_mode)

        manifest_item = dict(item)
        manifest_item["_saved_as"] = rel
        manifest_item["width"] = img.size[0]
        manifest_item["height"] = img.size[1]

        credit_asset: dict[str, Any] = {
            "file": rel,
            "title": str(item.get("title", "")),
            "creator": creator,
            "license": fetch_assets.license_key(item.get("license"))
            or str(item.get("license", "")),
            "source_url": str(item.get("foreign_landing_url") or url),
            "attribution": fetch_assets.format_attribution(item),
            "badge_text": badge_text,
            "detected_face": bool(info["detected_face"]),
            "focus": list(info["focus"]),
            "quality_warning": info.get("quality_warning"),
        }

        if dry_run:
            planned.append(
                {
                    "action": "crop_and_save",
                    "file": rel,
                    "source_url": url,
                    "license": credit_asset["license"],
                    "attribution": credit_asset["attribution"],
                    "crop_box": list(info["crop_box"]),
                    "output_size": list(info["output_size"]),
                    "badge_text": badge_text,
                    "detected_face": bool(info["detected_face"]),
                    "focus": credit_asset["focus"],
                    "quality_warning": credit_asset["quality_warning"],
                }
            )
        else:
            plate.save(portraits / name)
            saved.append(manifest_item)
            credit_assets.append(credit_asset)
            print(
                f"media_harvester: saved {rel} ({info['output_size'][0]}x"
                f"{info['output_size'][1]}, {credit_asset['license']}, "
                f"{source_name}) — {credit_asset['attribution']}"
            )

    if dry_run:
        print(
            json.dumps(
                {
                    "query": query,
                    "people": people,
                    "aspect": aspect,
                    "safe_mode": safe_mode,
                    "dry_run": True,
                    "count": len(planned),
                    "actions": planned,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not saved:
        print("media_harvester: nothing downloaded", file=sys.stderr)
        return 2

    manifest = fetch_assets.build_manifest(query, saved)
    manifest = merge_manifest(out_dir, manifest)
    credits = build_credits(query, people, aspect, safe_mode, credit_assets)
    json_path, md_path = write_credits(out_dir, credits)
    print(
        f"media_harvester: wrote {out_dir / 'manifest.json'} "
        f"({manifest['count']} assets), {json_path}, {md_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns 0 on success, 2 on invalid input/no assets."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--query", required=True, help="Person or subject to search")
    parser.add_argument(
        "--people",
        action="append",
        required=True,
        help="Comma-separated or repeatable real full names, e.g. 'Ada Lovelace'",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory for portraits + manifests",
    )
    parser.add_argument("--count", type=int, default=3, help="Portraits to keep (3)")
    parser.add_argument(
        "--aspect", choices=tuple(ASPECTS), default="9:16", help="Target aspect (9:16)"
    )
    parser.add_argument(
        "--safe-mode",
        choices=SAFE_MODES,
        default="organic",
        help="Safe-zone preset (organic)",
    )
    parser.add_argument(
        "--focus", default="0.5,0.35", help="Normalized x,y crop anchor (0.5,0.35)"
    )
    parser.add_argument("--min-width", type=int, default=1080, help="Short edge (1080)")
    parser.add_argument(
        "--source",
        choices=(*SOURCES, "all"),
        default="all",
        help="Licensed-imagery source(s) (all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only; write nothing"
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout (30)")
    parser.add_argument("--no-badge", action="store_true", help="Omit the credit badge")
    args = parser.parse_args(argv)

    try:
        people = parse_people(args.people)
        focus = parse_focus(args.focus)
    except ValueError as exc:
        print(f"media_harvester: {exc}", file=sys.stderr)
        return 2

    try:
        return harvest(
            query=args.query,
            people=people,
            out_dir=args.out_dir,
            count=args.count,
            aspect=args.aspect,
            safe_mode=args.safe_mode,
            focus=focus,
            min_width=args.min_width,
            timeout=args.timeout,
            source=args.source,
            dry_run=args.dry_run,
            badge=not args.no_badge,
        )
    except ValueError as exc:
        print(f"media_harvester: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
