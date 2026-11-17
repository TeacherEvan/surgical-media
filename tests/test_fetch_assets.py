"""fetch_assets unit tests — fully offline (HTTP layer stubbed)."""

import io
import json

import fetch_assets
import pytest
from PIL import Image


def _png_bytes(color=(10, 200, 10)):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="PNG")
    return buf.getvalue()


class TestLicenseKey:
    @pytest.mark.parametrize(
        "code", ["by", "by-sa", "cc0", "pdm", "BY", "By-SA", "by 2.0", "by-sa 4.0"]
    )
    def test_allowlist(self, code):
        assert fetch_assets.license_key(code) in fetch_assets.ALLOWED_LICENSES

    @pytest.mark.parametrize(
        "code",
        ["by-nc", "by-nd", "by-nc-nd", "by-nc-sa", "unknown", "", None, "fair-use"],
    )
    def test_rejected(self, code):
        assert fetch_assets.license_key(code) is None


def test_openverse_url_encodes_query_and_flags():
    url = fetch_assets.openverse_url("emperor penguin colony", page_size=12)
    assert url.startswith("https://api.openverse.org/v1/images/?")
    assert "q=emperor+penguin+colony" in url
    assert "page_size=12" in url
    assert "mature=false" in url


def test_filter_results_allowlist_width_dedupe_order():
    results = [
        {"title": "a", "url": "https://x/1.jpg", "width": 500, "license": "by"},
        {
            "title": "b",
            "url": "https://x/2.jpg",
            "width": 2000,
            "license": "by-nc",
        },  # rejected
        {"title": "c", "url": "https://x/3.jpg", "width": 1200, "license": "by-sa"},
        {
            "title": "d",
            "url": "https://x/3.jpg",
            "width": 1200,
            "license": "by",
        },  # dup url
        {"title": "e", "url": "https://x/4.jpg", "width": 900, "license": "cc0"},
        {"title": "f", "url": "https://x/5.jpg", "width": 1500, "license": "pdm"},
        {
            "title": "g",
            "url": "https://x/6.jpg",
            "width": 800,
            "license": "by-nd",
        },  # rejected
    ]
    kept = fetch_assets.filter_results(results, min_width=800)
    assert [r["title"] for r in kept] == [
        "f",
        "c",
        "e",
    ]  # width desc, allowlisted, deduped


def test_format_attribution_contents():
    item = {
        "creator": "Jane Photographer",
        "title": "Colony at Halley Bay",
        "license": "by-sa",
        "license_version": "4.0",
        "foreign_landing_url": "https://commons.example/colony",
    }
    attr = fetch_assets.format_attribution(item)
    assert "Jane Photographer" in attr
    assert "CC BY-SA 4.0" in attr
    assert "commons.example/colony" in attr


def test_format_attribution_unknown_creator():
    attr = fetch_assets.format_attribution(
        {"title": "X", "license": "cc0", "url": "https://x"}
    )
    assert "Unknown author" in attr


def test_build_manifest_structure():
    items = [
        {
            "title": "t",
            "creator": "c",
            "license": "by",
            "license_version": "2.0",
            "license_url": "https://lic",
            "foreign_landing_url": "https://src",
            "url": "https://direct",
            "width": 1024,
            "height": 768,
            "_saved_as": "01_t.jpg",
        }
    ]
    manifest = fetch_assets.build_manifest("emperor penguin", items)
    assert manifest["query"] == "emperor penguin"
    assert manifest["count"] == 1
    asset = manifest["assets"][0]
    assert asset["file"] == "01_t.jpg"
    assert asset["license"] == "by"
    assert "c — t" in asset["attribution"]
    assert json.loads(json.dumps(manifest))["count"] == 1


def test_decode_to_ext_roundtrip_and_garbage():
    img, ext = fetch_assets._decode_to_ext(_png_bytes())
    assert img is not None and ext == ".png"
    img, ext = fetch_assets._decode_to_ext(b"this is not an image")
    assert img is None and ext == ""


def test_download_assets_offline(tmp_path, monkeypatch):
    """Search returns 3 candidates; one is undecodable; manifest is written."""
    search_payload = {
        "results": [
            {
                "title": "Good Shot",
                "url": "https://img/good.jpg",
                "width": 2000,
                "height": 1500,
                "license": "by",
                "creator": "Photographer",
                "license_version": "2.0",
                "license_url": "https://lic",
                "foreign_landing_url": "https://src/good",
            },
            {
                "title": "Broken",
                "url": "https://img/broken.jpg",
                "width": 1500,
                "height": 1000,
                "license": "by-sa",
                "creator": "Someone",
                "license_version": "3.0",
                "license_url": "https://lic",
                "foreign_landing_url": "https://src/broken",
            },
            {
                "title": "Second Good",
                "url": "https://img/second.jpg",
                "width": 1200,
                "height": 900,
                "license": "cc0",
                "creator": "Anon",
                "license_version": "",
                "license_url": "",
                "foreign_landing_url": "https://src/second",
            },
        ]
    }

    def fake_http_get(url, timeout):
        if "api.openverse.org" in url:
            return json.dumps(search_payload).encode("utf-8")
        if "broken" in url:
            return b"not an image at all"
        return _png_bytes()

    monkeypatch.setattr(fetch_assets, "_http_get", fake_http_get)
    rc = fetch_assets.download_assets(
        query="emperor penguin",
        out_dir=tmp_path,
        count=2,
        min_width=800,
        timeout=5.0,
        dry_run=False,
    )
    assert rc == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 2
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".png")
    assert len(files) == 2
    for asset in manifest["assets"]:
        assert asset["attribution"]
        assert (tmp_path / asset["file"]).is_file()


def test_download_assets_merges_manifest_across_queries(tmp_path, monkeypatch):
    """A second query into the same dir must not clobber prior assets."""

    def payload_for(query):
        return {
            "results": [
                {
                    "title": query,
                    "url": f"https://img/{query.replace(' ', '_')}.jpg",
                    "width": 2000,
                    "height": 1500,
                    "license": "by",
                    "creator": "Photographer",
                    "license_version": "2.0",
                    "license_url": "https://lic",
                    "foreign_landing_url": f"https://src/{query}",
                },
            ]
        }

    def fake_http_get(url, timeout):
        if "api.openverse.org" in url:
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(url).query)["q"][0]
            return json.dumps(payload_for(q)).encode("utf-8")
        return _png_bytes()

    monkeypatch.setattr(fetch_assets, "_http_get", fake_http_get)
    for q in ("emperor penguin", "emperor penguin chick"):
        rc = fetch_assets.download_assets(
            q, tmp_path, count=1, min_width=800, timeout=5.0, dry_run=False
        )
        assert rc == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 2
    assert sorted(manifest["queries"]) == ["emperor penguin", "emperor penguin chick"]
    files = {a["file"] for a in manifest["assets"]}
    assert len(files) == 2
    for asset in manifest["assets"]:
        assert (tmp_path / asset["file"]).is_file()
