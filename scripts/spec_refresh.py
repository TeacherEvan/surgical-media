#!/usr/bin/env python3
"""spec_refresh.py — executable, auditable v3.0.0 Step 2 live spec refresh.

Parses the baked-in platform/licensing reference and checks that every baseline
fact is still present (local drift gate). Optionally performs *advisory* HTTPS
marker probes against authoritative sources — live results are recorded but are
never fatal and never change the exit code.

Stdlib-only and offline-safe: no shell, no third-party deps, no data files.

    python3 scripts/spec_refresh.py --check
    python3 scripts/spec_refresh.py --check --fetch --out spec_report.json

Exit 0 = local baseline intact, 3 = local drift detected, 2 = bad/unreadable doc.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

BASELINE_DATE = "2026-11-21"

DEFAULT_DOC = (
    Path(__file__).resolve().parent.parent
    / "references"
    / "specs-licensing-compliance.md"
)

# (url, acceptable marker strings). Any marker counts as present.
LIVE_SOURCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("https://support.google.com/youtube/answer/6013276", ("2026", "24 September")),
    ("https://www.remotion.dev/pricing", ("$0.01",)),
)

# Each value is (needle_regex, human description). Needles are compiled with
# re.search; literal facts are passed through re.escape to keep the dots/dashes
# honest. Tests add/remove drift by mutating these needles, not a data file.
BASELINE: dict[str, tuple[str, str]] = {
    "baseline_date": (re.escape(BASELINE_DATE), "baseline verification date"),
    "youtube_shorts_cap": (re.escape("3 min"), "YouTube Shorts 3 min cap"),
    "facebook_reels_cap": (re.escape("90 s"), "Facebook Reels 90 s cap"),
    "tiktok_cap": (re.escape("10 min in-app"), "TikTok 10 min in-app cap"),
    "safe_organic_rect": (
        re.escape("x=60..930, y=180..1540"),
        "9:16 organic safe rectangle",
    ),
    "safe_strict_rect": (
        re.escape("x=65..888, y=288..1248"),
        "9:16 strict/ad-safe rectangle",
    ),
    "audio_bitrate": (re.escape("192 kbps"), "audio bitrate 192 kbps"),
    "audio_lufs": (r"[-−]14 LUFS", "integrated loudness -14 LUFS"),
    "audio_true_peak": (r"[-−]1\.0 dBTP", "true peak ceiling -1.0 dBTP"),
    "shorts_content_id_date": (
        re.escape("2026-09-24"),
        "Shorts Content ID policy date",
    ),
    "originality_date": (re.escape("2026-10"), "Shorts originality policy month"),
    "license_kokoro": (re.escape("Kokoro-82M"), "Kokoro-82M local TTS"),
    "license_apache": (re.escape("Apache-2.0"), "Apache-2.0 license entry"),
    "license_xtts": (r"XTTS-v2.*non-commercial", "XTTS-v2 flagged non-commercial"),
    "license_remotion": (re.escape("Remotion"), "Remotion renderer"),
    "license_remotion_price": (
        r"\$0\.01(?:\s+per\s+|\s*/\s*)render",
        "Remotion $0.01 per render price",
    ),
}


def check_doc(text: str) -> dict[str, Any]:
    """Compare the Markdown reference against the embedded baseline.

    Returns a JSON-serialisable report with the full public shape (offline and
    live default to no network). No network or filesystem access happens here.
    """
    checks: list[dict[str, Any]] = []
    drift: list[str] = []
    for name, (needle, description) in BASELINE.items():
        found = re.search(needle, text) is not None
        detail = (
            f"OK: {description}"
            if found
            else f"MISSING: {description} (expected {needle!r})"
        )
        checks.append({"check": name, "ok": found, "detail": detail})
        if not found:
            drift.append(f"{name}: {detail}")
    return {
        "ok": not drift,
        "offline": True,
        "baseline_date": BASELINE_DATE,
        "doc": str(DEFAULT_DOC),
        "checks": checks,
        "drift": drift,
        "live": [],
    }


def fetch_live(timeout: float) -> list[dict[str, Any]]:
    """Probe authoritative URLs for expected markers; failures are advisory.

    Every exception is swallowed and recorded, so an offline machine (or a
    changed website) can never crash the check or turn it fatal.
    """
    results: list[dict[str, Any]] = []
    for url, markers in LIVE_SOURCES:
        ok = False
        marker_found = False
        detail = ""
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                payload = response.read()
            body = payload.decode("utf-8", errors="replace")
            ok = True
            marker_found = any(marker in body for marker in markers)
            detail = (
                f"fetched {len(payload)} bytes; "
                f"marker {'present' if marker_found else 'absent'}"
            )
        except Exception as exc:  # noqa: BLE001 - advisory probe is never fatal
            detail = f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "url": url,
                "ok": ok,
                "marker_found": marker_found,
                "detail": detail,
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="perform the local baseline check (the default action)",
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=DEFAULT_DOC,
        help="spec reference Markdown to audit",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="also probe authoritative URLs (advisory, never fatal)",
    )
    parser.add_argument("--out", type=Path, help="write the JSON report here")
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="per-request timeout (seconds)"
    )
    args = parser.parse_args(argv)

    try:
        text = args.doc.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"spec_refresh: cannot read doc {args.doc}: {exc}", file=sys.stderr)
        return 2

    report = check_doc(text)
    report["live"] = fetch_live(args.timeout) if args.fetch else []
    report["offline"] = not any(item["ok"] for item in report["live"])
    report["doc"] = str(args.doc)
    full: dict[str, Any] = report
    offline = bool(report["offline"])
    payload = json.dumps(full, indent=2, ensure_ascii=False)
    print(payload)

    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            print(
                f"spec_refresh: cannot write report {args.out}: {exc}", file=sys.stderr
            )
            return 2

    if full["ok"]:
        suffix = " (offline)" if offline else ""
        print(f"spec_refresh: PASS — baseline intact{suffix}", file=sys.stderr)
        return 0
    print(f"spec_refresh: FAIL — drift: {', '.join(full['drift'])}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
