#!/usr/bin/env python3
"""tts_align.py — audio-first timing generator for surgical-media.

Reads a beat script (schemas/script.schema.json), voices each scene
(edge-tts, or the local Kokoro-82M engine when installed, otherwise an
offline words-per-minute estimate), probes the *exact* voiced duration, and
emits a storyboard.json whose scene windows and per-word timestamps are
locked to that audio. Visuals are derived from audio — never the other way.

Image-first (v3.2.0): with ``--assets-manifest`` (fetch_assets.py output),
every scene is wired with a licensed subject plate via ``asset_wire.py``;
per-scene ``visual`` hints (image/query/kind/fit) art-direct the wiring.
Without a manifest, scenes fall back to generic archetype templates whose
filler elements are flagged ``placeholder: true`` and warned about.

Two timing paths:

* Online (edge-tts reachable): word timings come from the service's measured
  WordBoundary events (100 ns ticks) — kinetic captions highlight the word
  that is actually being spoken. Stems are transcoded as-is (silence is NOT
  stripped, because word offsets are relative to the untrimmed stem).
* Local Kokoro (--engine kokoro / auto when the runtime is installed): a
  48 kHz stem from Kokoro-82M (default voice ``af_heart``) with word spans
  allocated from the model's own phoneme lengths. No network or API key.
* Offline (--offline, or any TTS failure): syllable-weighted duration
  allocation plus punctuation pause bonuses — long multisyllabic words get
  proportionally more time and sentence boundaries get a real beat of
  silence — so captions land on the syllable rather than a uniform index.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asset_wire import load_manifest, wire_board
from kokoro_voice import DEFAULT_VOICE as KOKORO_DEFAULT_VOICE
from kokoro_voice import is_available as kokoro_available
from kokoro_voice import runtime_python as kokoro_runtime_python
from storyboard import SCENE_ID_RE, assign_start_times, scene_has_subject_visual

ASPECTS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1440, 1800),
}
# Archetype fallback templates — GENERIC filler, flagged ``placeholder: true``
# so asset_wire.py strips it when a licensed subject plate is wired in, and
# style_lint.py flags it when a board ships without subject imagery.
# Image-first: pass --assets-manifest (fetch_assets.py output) so every scene
# shows the subject instead of these topic-agnostic stand-ins.
DEFAULT_ELEMENTS = {
    "geometry_rig": [
        {"type": "background", "color": "#050508"},
        {"type": "phi_divider", "box": [260, 380, 1400, 700], "placeholder": True},
        {
            "type": "stick_rig",
            "x": 960,
            "y": 940,
            "height": 420,
            "reach_to": [960, 470],
            "placeholder": True,
        },
        {"type": "kinetic_captions"},
    ],
    "doc_essay": [
        {"type": "background", "color": "#0A0E17"},
        {
            "type": "grid",
            "spacing": 90,
            "color": "#1E293B",
            "alpha": 0.5,
            "placeholder": True,
        },
        {
            "type": "scaling_chart",
            "box": [220, 260, 1480, 620],
            "exponent": 4.35,
            "odometer_from": 1.0,
            "odometer_to": 500.0,
            "accent": "#38BDF8",
            "label": "COMPUTE",
            "placeholder": True,
        },
        {"type": "kinetic_captions"},
    ],
    "code_report": [
        {"type": "background", "color": "#0D1117"},
        {
            "type": "system_architecture",
            "origin": [960, 340],
            "nodes": [
                {"id": "lb", "label": "L7 LB", "x": 480, "y": 300},
                {"id": "ex1", "label": "EXCHANGE-1", "x": 1440, "y": 180},
                {"id": "ex2", "label": "EXCHANGE-2", "x": 1440, "y": 420},
                {"id": "ex3", "label": "EXCHANGE-3", "x": 1440, "y": 660},
            ],
            "cascade_start": 1.2,
            "cascade_step": 0.7,
            "placeholder": True,
        },
        {"type": "kinetic_captions"},
    ],
    "mixed": [{"type": "background", "color": "#0A0E17"}, {"type": "kinetic_captions"}],
}

PUNCT_PAUSE = (
    (".", 1.15),
    ("?", 1.15),
    ("!", 1.15),
    (",", 0.65),
    (":", 0.65),
    (";", 0.65),
    ("—", 0.40),
)
_VOWELS = re.compile(r"[aeiouyAEIOUY]+")


def syllable_count(word: str) -> int:
    core = re.sub(r"[^A-Za-z]", "", word)
    if not core:
        return 1
    groups = _VOWELS.findall(core)
    count = len(groups)
    # silent trailing e ("theme", "code") — not when it forms its own group like "the"
    if (
        count > 1
        and core.lower().endswith("e")
        and not core.lower().endswith(("le", "ee", "ye"))
    ):
        count -= 1
    return max(1, count)


def word_weight(word: str) -> float:
    weight = float(syllable_count(word))
    for mark, bonus in PUNCT_PAUSE:
        if word.rstrip().endswith(mark):
            weight += bonus
            break
    return weight


def word_boundaries_from_events(
    events: list[tuple[str, int, int]],
) -> list[dict[str, Any]]:
    """Convert edge-tts WordBoundary events (100 ns ticks) to word dicts."""
    words: list[dict[str, Any]] = []
    for token, offset, duration in events:
        token = str(token).strip()
        if not token:
            continue
        start = offset / 10_000_000.0
        end = (offset + duration) / 10_000_000.0
        words.append({"word": token, "start": round(start, 3), "end": round(end, 3)})
    return words


def align_words(text: str, duration_sec: float) -> list[dict[str, Any]]:
    words = text.split()
    if not words:
        return []
    weights = [word_weight(w) for w in words]
    total = sum(weights) or 1.0
    cursor = 0.0
    out = []
    for w, weight in zip(words, weights):
        span = duration_sec * (weight / total)
        out.append(
            {
                "word": w,
                "start": round(cursor, 3),
                "end": round(min(duration_sec, cursor + span), 3),
            }
        )
        cursor += span
    if out:
        out[-1]["end"] = round(duration_sec, 3)
    return out


def estimate_duration(text: str, wpm: float) -> float:
    if wpm <= 0:
        raise ValueError(f"wpm must be positive (got {wpm})")
    words = max(1, len(text.split()))
    return (
        words / (wpm / 60.0)
        + sum(1 for w in text.split() if w.rstrip()[-1:] in ".?!") * 0.25
    )


async def _edge_tts_capture(
    text: str,
    voice: str,
    out_path: Path,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> list[tuple[str, int, int]]:
    """Write the mp3 and return WordBoundary events (100 ns ticks)."""
    import edge_tts  # optional dependency

    communicate = edge_tts.Communicate(
        text, voice, rate=rate, pitch=pitch, boundary="WordBoundary"
    )
    events: list[tuple[str, int, int]] = []
    with out_path.open("wb") as fh:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                fh.write(chunk["data"])
            elif kind == "WordBoundary":
                events.append(
                    (
                        str(chunk["text"]),
                        int(chunk["offset"]),
                        int(chunk["duration"]),
                    )
                )
    return events


def synthesize_voice(
    text: str,
    voice: str,
    media_dir: Path,
    scene_id: str,
    trim_silence: bool,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> tuple[Path | None, float | None, list[dict[str, Any]] | None]:
    """Returns (wav_path, duration_sec, words_or_None)."""
    raw_mp3 = media_dir / f"{scene_id}.mp3"
    wav_out = media_dir / f"{scene_id}.wav"
    try:
        events = asyncio.run(
            _edge_tts_capture(text, voice, raw_mp3, rate=rate, pitch=pitch)
        )
    except Exception as exc:  # noqa: BLE001 — network down, voice missing, package absent: all fall back
        print(
            f"tts_align: edge-tts unavailable for {scene_id!r} ({exc.__class__.__name__}); "
            f"using offline estimate",
            file=sys.stderr,
        )
        return None, None, None

    words = word_boundaries_from_events(events) if events else None

    # When measured word boundaries exist we keep the stem untrimmed —
    # boundary offsets are relative to the untrimmed audio.
    filters = (
        "silenceremove=start_periods=1:start_threshold=-38dB:stop_periods=-1:stop_threshold=-38dB"
        if (trim_silence and words is None)
        else None
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_mp3)]
    if filters:
        cmd += ["-af", filters]
    cmd += ["-ar", "48000", "-ac", "1", "-sample_fmt", "s16", str(wav_out)]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print(
            f"tts_align: ffmpeg transcode failed for {scene_id!r}: {exc}",
            file=sys.stderr,
        )
        return None, None, None

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(wav_out),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            text=True,
        )
        duration = float(probe.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError):
        print(
            f"tts_align: ffprobe duration failed for {scene_id!r}; using estimate",
            file=sys.stderr,
        )
        return None, None, None
    return wav_out, duration, words


def synthesize_kokoro_voice(
    text: str,
    voice: str,
    media_dir: Path,
    scene_id: str,
) -> tuple[Path | None, float | None, list[dict[str, Any]] | None]:
    """Render a beat through the local Kokoro engine and return its timing.

    Kokoro runs in its own venv, so this is a subprocess call. The helper
    prints one JSON line with the measured duration and phoneme-weighted
    word spans.
    """
    wav_out = media_dir / f"{scene_id}.wav"
    helper = Path(__file__).resolve().with_name("kokoro_voice.py")
    cmd = [
        str(kokoro_runtime_python()),
        str(helper),
        "--text",
        text,
        "--out",
        str(wav_out),
        "--voice",
        voice,
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        payload: dict[str, Any] | None = None
        for line in reversed(proc.stdout.strip().splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                payload = candidate
                break
        if payload is None:
            raise ValueError("Kokoro helper produced no JSON payload")
        duration = float(payload["duration"])
        words = list(payload["words"])
    except (subprocess.SubprocessError, OSError, KeyError, ValueError) as exc:
        print(
            f"tts_align: local Kokoro failed for {scene_id!r} "
            f"({exc.__class__.__name__}: {exc}); using offline estimate",
            file=sys.stderr,
        )
        return None, None, None
    return wav_out, duration, words


RATE_RE = re.compile(r"^[+-]\d+%$")
PITCH_RE = re.compile(r"^[+-]\d+Hz$")


def validate_rate(value: str) -> str:
    """argparse type for --rate: edge-tts speaking-rate adjustment strings."""
    if not RATE_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"--rate must look like '+12%' or '-12%' (got {value!r})"
        )
    return value


def validate_pitch(value: str) -> str:
    """argparse type for --pitch: edge-tts pitch-adjustment strings."""
    if not PITCH_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"--pitch must look like '+2Hz' or '-2Hz' (got {value!r})"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a timing-locked storyboard from a beat script."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Beat script JSON (script.schema.json)",
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="storyboard.json to write"
    )
    parser.add_argument(
        "--voice", default=None, help="edge-tts voice (overrides script voice)"
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "edge", "kokoro"),
        default="auto",
        help="voice engine: auto prefers local Kokoro when installed (default)",
    )
    parser.add_argument(
        "--kokoro-voice",
        default=KOKORO_DEFAULT_VOICE,
        help=f"local Kokoro voice (default: {KOKORO_DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--rate",
        default="+0%",
        type=validate_rate,
        help="edge-tts speaking rate adjustment (e.g. '-12%%' for calm poetry)",
    )
    parser.add_argument(
        "--pitch",
        default="+0Hz",
        type=validate_pitch,
        help="edge-tts pitch adjustment (e.g. '-2Hz' for warmer tone)",
    )
    parser.add_argument(
        "--pad-tail",
        type=float,
        default=0.0,
        help="Extra breathing silence in seconds appended to each scene duration",
    )
    parser.add_argument("--aspect", choices=sorted(ASPECTS), default="16:9")
    parser.add_argument("--fps", type=int, choices=[24, 25, 30, 50, 60], default=30)
    parser.add_argument(
        "--offline", action="store_true", help="Skip TTS; estimate durations from WPM"
    )
    parser.add_argument(
        "--wpm", type=float, default=165.0, help="Fallback speaking rate (default 165)"
    )
    parser.add_argument(
        "--trim-silence",
        action="store_true",
        help="Strip silence below -38 dB (only applied when word boundaries are unavailable)",
    )
    parser.add_argument(
        "--media-dir",
        type=Path,
        default=None,
        help="Directory for voice stems (default: <output dir>/audio)",
    )
    parser.add_argument(
        "--assets-manifest",
        type=Path,
        default=None,
        help="fetch_assets.py manifest.json — wire licensed subject plates into "
        "every scene (image-first). Without it, scenes fall back to generic "
        "archetype filler flagged placeholder:true.",
    )
    parser.add_argument(
        "--subject",
        default="",
        help="Board subject for keyword-matching manifest plates to scenes",
    )
    parser.add_argument(
        "--brief",
        type=Path,
        default=None,
        help="investigation_brief.json — visual_anchors steer per-scene plate choice",
    )
    args = parser.parse_args(argv)
    engine = args.engine
    if engine == "auto":
        engine = "kokoro" if kokoro_available() else "edge"

    try:
        script = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"tts_align: cannot read script: {exc}", file=sys.stderr)
        return 2

    scenes_in = script.get("scenes")
    if not isinstance(scenes_in, list) or not scenes_in:
        print("tts_align: script.scenes must be a non-empty array", file=sys.stderr)
        return 2

    voice = args.voice or script.get("voice") or "en-US-ChristopherNeural"
    voice_overrides = script.get("voices")
    if not isinstance(voice_overrides, dict):
        voice_overrides = {}
    wpm = float(script.get("wpm") or args.wpm)
    if wpm <= 0:
        print(f"tts_align: wpm must be positive (got {wpm})", file=sys.stderr)
        return 2
    width, height = ASPECTS[args.aspect]
    media_dir = args.media_dir or (args.output.parent / "audio")
    media_dir.mkdir(parents=True, exist_ok=True)
    out_dir_resolved = args.output.resolve().parent

    scenes_out = []
    for idx, raw in enumerate(scenes_in):
        scene_id = str(raw.get("scene_id") or f"scene_{idx + 1:02d}")
        if not SCENE_ID_RE.match(scene_id):
            print(
                f"tts_align: invalid scene_id {scene_id!r} (must match ^[a-z0-9_-]{{1,64}}$)",
                file=sys.stderr,
            )
            return 2
        narration = str(raw.get("narration") or "").strip()
        if not narration:
            print(f"tts_align: scene {scene_id!r} has empty narration", file=sys.stderr)
            return 2
        archetype = str(raw.get("archetype") or "doc_essay")
        scene_voice = str(raw.get("voice") or voice_overrides.get(scene_id) or voice)

        vo_rel = None
        duration = None
        boundary_words = None
        if not args.offline:
            if engine == "kokoro":
                local_voice = str(
                    raw.get("kokoro_voice")
                    or script.get("kokoro_voice")
                    or args.kokoro_voice
                )
                wav_path, duration, boundary_words = synthesize_kokoro_voice(
                    narration, local_voice, media_dir, scene_id
                )
            else:
                wav_path, duration, boundary_words = synthesize_voice(
                    narration,
                    scene_voice,
                    media_dir,
                    scene_id,
                    args.trim_silence,
                    rate=args.rate,
                    pitch=args.pitch,
                )
            if wav_path is not None:
                vo_rel = Path(
                    os.path.relpath(wav_path.resolve(), out_dir_resolved)
                ).as_posix()
        if duration is None:
            duration = estimate_duration(narration, wpm)
        spoken_dur = max(0.5, duration)
        duration = round(spoken_dur + max(0.0, float(args.pad_tail)), 3)

        element_template = json.loads(
            json.dumps(DEFAULT_ELEMENTS.get(archetype, DEFAULT_ELEMENTS["mixed"]))
        )
        # adapt design-space x coordinates to target width
        sx = width / 1920.0
        sy = height / 1080.0
        for el in element_template:
            for key in ("box", "origin", "reach_to"):
                if key in el:
                    vals = el[key]
                    if len(vals) == 4:
                        el[key] = [
                            vals[0] * sx,
                            vals[1] * sy,
                            vals[2] * sx,
                            vals[3] * sy,
                        ]
                    else:
                        el[key] = [vals[0] * sx, vals[1] * sy]
            if el.get("type") == "stick_rig":
                el["x"] = el.get("x", 960) * sx
                el["y"] = el.get("y", 940) * sy
                el["height"] = el.get("height", 420) * sy
        # drop reach_to when it would exceed bottom safe zone on 9:16
        if args.aspect == "9:16":
            pass  # safe-zone clamping is the renderer's job; keep coordinates editable

        scene = {
            "scene_id": scene_id,
            "archetype": archetype,
            "narration": narration,
            "duration_sec": duration,
            "camera": {
                "zoom_start": 1.0,
                "zoom_end": 1.12,
                "pan_x": 0.5,
                "pan_y": 0.5,
                "easing": "ease_out_expo",
            },
            "elements": element_template,
            "words": (
                boundary_words if boundary_words else align_words(narration, duration)
            ),
            "sfx_events": [],
        }
        visual = raw.get("visual")
        if isinstance(visual, dict) and visual:
            scene["visual"] = visual
        if vo_rel:
            scene["vo_wav"] = vo_rel
        scenes_out.append(scene)

    storyboard: dict[str, Any] = {
        "meta": {
            "title": str(script.get("title") or args.input.stem),
            "seed": 20261118,
        },
        "format": {"width": width, "height": height, "fps": args.fps},
        "scenes": scenes_out,
        "audio": {
            "pad": False,
            "duck_depth": 0.72,
            "sample_rate": 48000,
        },
    }
    actual_voice = (
        ""
        if args.offline
        else (
            str(script.get("kokoro_voice") or args.kokoro_voice)
            if engine == "kokoro"
            else voice
        )
    )
    if not args.offline:
        provenance = f"Voice: {engine}/{actual_voice}."
        previous = str(storyboard["meta"].get("description", ""))
        storyboard["meta"]["description"] = (previous + " " + provenance).strip()[:400]
    # Image-first wiring: licensed subject plates replace generic archetype
    # filler. Runs when a manifest is supplied OR any scene pins visual.image.
    has_explicit = any(
        isinstance(sc.get("visual"), dict) and sc["visual"].get("image")
        for sc in scenes_out
    )
    if args.assets_manifest is not None or has_explicit or args.brief is not None:
        assets = (
            load_manifest(args.assets_manifest)
            if args.assets_manifest is not None
            else []
        )
        subject = args.subject or str(script.get("subject") or "")
        brief: dict[str, Any] | None = None
        if args.brief is not None:
            try:
                loaded = json.loads(args.brief.read_text(encoding="utf-8"))
                brief = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError) as exc:
                print(
                    f"tts_align: cannot read brief {args.brief}: {exc}", file=sys.stderr
                )
                return 2
        storyboard, wire_report = wire_board(
            storyboard,
            assets,
            manifest_dir=(
                args.assets_manifest.resolve().parent
                if args.assets_manifest is not None
                else out_dir_resolved
            ),
            board_dir=out_dir_resolved,
            subject=subject,
            brief=brief,
        )
        wired_n = sum(
            1 for r in wire_report if r["action"] in ("wired", "explicit", "reused")
        )
        print(
            f"tts_align: image-first wiring — {wired_n}/{len(scenes_out)} scenes plated"
        )
    storyboard = assign_start_times(storyboard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(storyboard, indent=2), encoding="utf-8")

    filler = [
        str(sc.get("scene_id"))
        for sc in storyboard["scenes"]
        if not scene_has_subject_visual(sc)
        and any(
            isinstance(e, dict) and e.get("placeholder") is True
            for e in sc.get("elements", [])
        )
    ]
    if filler:
        print(
            f"tts_align: WARNING — {len(filler)} scene(s) show generic filler, not the "
            f"subject ({', '.join(filler)}). Fetch licensed imagery "
            f"(fetch_assets.py) and re-run with --assets-manifest.",
            file=sys.stderr,
        )

    total = sum(sc["duration_sec"] for sc in storyboard["scenes"])
    voiced = sum(1 for sc in storyboard["scenes"] if sc.get("vo_wav"))
    print(
        f"tts_align: wrote {args.output} — {len(scenes_out)} scenes, "
        f"{total:.2f}s total, {voiced} voiced / {len(scenes_out) - voiced} estimated, "
        f"engine={'offline' if args.offline else engine}, voice={actual_voice}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
