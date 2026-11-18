#!/usr/bin/env python3
"""tts_align.py — audio-first timing generator for surgical-media.

Reads a beat script (schemas/script.schema.json), voices each scene
(edge-tts when available and network permits, otherwise an offline
words-per-minute estimate), probes the *exact* voiced duration, and emits a
storyboard.json whose scene windows and per-word timestamps are locked to
that audio. Visuals are then derived from audio — never the other way round.

Two timing paths:

* Online (edge-tts reachable): word timings come from the service's measured
  WordBoundary events (100 ns ticks) — kinetic captions highlight the word
  that is actually being spoken. Stems are transcoded as-is (silence is NOT
  stripped, because word offsets are relative to the untrimmed stem).
* Offline (--offline, or any TTS failure): syllable-weighted duration
  allocation plus punctuation pause bonuses — long multisyllabic words get
  proportionally more time and sentence boundaries get a real beat of
  silence — so captions land on the syllable rather than a uniform index.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from storyboard import assign_start_times

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
DEFAULT_ELEMENTS = {
    "geometry_rig": [
        {"type": "background", "color": "#050508"},
        {"type": "phi_divider", "box": [260, 380, 1400, 700]},
        {
            "type": "stick_rig",
            "x": 960,
            "y": 940,
            "height": 420,
            "reach_to": [960, 470],
        },
        {"type": "kinetic_captions"},
    ],
    "doc_essay": [
        {"type": "background", "color": "#0A0E17"},
        {"type": "grid", "spacing": 90, "color": "#1E293B", "alpha": 0.5},
        {
            "type": "scaling_chart",
            "box": [220, 260, 1480, 620],
            "exponent": 4.35,
            "odometer_from": 1.0,
            "odometer_to": 500.0,
            "accent": "#38BDF8",
            "label": "COMPUTE",
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
    words = max(1, len(text.split()))
    return (
        words / (wpm / 60.0)
        + sum(1 for w in text.split() if w.rstrip()[-1:] in ".?!") * 0.25
    )


async def _edge_tts_capture(
    text: str, voice: str, out_path: Path
) -> list[tuple[str, int, int]]:
    """Write the mp3 and return WordBoundary events (100 ns ticks)."""
    import edge_tts  # optional dependency

    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    events: list[tuple[str, int, int]] = []
    with out_path.open("wb") as fh:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                fh.write(chunk["data"])
            elif kind == "WordBoundary":
                events.append((chunk["text"], chunk["offset"], chunk["duration"]))
    return events


def synthesize_voice(
    text: str, voice: str, media_dir: Path, scene_id: str, trim_silence: bool
) -> tuple[Path | None, float | None, list[dict[str, Any]] | None]:
    """Returns (wav_path, duration_sec, words_or_None)."""
    raw_mp3 = media_dir / f"{scene_id}.mp3"
    wav_out = media_dir / f"{scene_id}.wav"
    try:
        events = asyncio.run(_edge_tts_capture(text, voice, raw_mp3))
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
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
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


def main() -> int:
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
    args = parser.parse_args()

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
    wpm = float(script.get("wpm") or args.wpm)
    width, height = ASPECTS[args.aspect]
    media_dir = args.media_dir or (args.output.parent / "audio")
    media_dir.mkdir(parents=True, exist_ok=True)

    scenes_out = []
    for idx, raw in enumerate(scenes_in):
        scene_id = str(raw.get("scene_id") or f"scene_{idx + 1:02d}")
        narration = str(raw.get("narration") or "").strip()
        if not narration:
            print(f"tts_align: scene {scene_id!r} has empty narration", file=sys.stderr)
            return 2
        archetype = str(raw.get("archetype") or "doc_essay")

        vo_rel = None
        duration = None
        boundary_words = None
        if not args.offline:
            wav_path, duration, boundary_words = synthesize_voice(
                narration, voice, media_dir, scene_id, args.trim_silence
            )
            if wav_path is not None:
                vo_rel = str(wav_path)
        if duration is None:
            duration = estimate_duration(narration, wpm)
        duration = round(max(0.5, duration), 3)

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
        if vo_rel:
            scene["vo_wav"] = vo_rel
        scenes_out.append(scene)

    storyboard = {
        "meta": {
            "title": str(script.get("title") or args.input.stem),
            "seed": 20261118,
        },
        "format": {"width": width, "height": height, "fps": args.fps},
        "scenes": scenes_out,
        "audio": {
            "pad": True,
            "pad_level": 0.055,
            "duck_depth": 0.72,
            "sample_rate": 48000,
        },
    }
    storyboard = assign_start_times(storyboard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(storyboard, indent=2), encoding="utf-8")

    total = sum(sc["duration_sec"] for sc in storyboard["scenes"])
    voiced = sum(1 for sc in storyboard["scenes"] if sc.get("vo_wav"))
    print(
        f"tts_align: wrote {args.output} — {len(scenes_out)} scenes, "
        f"{total:.2f}s total, {voiced} voiced / {len(scenes_out) - voiced} estimated, voice={voice}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
