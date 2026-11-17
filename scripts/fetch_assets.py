#!/usr/bin/env python3
"""fetch_assets.py — acquire licensed subject imagery for an investigation.

Stage 1 of the surgical-media pipeline must leave the subject on screen.
This tool searches Openverse (https://openverse.org) for open-licensed
photographs, filters to licenses the pipeline may remix, downloads them
with a proper User-Agent, verifies each file decodes via Pillow, and writes
``assets/manifest.json`` with per-image attribution strings ready to paste
into storyboard `image` elements.

License allowlist (lowercase, version-agnostic): ``by``, ``by-sa``, ``cc0``,
``pdm``. ``*-nd`` (no derivatives) forbids caption overlays; ``*-nc``
(non-commercial) forbids use in monetized social output. Everything else is
rejected. This is a curated fetcher, not an indiscriminate scraper: never
hotlink images into a render, always ship the manifest's attribution.

Network access is required. Tests for this module run offline: license
filtering, attribution formatting, manifest building, and URL construction
are pure; the download path is exercised with a stubbed HTTP layer.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "surgical-media/1.0 (open-licensed fetcher; +https://github.com/TeacherEvan/surgical-media)"
ALLOWED_LICENSES = {"by", "by-sa", "cc0", "pdm"}
LICENSE_LABELS = {
    "by": "CC BY",
    "by-sa": "CC BY-SA",
    "cc0": "CC0",
    "pdm": "PUBLIC DOMAIN",
}
IMAGE_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


def openverse_url(query: str, page_size: int = 12) -> str:
    params = {
        "q": query,
        "page_size": str(max(1, min(20, page_size))),
        "mature": "false",
    }
    return OPENVERSE_API + "?" + urllib.parse.urlencode(params)


def license_key(license_code: str | None) -> str | None:
    if not license_code:
        return None
    code = str(license_code).strip().lower()
    if code in ALLOWED_LICENSES:
        return code
    # tolerate "by 2.0" / "by-sa 4.0" style strings that some sources emit
    base = code.split()[0].split("/")[-1]
    return base if base in ALLOWED_LICENSES else None


def filter_results(
    results: list[dict[str, Any]], min_width: int = 800
) -> list[dict[str, Any]]:
    """Allowlisted licenses only, verified dimensions, deduped, largest first."""
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for r in results:
        if license_key(r.get("license")) is None:
            continue
        url = str(r.get("url", ""))
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        try:
            width = int(r.get("width") or 0)
        except (TypeError, ValueError):
            width = 0
        if width < min_width:
            continue
        seen.add(url)
        kept.append(r)
    kept.sort(key=lambda r: int(r.get("width") or 0), reverse=True)
    return kept


def format_attribution(item: dict[str, Any]) -> str:
    lic = license_key(item.get("license")) or str(item.get("license", "")).upper()
    label = LICENSE_LABELS.get(lic, lic.upper())
    version = str(item.get("license_version", "")).strip()
    lic_text = f"{label} {version}".strip()
    creator = str(item.get("creator") or "Unknown author").strip()
    title = str(item.get("title") or "Untitled").strip()
    source = str(item.get("foreign_landing_url") or item.get("url", "")).strip()
    return f"{creator} — {title} · {lic_text} · {source}"


def build_manifest(query: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    assets = []
    for item in items:
        lic = license_key(item.get("license")) or str(item.get("license", ""))
        assets.append(
            {
                "file": item["_saved_as"],
                "title": str(item.get("title", "")),
                "creator": str(item.get("creator", "")),
                "license": lic,
                "license_version": str(item.get("license_version", "")),
                "license_url": str(item.get("license_url", "")),
                "source_url": str(item.get("foreign_landing_url", "")),
                "url": str(item.get("url", "")),
                "width": item.get("width"),
                "height": item.get("height"),
                "attribution": format_attribution(item),
            }
        )
    return {
        "query": query,
        "queries": [query],
        "retrieved": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(assets),
        "assets": assets,
    }


def _decode_to_ext(data: bytes) -> tuple[Any, str] | tuple[None, str]:
    """Verify bytes are a decodable image; return (PIL image, extension)."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:  # noqa: BLE001 — any decode failure disqualifies the asset
        return None, ""
    ext = IMAGE_EXTENSIONS.get(img.format or "", ".jpg")
    return img, ext


def _http_get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def search_openverse(
    query: str, page_size: int, timeout: float
) -> list[dict[str, Any]]:
    raw = _http_get(openverse_url(query, page_size), timeout)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    return list(payload.get("results", []))


def download_assets(
    query: str,
    out_dir: Path,
    count: int,
    min_width: int,
    timeout: float,
    dry_run: bool,
) -> int:
    print(f"fetch_assets: searching Openverse for {query!r}")
    try:
        results = search_openverse(
            query, page_size=min(20, count * 3 + 4), timeout=timeout
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"fetch_assets: search failed: {exc}", file=sys.stderr)
        return 2

    candidates = filter_results(results, min_width=min_width)
    if not candidates:
        print("fetch_assets: no open-licensed candidates found", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, Any]] = []
    for item in candidates:
        if len(saved) >= count:
            break
        url = str(item["url"])
        title_slug = (
            "".join(
                c if c.isalnum() else "_" for c in str(item.get("title", "asset"))[:48]
            )
            .strip("_")
            .lower()
        )
        try:
            data = _http_get(url, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"fetch_assets: skipping {url}: {exc}", file=sys.stderr)
            continue
        img, ext = _decode_to_ext(data)
        if img is None:
            print(f"fetch_assets: skipping undecodable asset: {url}", file=sys.stderr)
            continue
        name = f"{len(saved) + 1:02d}_{title_slug or 'asset'}{ext}"
        item = dict(item)
        item["_saved_as"] = name
        if dry_run:
            print(
                f"fetch_assets: [dry-run] would save {name} ({item.get('width')}x{item.get('height')}, {item.get('license')})"
            )
            saved.append(item)
            continue
        (out_dir / name).write_bytes(data)
        saved.append(item)
        print(
            f"fetch_assets: saved {name} ({img.size[0]}x{img.size[1]}, {item.get('license')}) — {format_attribution(item)}"
        )

    if not saved:
        print("fetch_assets: nothing downloaded", file=sys.stderr)
        return 2

    manifest = build_manifest(query, saved)
    manifest_path = out_dir / "manifest.json"
    if manifest_path.is_file() and not dry_run:
        # multi-angle investigations: merge with prior runs instead of clobbering
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            merged_files = {a["file"] for a in manifest["assets"]}
            prior_assets = [
                a for a in prior.get("assets", []) if a.get("file") not in merged_files
            ]
            manifest["assets"] = prior_assets + manifest["assets"]
            manifest["count"] = len(manifest["assets"])
            prior_queries = prior.get("queries") or [prior.get("query", query)]
            manifest["queries"] = sorted({*prior_queries, query})
        except (json.JSONDecodeError, OSError):
            pass
    if not dry_run:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"fetch_assets: wrote {manifest_path} ({manifest['count']} assets)")
    else:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--query", required=True, help="Subject to search, e.g. 'emperor penguin'"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory to save assets + manifest.json",
    )
    parser.add_argument(
        "--count", type=int, default=3, help="Assets to download (default: 3)"
    )
    parser.add_argument(
        "--min-width",
        type=int,
        default=800,
        help="Reject images narrower than this (default: 800 px)",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="HTTP timeout in seconds"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the manifest without downloading"
    )
    args = parser.parse_args()
    return download_assets(
        args.query, args.out_dir, args.count, args.min_width, args.timeout, args.dry_run
    )


if __name__ == "__main__":
    raise SystemExit(main())
