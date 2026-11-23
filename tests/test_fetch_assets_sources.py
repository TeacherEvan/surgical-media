"""Multi-source fetcher tests — fully offline (HTTP layer stubbed)."""

import io
import json
from typing import ClassVar

import fetch_assets
import pytest
from PIL import Image


def _png_bytes(color=(10, 200, 10)):
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), color).save(buf, format="PNG")
    return buf.getvalue()


# ---------- license parsing ----------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CC BY 4.0", ("by", "4.0")),
        ("CC BY 2.0", ("by", "2.0")),
        ("CC BY-SA 4.0", ("by-sa", "4.0")),
        ("CC BY-SA 3.0", ("by-sa", "3.0")),
        ("CC0", ("cc0", "1.0")),
        ("CC0 1.0", ("cc0", "1.0")),
        ("Public domain", ("pdm", "")),
        ("CC BY-NC 4.0", (None, "")),
        ("CC BY-NC-SA 3.0", (None, "")),
        ("CC BY-ND 2.0", (None, "")),
        ("GNU Free Documentation License", (None, "")),
        ("", (None, "")),
        (None, (None, "")),
    ],
)
def test_parse_commons_license(text, expected):
    assert fetch_assets.parse_commons_license(text) == expected


def test_strip_html():
    assert (
        fetch_assets.strip_html("<a href='x'>Jane</a> Photographer")
        == "Jane Photographer"
    )
    assert fetch_assets.strip_html("plain &amp; simple") == "plain & simple"
    assert fetch_assets.strip_html("") == ""


# ---------- commons search ----------

COMMONS_PAYLOAD = {
    "query": {
        "pages": {
            "1": {
                "title": "File:Emperor jumping.jpg",
                "imageinfo": [
                    {
                        "thumburl": "https://upload.wikimedia.org/thumb/jump.jpg",
                        "url": "https://upload.wikimedia.org/jump.jpg",
                        "thumbwidth": 2048,
                        "thumbheight": 1362,
                        "width": 3989,
                        "height": 2652,
                        "mime": "image/jpeg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Emperor_jumping.jpg",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY 2.0"},
                            "LicenseUrl": {
                                "value": "https://creativecommons.org/licenses/by/2.0"
                            },
                            "Artist": {
                                "value": "<a href='https://x'>Christopher Michel</a>"
                            },
                        },
                    }
                ],
            },
            "2": {
                "title": "File:Diagram.svg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/diagram.svg",
                        "width": 800,
                        "height": 600,
                        "mime": "image/svg+xml",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Diagram.svg",
                        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                    }
                ],
            },
            "3": {
                "title": "File:NonCommercial snap.jpg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/nc.jpg",
                        "width": 3000,
                        "height": 2000,
                        "mime": "image/jpeg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:NC.jpg",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY-NC-SA 4.0"}
                        },
                    }
                ],
            },
        }
    }
}


def test_commons_search_normalizes_and_filters_svg(monkeypatch):
    monkeypatch.setattr(
        fetch_assets,
        "_http_get",
        lambda url, timeout: json.dumps(COMMONS_PAYLOAD).encode(),
    )
    items = fetch_assets.search_commons("emperor penguin", 10, 5.0)
    assert len(items) == 2  # svg dropped
    jump = items[0]
    assert jump["url"] == "https://upload.wikimedia.org/thumb/jump.jpg"
    assert jump["width"] == 2048
    assert jump["license"], "license must parse"
    assert jump["creator"] == "Christopher Michel"  # HTML stripped
    assert jump["source"] == "commons"
    assert jump["license_url"].endswith("by/2.0")


def test_commons_license_rejected_by_filter_results(monkeypatch):
    monkeypatch.setattr(
        fetch_assets,
        "_http_get",
        lambda url, timeout: json.dumps(COMMONS_PAYLOAD).encode(),
    )
    items = fetch_assets.search_commons("x", 10, 5.0)
    kept = fetch_assets.filter_results(items, min_width=800)
    assert all(i["license"] != "nc" for i in kept)
    assert len(kept) == 1  # only the CC BY plate survives


# ---------- inaturalist search ----------

INAT_PAYLOAD = {
    "results": [
        {
            "id": 111,
            "license_code": "cc-by",
            "user": {"login": "icewatcher"},
            "taxon": {
                "name": "Aptenodytes forsteri",
                "preferred_common_name": "Emperor Penguin",
            },
            "photos": [
                {
                    "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/10/square.jpg"
                }
            ],
        },
        {
            "id": 222,
            "license_code": "cc-by-nc",
            "user": {"login": "pirate"},
            "taxon": {"name": "Aptenodytes forsteri"},
            "photos": [
                {
                    "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/20/square.jpg"
                }
            ],
        },
    ]
}


def test_inaturalist_search_normalizes(monkeypatch):
    monkeypatch.setattr(
        fetch_assets,
        "_http_get",
        lambda url, timeout: json.dumps(INAT_PAYLOAD).encode(),
    )
    items = fetch_assets.search_inaturalist("emperor penguin", 10, 5.0)
    assert len(items) == 1  # cc-by-nc skipped
    it = items[0]
    assert it["url"].endswith("/photos/10/original.jpg")  # square upscaled to original
    assert it["license"] == "by"
    assert it["source"] == "inaturalist"
    assert "observations/111" in it["foreign_landing_url"]
    assert "Emperor Penguin" in it["title"]


def test_filter_results_keeps_unknown_width():
    items = [{"title": "t", "url": "https://x/1.jpg", "width": 0, "license": "by"}]
    assert len(fetch_assets.filter_results(items, min_width=800)) == 1


def test_search_subject_merges_sources_and_dedupes(monkeypatch):
    payloads = {
        "api.openverse.org": {
            "results": [
                {
                    "title": "ov",
                    "url": "https://dup/x.jpg",
                    "width": 2000,
                    "license": "by",
                    "source": "openverse",
                }
            ]
        },
        "commons.wikimedia.org": {
            "query": {
                "pages": {
                    "1": {
                        "title": "File:Dup.jpg",
                        "imageinfo": [
                            {
                                "url": "https://dup/x.jpg",
                                "width": 2048,
                                "mime": "image/jpeg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY 4.0"}
                                },
                            }
                        ],
                    }
                }
            }
        },
        "api.inaturalist.org": {"results": []},
    }

    def fake_http_get(url, timeout):
        for host, payload in payloads.items():
            if host in url:
                return json.dumps(payload).encode()
        raise AssertionError(url)

    monkeypatch.setattr(fetch_assets, "_http_get", fake_http_get)
    items = fetch_assets.search_subject(
        "emperor penguin", list(fetch_assets.SOURCES), 6, 5.0
    )
    urls = [i["url"] for i in items]
    assert urls == ["https://dup/x.jpg"]  # same plate from two sources → kept once


def test_download_assets_all_records_sources(tmp_path, monkeypatch):
    search_payload = {
        "api.openverse.org": {
            "results": [
                {
                    "title": "OV Plate — emperor penguin",
                    "url": "https://img/ov.jpg",
                    "width": 2000,
                    "height": 1500,
                    "license": "by",
                    "creator": "O",
                }
            ]
        },
        "commons.wikimedia.org": {
            "query": {
                "pages": {
                    "1": {
                        "title": "File:Commons Plate.jpg",
                        "imageinfo": [
                            {
                                "url": "https://img/commons.png",
                                "thumbwidth": 2048,
                                "thumbheight": 1152,
                                "mime": "image/png",
                                "descriptionurl": "https://commons.x/commons",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "Artist": {"value": "C"},
                                },
                            }
                        ],
                    }
                }
            }
        },
        "api.inaturalist.org": {"results": []},
    }

    def fake_http_get(url, timeout):
        for host, payload in search_payload.items():
            if host in url:
                return json.dumps(payload).encode()
        return _png_bytes()

    monkeypatch.setattr(fetch_assets, "_http_get", fake_http_get)
    rc = fetch_assets.download_assets(
        "emperor penguin", tmp_path, count=2, min_width=800, timeout=5.0, dry_run=False
    )
    assert rc == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 2
    assert set(manifest["sources"]) == {"openverse", "commons"}
    assert all(a["source"] in {"openverse", "commons"} for a in manifest["assets"])


def test_http_get_rejects_non_https(monkeypatch):
    import fetch_assets

    class R:
        pass

    monkeypatch.setattr(
        fetch_assets.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("urlopen must not be reached for non-https URLs"),
    )
    with pytest.raises(fetch_assets.FetchError):
        fetch_assets._http_get("http://example.com/x.jpg", 1.0)


def test_http_get_rejects_oversized_content_length(monkeypatch):
    import fetch_assets

    class FakeResp:
        def __init__(self):
            self.headers = {"Content-Length": str(60 * 1024 * 1024)}

        def geturl(self):
            return "https://example.com/big.jpg"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        fetch_assets.urllib.request, "urlopen", lambda *a, **k: FakeResp()
    )
    with pytest.raises(fetch_assets.FetchError):
        fetch_assets._http_get("https://example.com/big.jpg", 1.0)


def test_http_get_rejects_redirect_to_http(monkeypatch):
    import fetch_assets

    class FakeResp:
        headers: ClassVar[dict] = {}

        def geturl(self):
            return "http://169.254.169.254/latest/meta-data"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        fetch_assets.urllib.request, "urlopen", lambda *a, **k: FakeResp()
    )
    with pytest.raises(fetch_assets.FetchError):
        fetch_assets._http_get("https://example.com/redirect", 1.0)
