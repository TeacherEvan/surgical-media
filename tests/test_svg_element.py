"""Tests for the SVG vector art & animated line-drawing element (`elements/svg.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import storyboard
from canvas import SupersampledCanvas, layout_zones
from elements import RENDERERS, ElementContext, render_element
from elements.svg import _find_chromium_svg_runner, parse_svg_path

SAMPLE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
  <g transform="translate(10, 10)">
    <rect x="10" y="10" width="160" height="160" rx="18" fill="#0F172A" stroke="#38BDF8" stroke-width="4" />
    <circle cx="90" cy="90" r="46" fill="none" stroke="#FACC15" stroke-width="3" />
    <path d="M 55 95 L 80 120 Q 105 90 130 65 C 135 60 140 62 142 66" fill="none" stroke="#34D399" stroke-width="5" />
    <path d="M 40 40 A 20 20 0 0 1 80 40 Z" fill="#A78BFA" />
    <text x="90" y="165" font-size="14" text-anchor="middle" fill="#FFFFFF">SVG OK</text>
  </g>
</svg>
"""


def _ctx(t: float = 0.75, base_dir: str | None = None) -> ElementContext:
    return ElementContext(
        width=320,
        height=180,
        t=t,
        scene_time=t,
        local_time=t,
        words=[],
        seed=7,
        trauma=0.0,
        zones=layout_zones(320, 180),
        base_dir=base_dir,
    )


def _nonzero_pixels(img: Image.Image) -> int:
    return sum(1 for px in img.get_flattened_data() if px != (0, 0, 0))


def test_svg_registered_in_renderers_and_known_elements():
    assert "svg" in RENDERERS
    assert "svg" in storyboard.KNOWN_ELEMENTS


def test_parse_svg_path_supports_all_core_commands():
    subpaths = parse_svg_path(
        "M 0 0 L 10 0 H 20 V 10 C 20 20 10 20 10 10 S 0 0 0 10 Q 5 15 10 15 T 20 15 A 5 5 0 0 1 25 20 Z"
    )
    assert len(subpaths) == 1
    pts, closed = subpaths[0]
    assert closed is True
    assert len(pts) > 30


def test_svg_inline_renders_visible_pixels():
    cv = SupersampledCanvas(320, 180, scale=2, background="#000000")
    render_element(
        cv,
        {
            "type": "svg",
            "svg": SAMPLE_SVG,
            "box": [60, 10, 260, 170],
            "render_mode": "vector",
        },
        _ctx(t=1.0),
    )
    frame = cv.final()
    assert frame.mode == "RGB"
    assert _nonzero_pixels(frame) > 500


def test_svg_draw_reveal_progresses_with_time():
    cv_early = SupersampledCanvas(320, 180, scale=1, background="#000000")
    render_element(
        cv_early,
        {
            "type": "svg",
            "svg": SAMPLE_SVG,
            "box": [60, 10, 260, 170],
            "reveal": "draw",
            "glow": True,
        },
        _ctx(t=0.12),
    )
    cv_late = SupersampledCanvas(320, 180, scale=1, background="#000000")
    render_element(
        cv_late,
        {
            "type": "svg",
            "svg": SAMPLE_SVG,
            "box": [60, 10, 260, 170],
            "reveal": "draw",
            "glow": True,
        },
        _ctx(t=0.95),
    )
    assert _nonzero_pixels(cv_late.final()) > _nonzero_pixels(cv_early.final())


def test_svg_pop_fade_rotation_and_tint():
    for reveal in ("pop", "fade"):
        cv = SupersampledCanvas(320, 180, scale=1, background="#000000")
        render_element(
            cv,
            {
                "type": "svg",
                "svg": SAMPLE_SVG,
                "box": [60, 10, 260, 170],
                "reveal": reveal,
                "rotation_deg": -15.0,
                "rotation_end_deg": 15.0,
                "scale_start": 0.9,
                "scale_end": 1.1,
                "tint": "#38BDF8",
            },
            _ctx(t=0.6),
        )
        assert _nonzero_pixels(cv.final()) > 200


def test_svg_external_file_relative_to_base_dir(tmp_path):
    svg_file = tmp_path / "badge.svg"
    svg_file.write_text(SAMPLE_SVG, encoding="utf-8")
    cv = SupersampledCanvas(320, 180, scale=1, background="#000000")
    render_element(
        cv,
        {
            "type": "svg",
            "src": "badge.svg",
            "box": [60, 10, 260, 170],
            "render_mode": "vector",
        },
        _ctx(t=1.0, base_dir=str(tmp_path)),
    )
    assert _nonzero_pixels(cv.final()) > 500


def test_svg_20_chromium_rasterizes_gradients_and_filters():
    if _find_chromium_svg_runner() is None:
        pytest.skip("Node/Chromium SVG 2.0 rasterizer unavailable")
    svg_20 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 90">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#0EA5E9"/>
          <stop offset="100%" stop-color="#6366F1"/>
        </linearGradient>
        <filter id="f"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#38BDF8"/></filter>
      </defs>
      <rect x="8" y="8" width="224" height="74" rx="14" fill="url(#g)" filter="url(#f)"/>
      <path d="M 45 25 A 20 20 0 1 0 45.1 25 Z M 45 35 A 10 10 0 1 1 44.9 35 Z" fill="#FACC15" fill-rule="evenodd"/>
    </svg>"""
    cv = SupersampledCanvas(320, 180, scale=1, background="#000000")
    render_element(
        cv,
        {
            "type": "svg",
            "svg": svg_20,
            "box": [40, 45, 280, 135],
            "render_mode": "browser",
        },
        _ctx(t=1.0),
    )
    frame = cv.final()
    assert frame.mode == "RGB"
    assert _nonzero_pixels(frame) > 5000
    assert (
        len(set(frame.get_flattened_data())) > 40
    )  # real gradient + shadow, not flat fill


def test_svg_rejects_unsafe_doctype_entity(capsys):
    unsafe = '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg/>'
    cv = SupersampledCanvas(320, 180, scale=1, background="#000000")
    render_element(cv, {"type": "svg", "svg": unsafe, "box": [0, 0, 100, 100]}, _ctx())
    assert _nonzero_pixels(cv.final()) == 0
    assert "unsafe DOCTYPE/ENTITY" in capsys.readouterr().err


def test_svg_storyboard_validates_with_no_lint_warnings():
    board = {
        "meta": {"title": "SVG Test"},
        "format": {"width": 1280, "height": 720, "fps": 30},
        "scenes": [
            {
                "scene_id": "svg_intro",
                "archetype": "mixed",
                "duration_sec": 2.0,
                "elements": [
                    {"type": "background", "color": "#050811"},
                    {
                        "type": "svg",
                        "svg": SAMPLE_SVG,
                        "box": [440, 160, 840, 560],
                        "reveal": "draw",
                        "glow": True,
                    },
                ],
            }
        ],
    }
    assert storyboard.validate_storyboard(board) == []
    assert storyboard.lint_storyboard(board) == []
