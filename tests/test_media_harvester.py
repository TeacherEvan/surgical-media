"""media_harvester unit tests — fully offline (HTTP + search layers stubbed)."""

from __future__ import annotations

import builtins
import io
import json
from pathlib import Path
from typing import Any

import fetch_assets
import media_harvester
import pytest
from PIL import Image, ImageDraw


def _png_bytes(
    size: tuple[int, int] = (1600, 1200), color: tuple[int, int, int] = (12, 16, 24)
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _item(
    title: str = "Ada Lovelace",
    url: str = "https://img.example/ada.png",
    license_code: str = "by",
    source: str = "commons",
) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "width": 1600,
        "height": 1200,
        "license": license_code,
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "creator": "Jane Photographer",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Ada",
        "source": source,
    }


@pytest.fixture(autouse=True)
def _no_face_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic crops: cv2 is optional and absent in the test venv anyway."""
    monkeypatch.setattr(media_harvester, "_detect_face_normalized", lambda image: None)


def _stub_network(
    monkeypatch: pytest.MonkeyPatch,
    results: list[dict[str, Any]],
    png: bytes | None = None,
) -> list[str]:
    """Stub search + image download; return the list of requested image URLs."""
    requested: list[str] = []
    image_bytes = png if png is not None else _png_bytes()

    monkeypatch.setattr(
        media_harvester, "search_photos", lambda *a, **k: [dict(r) for r in results]
    )

    def fake_http_get(url: str, timeout: float) -> bytes:
        requested.append(url)
        return image_bytes

    monkeypatch.setattr(fetch_assets, "_http_get", fake_http_get)
    return requested


# ---------------------------------------------------------------------------
# Crop maths
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("aspect", "expected"),
    [
        ("9:16", (1080, 1920)),
        ("16:9", (1920, 1080)),
        ("1:1", (1080, 1080)),
        ("4:5", (1080, 1350)),
    ],
)
def test_aspect_crop_math_all_ratios(aspect: str, expected: tuple[int, int]) -> None:
    img = Image.new("RGB", (1600, 1200), (20, 40, 60))
    cropped, info = media_harvester.face_center(img, (0.5, 0.5), aspect, 1080)
    assert cropped.size == expected
    assert info["output_size"] == expected
    assert info["detected_face"] is False
    assert info["quality_warning"] is None
    x0, y0, x1, y1 = info["crop_box"]
    assert 0 <= x0 < x1 <= 1600
    assert 0 <= y0 < y1 <= 1200


def test_crop_box_clamps_near_edges() -> None:
    img = Image.new("RGB", (1600, 800), (20, 40, 60))
    cropped, info = media_harvester.face_center(img, (0.95, 0.95), "9:16", 1080)
    x0, y0, x1, y1 = info["crop_box"]
    assert x1 == 1600  # right-clamped
    assert y0 == 0  # top-clamped
    assert (x1 - x0) < (y1 - y0)  # tall crop from a wide source
    assert cropped.size == (1080, 1920)


def test_detected_face_overrides_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media_harvester, "_detect_face_normalized", lambda image: (0.2, 0.25)
    )
    img = Image.new("RGB", (1000, 1000), (20, 40, 60))
    _cropped, info = media_harvester.face_center(img, (0.9, 0.9), "1:1", 500)
    assert info["detected_face"] is True
    assert info["focus"] == (0.2, 0.25)
    assert info["requested_focus"] == (0.9, 0.9)


def test_cv2_missing_falls_back_to_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "cv2":
            raise ImportError("cv2 deliberately unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    img = Image.new("RGB", (800, 800), (20, 40, 60))
    _cropped, info = media_harvester.face_center(img, (0.33, 0.66), "4:5", 400)
    assert info["detected_face"] is False
    assert info["focus"] == (0.33, 0.66)
    assert info["anchor_source"] == "manual"


def test_skin_tone_centroid_replaces_blind_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(media_harvester, "_detect_face_normalized", lambda image: None)
    img = Image.new("RGB", (800, 800), (40, 40, 40))
    # Skin-tone patch off-centre (x 0.2..0.3, y 0.6..0.75).
    ImageDraw.Draw(img).rectangle((160, 480, 240, 600), fill=(210, 170, 140))
    center = media_harvester._skin_tone_center(img)
    assert center is not None
    assert 0.18 <= center[0] <= 0.32
    assert 0.58 <= center[1] <= 0.77

    _cropped, info = media_harvester.face_center(img, (0.5, 0.35), "1:1", 400)
    assert info["detected_face"] is False
    assert info["anchor_source"] == "skin_tone"
    assert abs(info["focus"][0] - center[0]) < 0.02
    assert abs(info["focus"][1] - center[1]) < 0.02


def test_skin_tone_detector_rejects_uniform_non_skin() -> None:
    img = Image.new("RGB", (800, 800), (20, 40, 60))
    assert media_harvester._skin_tone_center(img) is None


def test_quality_warning_for_undersized_source() -> None:
    img = Image.new("RGB", (400, 300), (20, 40, 60))
    _cropped, info = media_harvester.face_center(img, (0.5, 0.5), "9:16", 1080)
    assert info["quality_warning"] and "upscaled" in info["quality_warning"]


# ---------------------------------------------------------------------------
# Badge
# ---------------------------------------------------------------------------
def _count_light(image: Image.Image, box: tuple[int, int, int, int]) -> int:
    x0, y0, x1, y1 = box
    pixels = image.load()
    return sum(
        1
        for y in range(y0, y1)
        for x in range(x0, x1)
        if all(channel > 150 for channel in pixels[x, y][:3])
    )


def test_badge_text_inside_safe_rect_pixel_presence() -> None:
    img = Image.new("RGB", (1080, 1920), (8, 10, 14))
    media_harvester.draw_credit_badge(
        img, "Photo: Jane Photographer / commons", "9:16", "organic"
    )
    # Bottom edge of the organic safe rect is y=1540; the badge must sit above it.
    assert _count_light(img, (60, 1480, 930, 1540)) > 0
    # Below the safe rect (Shorts caption bar) must remain untouched.
    assert _count_light(img, (0, 1600, 1080, 1920)) == 0
    assert _count_light(img, (0, 0, 1080, 180)) == 0


@pytest.mark.parametrize(
    ("aspect", "safe_mode"),
    [
        ("9:16", "organic"),
        ("9:16", "strict"),
        ("16:9", "organic"),
        ("1:1", "strict"),
        ("4:5", "organic"),
    ],
)
def test_badge_fits_all_aspects_and_modes(aspect: str, safe_mode: str) -> None:
    width, height = media_harvester._output_size(aspect, 1080)
    img = Image.new("RGB", (width, height), (8, 10, 14))
    media_harvester.draw_credit_badge(img, "Photo: Jane / commons", aspect, safe_mode)
    x0, y0, x1, y1 = media_harvester._safe_rect(width, height, aspect, safe_mode)
    assert 0 <= x0 < x1 <= width
    assert 0 <= y0 < y1 <= height
    assert _count_light(img, (x0, max(y0, y1 - 90), x1, y1)) > 0
    if y1 < height - 8:
        assert _count_light(img, (0, y1 + 8, width, height)) == 0


# ---------------------------------------------------------------------------
# Licensing / validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("by", True),
        ("by-sa", True),
        ("cc0", True),
        ("pdm", True),
        ("by-nc", False),
        ("by-nc-sa", False),
        ("by-nd", False),
        ("by-nc-nd", False),
        ("pd", False),
        ("all-rights-reserved", False),
    ],
)
def test_is_remixable(code: str, expected: bool) -> None:
    assert media_harvester.is_remixable(_item(license_code=code)) is expected


def test_non_https_url_is_not_remixable() -> None:
    assert (
        media_harvester.is_remixable(_item(url="http://img.example/ada.png")) is False
    )


def test_parse_people_and_focus_validation() -> None:
    assert media_harvester.parse_people(
        ["Ada Lovelace, Grace Hopper", "Alan Turing"]
    ) == [
        "Ada Lovelace",
        "Grace Hopper",
        "Alan Turing",
    ]
    with pytest.raises(ValueError):
        media_harvester.parse_people(["penguin"])
    with pytest.raises(ValueError):
        media_harvester.parse_people(["   "])
    assert media_harvester.parse_focus("0.5,0.35") == (0.5, 0.35)
    assert media_harvester.parse_focus("2,-1") == (1.0, 0.0)
    with pytest.raises(ValueError):
        media_harvester.parse_focus("0.5")


# ---------------------------------------------------------------------------
# Harvest pipeline
# ---------------------------------------------------------------------------
def _harvest_kwargs(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query": "Ada Lovelace",
        "people": ["Ada Lovelace"],
        "out_dir": tmp_path,
        "count": 2,
        "aspect": "9:16",
        "safe_mode": "organic",
        "focus": (0.5, 0.35),
        "min_width": 1080,
        "timeout": 3.0,
        "source": "all",
    }
    kwargs.update(overrides)
    return kwargs


def test_harvest_rejects_non_remixable_licenses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = _stub_network(
        monkeypatch,
        [
            _item("NC Portrait", "https://img.example/nc.png", "by-nc"),
            _item("ND Portrait", "https://img.example/nd.png", "by-nd"),
            _item("Ada Lovelace", "https://img.example/ada.png", "by"),
        ],
    )
    rc = media_harvester.harvest(**_harvest_kwargs(tmp_path, count=3))
    assert rc == 0
    assert requested == ["https://img.example/ada.png"]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 1
    assert manifest["assets"][0]["license"] == "by"


def test_harvest_manifest_and_credits_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_network(monkeypatch, [_item()])
    rc = media_harvester.harvest(**_harvest_kwargs(tmp_path, count=1))
    assert rc == 0

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert {"query", "queries", "sources", "retrieved", "count", "assets"} <= set(
        manifest
    )
    asset = manifest["assets"][0]
    assert {
        "file",
        "title",
        "creator",
        "license",
        "license_version",
        "license_url",
        "source_url",
        "url",
        "width",
        "height",
        "source",
        "attribution",
    } <= set(asset)
    assert asset["file"].startswith("portraits/01_")
    assert (tmp_path / asset["file"]).is_file()

    credits = json.loads((tmp_path / "credits.json").read_text(encoding="utf-8"))
    assert {
        "generated_at",
        "query",
        "aspect",
        "safe_mode",
        "assets",
        "disclosures",
        "originality_note",
    } <= set(credits)
    c_asset = credits["assets"][0]
    assert c_asset["badge_text"] == "Photo: Jane Photographer / commons"
    assert c_asset["detected_face"] is False
    assert c_asset["focus"] == [0.5, 0.35]
    assert c_asset["attribution"] == asset["attribution"]
    assert credits["disclosures"] and credits["originality_note"]

    md = (tmp_path / "CREDITS.md").read_text(encoding="utf-8")
    for section in ("Images", "News sources", "AI disclosure", "Originality note"):
        assert f"## {section}" in md
    assert asset["attribution"] in md
    assert asset["source_url"] in md
    assert "by" in md


def test_manifest_merges_across_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_network(monkeypatch, [_item("Ada Lovelace", "https://img.example/ada.png")])
    assert media_harvester.harvest(**_harvest_kwargs(tmp_path, count=1)) == 0
    _stub_network(monkeypatch, [_item("Grace Hopper", "https://img.example/grace.png")])
    assert (
        media_harvester.harvest(
            **_harvest_kwargs(tmp_path, query="Grace Hopper", count=1)
        )
        == 0
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 2
    assert len(manifest["assets"]) == 2
    assert len({a["file"] for a in manifest["assets"]}) == 2
    assert set(manifest["queries"]) == {"Ada Lovelace", "Grace Hopper"}


def test_tiny_and_http_images_are_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = _stub_network(
        monkeypatch,
        [
            _item("Tiny", "https://img.example/tiny.png"),
            _item("Insecure", "http://img.example/insecure.png"),
        ],
        png=_png_bytes((100, 100)),
    )
    rc = media_harvester.harvest(**_harvest_kwargs(tmp_path, count=2))
    assert rc == 2
    assert requested == ["https://img.example/tiny.png"]
    assert list((tmp_path / "portraits").glob("*")) == []


def test_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_network(monkeypatch, [_item()])
    out = tmp_path / "planned"
    rc = media_harvester.harvest(**_harvest_kwargs(out, count=1, dry_run=True))
    assert rc == 0
    assert not out.exists()
    captured = capsys.readouterr().out
    payload = json.loads(captured[captured.index("{") :])
    assert payload["dry_run"] is True
    assert payload["count"] == 1
    assert payload["actions"][0]["file"].startswith("portraits/01_")


def test_no_network_guarantee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("real network access attempted")

    monkeypatch.setattr(fetch_assets.urllib.request, "urlopen", no_network)
    _stub_network(monkeypatch, [_item()])
    assert media_harvester.harvest(**_harvest_kwargs(tmp_path, count=1)) == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_network(monkeypatch, [_item()])
    rc = media_harvester.main(
        [
            "--query",
            "Ada Lovelace",
            "--people",
            "Ada Lovelace",
            "--out-dir",
            str(tmp_path),
            "--count",
            "1",
            "--aspect",
            "9:16",
            "--safe-mode",
            "organic",
            "--focus",
            "0.5,0.35",
            "--source",
            "all",
        ]
    )
    assert rc == 0
    assert (tmp_path / "manifest.json").is_file()


def test_cli_exit_two_for_invalid_people(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_assets.urllib.request, "urlopen", lambda *a, **k: None)
    rc = media_harvester.main(
        [
            "--query",
            "penguins",
            "--people",
            "penguin",
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert rc == 2
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "portraits").exists()


def test_cli_exit_two_for_missing_required_args() -> None:
    with pytest.raises(SystemExit) as exc:
        media_harvester.main([])
    assert exc.value.code == 2
