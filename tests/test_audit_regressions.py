"""MVTH Tier 1 & Tier 2 regression tests for all 2026-11-22 audit remediations."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import audio_dsp
import blender_runner
import canvas
import fetch_assets
import hybrid_compositor
import media_harvester
import monetization_gate
import render_engine
import scene_router
import software_3d_projection
import spec_refresh
import storyboard
import tts_align
import tts_normalizer
import verify_output
from elements import ElementContext, render_element
from elements.svg import _SVG_DOC_CACHE, parse_svg_path
from job_cli import main as job_cli_main
from job_director import Director
from job_model import JobError, JobState
from job_store import JobStore


def _ctx(w: int = 320, h: int = 240, local_time: float = 0.5) -> ElementContext:
    return ElementContext(
        width=w,
        height=h,
        t=0.5,
        scene_time=local_time,
        local_time=local_time,
        words=[],
        seed=1,
        zones=canvas.layout_zones(w, h),
    )


# ---------------------------------------------------------------------------
# P0-1 / P1-4: render_engine
# ---------------------------------------------------------------------------


def test_safe_child_path_rejects_traversal(tmp_path: Path) -> None:
    assert (
        render_engine._safe_child_path(tmp_path, "scene_01").parent
        == tmp_path.resolve()
    )
    for bad in ("../evil", "a/b", "a\\b", ".", "..", ""):
        with pytest.raises(ValueError):
            render_engine._safe_child_path(tmp_path, bad)


def test_loudnorm_filter_pass1_includes_acompressor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_argvs: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        seen_argvs.append(list(argv))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="",
            stderr='{"input_i": "-16.0", "input_tp": "-2.0", "input_lra": "4.0", "input_thresh": "-26.0", "target_offset": "0.0"}',
        )

    monkeypatch.setattr(render_engine.subprocess, "run", fake_run)
    flt = render_engine._loudnorm_filter(tmp_path / "master.wav")
    assert seen_argvs, "Pass 1 ffmpeg was not invoked"
    assert "acompressor=" in " ".join(seen_argvs[0])
    assert "loudnorm=" in flt


def test_load_blender_tracks_lru_cache_hits_and_refreshes(tmp_path: Path) -> None:
    render_engine._TRACKS_CACHE.clear()
    tracks_file = tmp_path / "anchor_tracks.json"
    tracks_file.write_text(
        json.dumps(
            {
                "frames": [
                    {
                        "anchors": [
                            {"anchor_id": "a1", "u": 0.5, "v": 0.5, "visible": True}
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    spec = {"anchors_3d": [{"anchor_id": "a1", "label": "A1"}]}
    first = render_engine._load_blender_tracks(tracks_file, 0, spec)
    assert len(render_engine._TRACKS_CACHE) == 1
    second = render_engine._load_blender_tracks(tracks_file, 0, spec)
    assert second == first


def test_render_broken_pipe_cleans_up_partial_mp4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = json.loads(
        (REPO / "examples" / "tri_archetype_storyboard.json").read_text(
            encoding="utf-8"
        )
    )
    board["scenes"] = [board["scenes"][0]]
    board["scenes"][0]["duration_sec"] = 0.2
    board["scenes"][0]["sfx_events"] = []
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(board), encoding="utf-8")
    out_mp4 = tmp_path / "out.mp4"

    fake_stdin = MagicMock()
    fake_stdin.closed = False
    fake_stdin.write.side_effect = BrokenPipeError("broken")
    fake_proc = MagicMock()
    fake_proc.stdin = fake_stdin
    fake_proc.poll.return_value = None
    fake_proc.returncode = 1

    monkeypatch.setattr(render_engine.subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr(render_engine, "_loudnorm_filter", lambda _p: "anull")
    monkeypatch.setattr(
        render_engine.audio_dsp, "build_master_wav", lambda *a, **kw: 0.2
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render_engine.py",
            "--storyboard",
            str(board_path),
            "--output",
            str(out_mp4),
            "--no-verify",
        ],
    )
    rc = render_engine.main()
    assert rc == 4
    assert not out_mp4.exists()
    fake_proc.wait.assert_called()


# ---------------------------------------------------------------------------
# P0-2: monetization_gate
# ---------------------------------------------------------------------------


def test_monetization_gate_blocks_scene_narration_and_static_zoom(
    tmp_path: Path,
) -> None:
    board = {
        "meta": {"title": "Test"},
        "format": {"width": 1280, "height": 720, "fps": 30},
        "scenes": [
            {
                "scene_id": "s1",
                "archetype": "doc_essay",
                "duration_sec": 6.0,
                "narration": "This company is a criminal scam and fraud.",
                "transition": "cut",
                "camera": {"mode": "zoom", "zoom_start": 1.0, "zoom_end": 1.0},
                "elements": [{"type": "background", "color": "#000000"}],
            }
        ],
    }
    res = monetization_gate.check_board_monetization(
        board, board_path=tmp_path / "b.json"
    )
    assert isinstance(res["issues"], list)
    assert not monetization_gate._scene_moves(board["scenes"][0])


# ---------------------------------------------------------------------------
# P0-4 / spec_refresh: HTTPS redirect & filter_results
# ---------------------------------------------------------------------------


def test_https_only_redirect_handlers_reject_http() -> None:
    req = fetch_assets.urllib.request.Request("https://example.com/a.jpg")
    h1 = fetch_assets._HttpsOnlyRedirectHandler()
    with pytest.raises(fetch_assets.FetchError, match="non-https"):
        h1.redirect_request(req, None, 302, "Found", {}, "http://example.com/a.jpg")

    h2 = spec_refresh._HttpsOnlyRedirectHandler()
    with pytest.raises(ValueError, match="non-https"):
        h2.redirect_request(req, None, 302, "Found", {}, "file:///etc/passwd")


def test_fetch_assets_filter_results_handles_non_int_width() -> None:
    kept = fetch_assets.filter_results(
        [
            {"url": "https://a.example/1.jpg", "license": "cc0", "width": "unknown"},
            {"url": "https://a.example/2.jpg", "license": "cc0", "width": 1200},
        ]
    )
    assert len(kept) == 2
    assert kept[0]["width"] == 1200


# ---------------------------------------------------------------------------
# P0-6 / P1-12: elements/*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spacing", [0, -10, float("nan")])
def test_paint_grid_invalid_spacing_is_noop(spacing: float) -> None:
    cv = canvas.SupersampledCanvas(160, 120, scale=1, background="#050508")
    cv.set_frame(0.5, 0.5)
    before = cv.final().tobytes()
    render_element(cv, {"type": "grid", "spacing": spacing}, _ctx(160, 120))
    assert cv.final().tobytes() == before


def test_paint_leader_arrow_traces_elbow_vertex() -> None:
    cv = canvas.SupersampledCanvas(200, 200, scale=1, background="#000000")
    cv.set_frame(0.5, 1.0)
    el = {
        "type": "leader_arrow",
        "points": [[20, 180], [20, 20], [180, 20]],
        "speed": 10.0,
        "color": "#FFFFFF",
        "width": 6,
    }
    render_element(cv, el, _ctx(200, 200, local_time=1.0))
    im = cv.final().convert("RGB")
    # Elbow vertex (20, 20) must be painted; diagonal midpoint (100, 100) must stay black
    assert im.getpixel((20, 20)) != (0, 0, 0)
    assert im.getpixel((100, 100)) == (0, 0, 0)


def test_paint_scaling_chart_zero_exponent_and_nonpositive_odo() -> None:
    cv = canvas.SupersampledCanvas(320, 240, scale=1, background="#050508")
    cv.set_frame(0.5, 0.5)
    render_element(
        cv,
        {"type": "scaling_chart", "exponent": 0.0, "odo_from": 0.0, "odo_to": 10.0},
        _ctx(320, 240),
    )
    assert cv.final().getbbox() is not None


def test_paint_map_callout_and_right_chat_bubble_stay_in_bounds() -> None:
    cv = canvas.SupersampledCanvas(400, 300, scale=1, background="#050508")
    cv.set_frame(0.5, 2.0)
    render_element(
        cv,
        {"type": "map_callout", "label": "Cape Town", "pos": [200, 120]},
        _ctx(400, 300, local_time=2.0),
    )
    render_element(
        cv,
        {
            "type": "chat_bubble",
            "box": [20, 140, 380, 280],
            "bubbles": [{"side": "right", "text": "Hi"}],
        },
        _ctx(400, 300, local_time=2.0),
    )
    assert cv.final().getbbox() is not None


# ---------------------------------------------------------------------------
# P1-7 / P1-9 / P1-6: svg, canvas, software_3d_projection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("d", ["M 0 0 H", "M 10 L Z", "M 0 0 C 1 2", "M"])
def test_parse_svg_path_truncated_commands_do_not_crash(d: str) -> None:
    subpaths = parse_svg_path(d)
    assert isinstance(subpaths, list)
    assert len(_SVG_DOC_CACHE) <= 64


def test_canvas_color_cache_font_weight_and_bloom_fastpath() -> None:
    assert canvas.parse_color("#FF0000", 128) != canvas.parse_color("#FF0000", 255)
    f_reg = canvas.find_font(bold=False)
    f_bold = canvas.find_font(bold=True)
    assert f_reg != f_bold

    cv = canvas.SupersampledCanvas(120, 80, scale=2, background="#101010")
    cv.set_frame(0.0, 0.0)
    assert cv.bloom_image.getbbox() is None
    assert cv.final().size == (120, 80)


@pytest.mark.parametrize("elev", [90.0, -90.0])
def test_software_3d_camera_handles_gimbal_lock(elev: float) -> None:
    cam = software_3d_projection.PerspectiveCamera3D(
        eye=(0.0, 0.0, 5.0 if elev > 0 else -5.0),
        target=(0.0, 0.0, 0.0),
    )
    assert len(cam.right) == 3


# ---------------------------------------------------------------------------
# P1-11 / P1-3 / P1-2: tts_normalizer, tts_align, media_harvester -> qc_gate
# ---------------------------------------------------------------------------


def test_tts_normalizer_preserves_tech_tokens_and_rejects_bad_dates() -> None:
    assert (
        tts_normalizer.normalize_text("Upgrade to DDR5 and GTX1080")
        == "Upgrade to DDR5 and GTX1080"
    )
    assert "2026-02-31" in tts_normalizer.normalize_text("Date 2026-02-31 invalid")
    assert (
        "five hundred rand" in tts_normalizer.normalize_text("Costs R500 today").lower()
    )
    assert "February" in tts_normalizer.normalize_text("2026-02-28")


def test_tts_align_nested_output_and_4_5_aspect(tmp_path: Path) -> None:
    assert "4:5" in tts_align.ASPECTS
    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps(
            {
                "title": "Nested Test",
                "aspect": "4:5",
                "scenes": [
                    {
                        "scene_id": "s1",
                        "narration": "Hello world.",
                        "archetype": "doc_essay",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_board = tmp_path / "sub" / "dir" / "board.json"
    rc = tts_align.main(
        [
            "--input",
            str(script_path),
            "--output",
            str(out_board),
            "--media-dir",
            str(tmp_path / "audio"),
            "--aspect",
            "4:5",
            "--offline",
        ]
    )
    assert rc == 0
    board = json.loads(out_board.read_text(encoding="utf-8"))
    assert board["format"]["width"] == 1440
    assert board["format"]["height"] == 1800


def test_media_harvester_credits_roundtrip_passes_qc_gate(tmp_path: Path) -> None:
    c1 = {
        "query": "Ada",
        "generated_at": "2026-11-22T00:00:00Z",
        "count": 1,
        "originality_note": "Original commentary.",
        "assets": [
            {
                "file": "portraits/01_ada.jpg",
                "attribution": "Photo by Ada",
                "source_url": "https://example.org/ada",
                "license": "by",
            }
        ],
    }
    c2 = {
        "query": "Grace",
        "generated_at": "2026-11-22T00:00:00Z",
        "count": 1,
        "originality_note": "Original commentary.",
        "assets": [
            {
                "file": "portraits/02_grace.jpg",
                "attribution": "Photo by Grace",
                "source_url": "https://example.org/grace",
                "license": "cc0",
            }
        ],
    }
    media_harvester.write_credits(tmp_path, c1)
    _, md_path = media_harvester.write_credits(tmp_path, c2)
    md_text = md_path.read_text(encoding="utf-8")
    assert "portraits/01_ada.jpg" in md_text
    assert "portraits/02_grace.jpg" in md_text


# ---------------------------------------------------------------------------
# P1-13 / Wave 2: job_director & job_cli
# ---------------------------------------------------------------------------


def test_job_director_export_audit_charge_and_brief_wiring(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    board_data = json.loads(
        (REPO / "examples" / "tri_archetype_storyboard.json").read_text(
            encoding="utf-8"
        )
    )
    req = json.loads(
        (REPO / "examples" / "jobs" / "horse_tenny.json").read_text(encoding="utf-8")
    )
    req["target_duration_seconds"] = round(storyboard.total_duration(board_data))

    def ok_runner(argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        if "--output" in argv:
            Path(argv[argv.index("--output") + 1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    d = Director(store, runner=ok_runner)
    jid = d.create(req)

    # Invalid brief must fail BEFORE transitioning state
    bad_brief = tmp_path / "bad_brief.json"
    bad_brief.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
    with pytest.raises(JobError, match="invalid investigation brief"):
        d.plan(jid, brief_path=bad_brief)
    assert store.state(jid) is JobState.VALIDATED

    # Valid brief attaches investigation_brief.json
    valid_brief = tmp_path / "brief.json"
    valid_brief.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "subject": "Horse Tenny",
                "facts": [
                    {
                        "claim_id": "claim-00000001",
                        "claim_type": "factual",
                        "claim": "Horses like gardens.",
                        "source": "https://example.org",
                    },
                    {
                        "claim_id": "claim-00000002",
                        "claim_type": "factual",
                        "claim": "Tenny owns a garden.",
                        "source": "https://example.org/2",
                    },
                    {
                        "claim_id": "claim-00000003",
                        "claim_type": "statistical",
                        "claim": "Ratings are 4.2 stars.",
                        "source": "https://example.org/3",
                    },
                ],
                "visual_anchors": [
                    {
                        "claim_index": 0,
                        "primitive": "quote_card",
                    }
                ],
                "target_format": {
                    "aspect": "16:9",
                    "platform": "youtube",
                },
            }
        ),
        encoding="utf-8",
    )
    assert job_cli_main(["validate-brief", str(valid_brief)]) == 0
    assert job_cli_main(["validate-brief", str(bad_brief)]) == 1

    req_path = d.plan(jid, brief_path=valid_brief)
    req_json = json.loads(req_path.read_text(encoding="utf-8"))
    assert req_json["investigation_brief"]["claim_ids"] == [
        "claim-00000001",
        "claim-00000002",
        "claim-00000003",
    ]

    with pytest.raises(JobError, match="finite"):
        d.charge(jid, float("nan"), "bad")

    board_file = tmp_path / "board.json"
    board_file.write_text(json.dumps(board_data), encoding="utf-8")
    assert d.submit(jid, board_file) == []
    d.preview(jid)

    # Timeout in audit() transitions cleanly to REJECTED
    def timeout_runner(
        _argv: list[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["verify_output.py"], 10)

    d_timeout = Director(store, runner=timeout_runner)
    rep = d_timeout.audit(jid)
    assert rep["ok"] is False
    assert store.state(jid) is JobState.REJECTED


# ---------------------------------------------------------------------------
# P2-1 / P2-3 / P2-4 / P3-2 / verify_output: audio_dsp, hybrid, router, blender, verify
# ---------------------------------------------------------------------------


def test_audio_dsp_no_pad_double_sum_and_smooth_duck_release(tmp_path: Path) -> None:
    # 0-frame non-48kHz WAV returns []
    empty_wav = tmp_path / "empty.wav"
    with wave.open(str(empty_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"")
    assert audio_dsp.read_wav_mono(empty_wav, audio_dsp.RATE) == []

    # Short VO in mix_timeline releases ducking smoothly by end of timeline
    vo_wav = tmp_path / "short.wav"
    samples = array(
        "h",
        [
            int(0.8 * math.sin(2 * math.pi * 200 * i / audio_dsp.RATE) * 32767)
            for i in range(audio_dsp.RATE // 5)
        ],
    )
    with wave.open(str(vo_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio_dsp.RATE)
        w.writeframes(samples.tobytes())
    mixed = audio_dsp.mix_timeline(
        1.2, vo_wav, pad=True, pad_level=0.08, duck_depth=0.9
    )
    tail_peak = max(abs(s) for s in mixed[-audio_dsp.RATE // 5 :])
    assert tail_peak > 0

    # Overlapping scenes must not double-sum pad
    out_wav = tmp_path / "master.wav"
    scenes = [
        {"start_sec": 0.0, "duration_sec": 0.5},
        {"start_sec": 0.0, "duration_sec": 0.5},
    ]
    audio_dsp.build_master_wav(scenes, out_wav, pad=True, pad_level=0.05)
    with wave.open(str(out_wav), "rb") as w:
        frames = array("h", w.readframes(w.getnframes()))
    expected_peak = max(
        abs(audio_dsp.pad_at(i / audio_dsp.RATE, 0.05)) for i in range(1000)
    )
    actual_peak = max(abs(s) for s in frames[:2000]) / audio_dsp.FULL_SCALE
    assert actual_peak == pytest.approx(expected_peak, rel=0.05)


def test_hybrid_compositor_720x1280_9_16_scales_cleanly() -> None:
    cv = canvas.SupersampledCanvas(720, 1280, scale=1, background="#000000")
    cv.set_frame(0.5, 0.5)
    hybrid_compositor.composite_3d_tracked_hud(
        cv,
        [
            {
                "anchor_id": "a1",
                "u": 0.5,
                "v": 0.5,
                "visible": True,
                "label": "Node",
                "metric": "1.0x",
            }
        ],
        "Node Topology",
        0.5,
        aspect_ratio="9:16",
    )
    assert cv.final().size == (720, 1280)


def test_scene_router_word_boundaries_and_distinct_hits() -> None:
    assert (
        scene_router._keyword_hits(scene_router.KEYWORDS_3D, "The audience studied")
        == 0
    )
    assert scene_router._keyword_hits(scene_router.KEYWORDS_3D, "3d 3d 3d") == 1


def test_blender_runner_camera_location_and_docstring() -> None:
    assert "network_topology_3d" in (blender_runner.__doc__ or "")
    assert "external_asset_3d" in (blender_runner.__doc__ or "")
    p0 = blender_runner.compute_camera_location(
        {"target_pos": [1.0, 2.0, 3.0], "mode": "static"}, 0.0
    )
    p1 = blender_runner.compute_camera_location(
        {"target_pos": [1.0, 2.0, 3.0], "mode": "static"}, 1.0
    )
    assert p0 == p1
    assert p0[2] > 3.0


def test_verify_output_detail_strings_and_unmeasured_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_mp4 = tmp_path / "v.mp4"
    fake_mp4.write_bytes(b"mp4")
    monkeypatch.setattr(
        verify_output,
        "_ffprobe_json",
        lambda _p: {
            "format": {},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "pix_fmt": "yuv420p",
                    "width": 1280,
                    "height": 720,
                    "r_frame_rate": "30/1",
                },
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
            ],
        },
    )
    rep = verify_output.verify_mp4(
        fake_mp4,
        expected_width=1280,
        expected_height=720,
        expected_fps=30,
        expected_duration=3.0,
    )
    by_name = {c["check"]: c for c in rep["checks"]}
    assert "==" in by_name["width"]["detail"]
    assert "==" in by_name["height"]["detail"]
    assert "==" in by_name["fps"]["detail"]
    assert by_name["duration_drift_le_150ms"]["ok"] is False


def test_threejs_scenes_module_syntax_and_update() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    res = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            "import * as s from './scripts/threejs/scenes.mjs'; console.log(s.SUPPORTED_CATEGORIES.length);",
        ],
        cwd=str(REPO),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "5"
