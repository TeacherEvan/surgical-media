#!/usr/bin/env python3
"""fetch_assets.py — acquire licensed subject imagery for an investigation.

Stage 1 of the surgical-media pipeline must leave the subject on screen.
This tool searches multiple open-licensing APIs for photographs —
Openverse (https://openverse.org), Wikimedia Commons originals (via the
MediaWiki API, with 2048 px thumbnails), and iNaturalist (CC-licensed nature
photographs) — filters to licenses the pipeline may remix, downloads them
with a proper User-Agent, verifies each file decodes via Pillow, and writes
``assets/manifest.json`` with per-image attribution strings ready to paste
into storyboard `image` elements.

License allowlist (lowercase, version-agnostic): ``by``, ``by-sa``, ``cc0``,
``pdm``. ``*-nd`` (no derivatives) forbids caption overlays; ``*-nc``
(non-commercial) forbids use in monetized social output. Everything else is
rejected. This is a curated fetcher, not an indiscriminate scraper: never
hotlink images into a render, always ship the manifest's attribution.

``--source`` selects the API set: ``openverse`` (broad web), ``commons``
(original-resolution Wikimedia files — where the large plates live), or
``inaturalist`` (CC-licensed wildlife photography). Default: ``all``.

Network access is required. Tests for this module run offline: license
filtering, attribution formatting, manifest building, and URL construction
are pure; the download path is exercised with a stubbed HTTP layer.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OPENVERSE_API = "https://api.openverse.org/v1/images/"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
INAT_API = "https://api.inaturalist.org/v1/observations"
SOURCES = ("openverse", "commons", "inaturalist")
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
        if 0 < width < min_width:  # known-but-too-small is rejected; unknown (0) passes
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
                "source": str(item.get("source", "openverse")),
                "attribution": format_attribution(item),
            }
        )
    return {
        "query": query,
        "queries": [query],
        "sources": sorted({str(a.get("source", "openverse")) for a in assets}),
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


def strip_html(text: str) -> str:
    """Commons extmetadata artists carry HTML — strip tags, collapse whitespace."""
    import html

    cleaned = re.sub(r"<[^>]+>", " ", str(text or ""))
    return " ".join(html.unescape(cleaned).split())


def parse_commons_license(text: str | None) -> tuple[str | None, str]:
    """Map Commons LicenseShortName ('CC BY-SA 4.0') to (key, version)."""
    raw = str(text or "").strip()
    if not raw:
        return None, ""
    upper = raw.upper().replace(" ", " ")
    if upper.startswith(("PUBLIC DOMAIN", "PD ")):
        m = re.search(r"(\d[\d.]*)\s*$", raw)
        return "pdm", (m.group(1) if m else "")
    if upper.startswith("CC0"):
        return "cc0", "1.0"  # CC0 has a single version; normalize all its spellings
    if upper.startswith("CC BY-SA"):
        key = "by-sa"
    elif upper.startswith("CC BY"):
        key = "by"
    else:  # NC / ND / other — rejected for remix pipelines
        return None, ""
    m = re.search(r"(\d[\d.]*)\s*$", raw)
    version = m.group(1) if m else ""
    if "NC" in upper or "ND" in upper:
        return None, ""
    return key, version


def commons_url(query: str, limit: int = 12) -> str:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(max(1, min(50, limit))),
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": "2048",
        "format": "json",
    }
    return COMMONS_API + "?" + urllib.parse.urlencode(params)


def search_commons(query: str, page_size: int, timeout: float) -> list[dict[str, Any]]:
    raw = _http_get(commons_url(query, page_size), timeout)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    items: list[dict[str, Any]] = []
    for page in (payload.get("query", {}) or {}).get("pages", {}).values():
        ii = (page.get("imageinfo") or [{}])[0]
        mime = str(ii.get("mime", ""))
        if not mime.startswith("image/") or "svg" in mime:
            continue
        md = ii.get("extmetadata", {}) or {}

        def mdv(key: str, md: dict = md) -> str:
            return str((md.get(key) or {}).get("value", "") or "")

        key, version = parse_commons_license(mdv("LicenseShortName"))
        url = str(ii.get("thumburl") or ii.get("url") or "")
        items.append(
            {
                "title": strip_html(str(page.get("title", "")).removeprefix("File:")),
                "url": url,
                "width": ii.get("thumbwidth") or ii.get("width"),
                "height": ii.get("thumbheight") or ii.get("height"),
                "license": key,
                "license_version": version,
                "license_url": mdv("LicenseUrl"),
                "creator": strip_html(mdv("Artist")) or "Unknown author",
                "foreign_landing_url": str(ii.get("descriptionurl") or url),
                "source": "commons",
            }
        )
    return items


def inaturalist_url(query: str, limit: int = 12) -> str:
    params = {
        "taxon_name": query,
        "photo_license": "cc-by,cc-by-sa,cc0",
        "per_page": str(max(1, min(50, limit))),
        "order_by": "votes",
        "order": "desc",
        "photos": "true",
    }
    return INAT_API + "?" + urllib.parse.urlencode(params)


def search_inaturalist(
    query: str, page_size: int, timeout: float
) -> list[dict[str, Any]]:
    raw = _http_get(inaturalist_url(query, page_size), timeout)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    lic_map = {"cc-by": "by", "cc-by-sa": "by-sa", "cc0": "cc0"}
    items: list[dict[str, Any]] = []
    for obs in payload.get("results", []):
        code = str(obs.get("license_code") or "").lower()
        lic = lic_map.get(code)
        if lic is None:  # nc / all-rights-reserved — rejected
            continue
        taxon = obs.get("taxon") or {}
        common = (
            taxon.get("preferred_common_name") or taxon.get("name") or "Unknown species"
        )
        sci = taxon.get("name") or ""
        title = f"{common} ({sci})" if sci else str(common)
        obs_url = f"https://www.inaturalist.org/observations/{obs.get('id')}"
        for photo in (obs.get("photos") or [])[:1]:
            url = str(photo.get("url", ""))
            for size in ("square", "medium", "large", "small"):
                url = url.replace(f"/{size}.", "/original.")
            if not url.startswith(("http://", "https://")):
                continue
            items.append(
                {
                    "title": title,
                    "url": url,
                    "width": 0,  # unknown until download — passes the width gate
                    "height": 0,
                    "license": lic,
                    "license_version": "",
                    "license_url": str(obs.get("license_url") or ""),
                    "creator": str(
                        (obs.get("user") or {}).get("login") or "Unknown author"
                    ),
                    "foreign_landing_url": obs_url,
                    "source": "inaturalist",
                }
            )
    return items


def search_subject(
    query: str, sources: list[str], page_size: int, timeout: float
) -> list[dict[str, Any]]:
    searchers = {
        "openverse": search_openverse,
        "commons": search_commons,
        "inaturalist": search_inaturalist,
    }
    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for name in sources:
        try:
            found = searchers[name](query, page_size, timeout)
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            print(f"fetch_assets: {name} search failed: {exc}", file=sys.stderr)
            continue
        unique = []
        for it in found:
            it.setdefault("source", name)
            url = str(it.get("url", ""))
            if url in seen_urls:  # same plate licensed on two hosts — keep first
                continue
            seen_urls.add(url)
            unique.append(it)
        print(f"fetch_assets: {name}: {len(unique)} candidates")
        items.extend(unique)
    return items


def search_openverse(
    query: str, page_size: int, timeout: float
) -> list[dict[str, Any]]:
    raw = _http_get(openverse_url(query, page_size), timeout)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    results = list(payload.get("results", []))
    for item in results:
        item.setdefault("source", "openverse")
    return results


def download_assets(
    query: str,
    out_dir: Path,
    count: int,
    min_width: int,
    timeout: float,
    dry_run: bool,
    sources: tuple[str, ...] = SOURCES,
) -> int:
    print(f"fetch_assets: searching {', '.join(sources)} for {query!r}")
    results = search_subject(
        query, list(sources), page_size=min(20, count * 3 + 4), timeout=timeout
    )
    if not results:
        print("fetch_assets: all searches failed or returned nothing", file=sys.stderr)
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
                f"fetch_assets: [dry-run] would save {name} "
                f"({item.get('width')}x{item.get('height')}, {item.get('license')}, {item.get('source', '?')})"
            )
            saved.append(item)
            continue
        (out_dir / name).write_bytes(data)
        saved.append(item)
        print(
            f"fetch_assets: saved {name} ({img.size[0]}x{img.size[1]}, {item.get('license')}, {item.get('source', '?')}) — {format_attribution(item)}"
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
            prior_sources = prior.get("sources") or []
            manifest["sources"] = sorted({*prior_sources, *manifest["sources"]})
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
        "--source",
        choices=("openverse", "commons", "inaturalist", "all"),
        default="all",
        help="Licensed-imagery source(s); default: all (openverse + commons + inaturalist)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the manifest without downloading"
    )
    args = parser.parse_args()
    sources = SOURCES if args.source == "all" else (args.source,)
    return download_assets(
        args.query,
        args.out_dir,
        args.count,
        args.min_width,
        args.timeout,
        args.dry_run,
        sources,
    )


if __name__ == "__main__":
    raise SystemExit(main())
