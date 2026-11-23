#!/usr/bin/env python3
"""Local Kokoro-82M voice engine for surgical-media.

Runs under the small Python 3.12 venv created by ``scripts/setup_kokoro.sh``;
the pipeline itself stays stdlib-only and calls this module as a subprocess.
The ONNX export exposes waveform only (no duration output), so word spans are
allocated from phoneme lengths measured by Kokoro's own tokenizer rather than
from a uniform index.

Environment overrides:
    KOKORO_HOME      runtime directory (default ~/.cache/surgical-media/kokoro)
    KOKORO_PYTHON    interpreter used to run the engine (default <home>/venv/bin/python)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import wave
from pathlib import Path
from typing import Any

DEFAULT_HOME = Path.home() / ".cache" / "surgical-media" / "kokoro"
MODEL_NAME = "model_quantized.onnx"
VOICES_NAME = "voices.npz"
DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "en-us"
DEFAULT_SPEED = 1.0

MODEL_URL = (
    "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/"
    "resolve/main/onnx/model_quantized.onnx"
)
VOICE_URL = (
    "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/"
    "resolve/main/voices/{name}.bin"
)
VOICE_NAMES = (
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sky",
    "am_adam",
    "am_eric",
    "am_michael",
    "bm_george",
)

_PAUSE_BONUS = (
    (".", 0.35),
    ("!", 0.35),
    ("?", 0.35),
    (",", 0.15),
    (";", 0.15),
    (":", 0.15),
)


def runtime_dir() -> Path:
    """Resolve the Kokoro runtime directory (env override wins)."""
    return Path(os.environ.get("KOKORO_HOME") or str(DEFAULT_HOME)).expanduser()


def runtime_python() -> Path:
    """Resolve the interpreter for the Kokoro venv."""
    override = os.environ.get("KOKORO_PYTHON")
    if override:
        return Path(override).expanduser()
    return runtime_dir() / "venv" / "bin" / "python"


def is_available() -> bool:
    """True when the runtime interpreter, model and voice bank are present."""
    home = runtime_dir()
    return (
        runtime_python().is_file()
        and (home / MODEL_NAME).is_file()
        and (home / VOICES_NAME).is_file()
    )


def word_weight(word: str, phoneme_len: int) -> float:
    """Phoneme count plus a small pause bonus after sentence punctuation."""
    weight = float(max(1, phoneme_len))
    for mark, bonus in _PAUSE_BONUS:
        if word.rstrip().endswith(mark):
            return weight + bonus
    return weight


def weighted_words(
    text: str, duration_sec: float, phoneme_lengths: list[int]
) -> list[dict[str, Any]]:
    """Allocate a measured duration across words by phoneme weight.

    The result is contiguous and ends exactly at ``duration_sec``.
    """
    words = text.split()
    if not words:
        return []
    if len(phoneme_lengths) != len(words):
        raise ValueError("phoneme_lengths must match the word count")
    weights = [
        word_weight(word, length) for word, length in zip(words, phoneme_lengths)
    ]
    total = sum(weights) or 1.0
    cursor = 0.0
    out: list[dict[str, Any]] = []
    for word, weight in zip(words, weights):
        span = duration_sec * (weight / total)
        out.append(
            {
                "word": word,
                "start": round(cursor, 3),
                "end": round(min(duration_sec, cursor + span), 3),
            }
        )
        cursor += span
    out[-1]["end"] = round(duration_sec, 3)
    return out


def synthesize(
    text: str,
    out_wav: Path,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    lang: str = DEFAULT_LANG,
) -> dict[str, Any]:
    """Write a 48 kHz mono stem and return its duration and word spans.

    Must be called with the venv interpreter; Kokoro is imported lazily so
    this module stays importable from the stdlib pipeline.
    """
    import numpy as np
    from kokoro_onnx import Kokoro

    home = runtime_dir()
    engine = Kokoro(str(home / MODEL_NAME), str(home / VOICES_NAME))
    samples, src_rate = engine.create(text, voice=voice, speed=speed, lang=lang)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    temp_wav = out_wav.with_suffix(".kokoro24k.wav")
    with wave.open(str(temp_wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(src_rate)
        handle.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(temp_wav),
                "-ar",
                "48000",
                "-ac",
                "1",
                "-sample_fmt",
                "s16",
                str(out_wav),
            ],
            check=True,
            timeout=120,
        )
        with wave.open(str(out_wav), "rb") as handle:
            duration = handle.getnframes() / float(handle.getframerate())
    finally:
        temp_wav.unlink(missing_ok=True)

    lengths = [
        len("".join(engine.tokenizer.phonemize(word, lang).split()))
        for word in text.split()
    ]
    return {
        "duration": round(duration, 3),
        "words": weighted_words(text, duration, lengths),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kokoro local voice stem + timings")
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument("--lang", default=DEFAULT_LANG)
    args = parser.parse_args(argv)
    print(
        json.dumps(synthesize(args.text, args.out, args.voice, args.speed, args.lang))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
