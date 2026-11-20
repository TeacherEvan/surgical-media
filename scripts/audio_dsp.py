#!/usr/bin/env python3
"""audio_dsp.py — procedural SFX synthesis, ambient pad, sidechain ducking.

Pure stdlib (wave/math/array) — no numpy required. All synthesis is
deterministic (seeded noise for whooshes), so renders are bit-reproducible.

Pipeline per video::

    VO stems + pad + SFX events
      -> envelope follower -> gain computer -> ducked pad
      -> peak limiter (-1 dBFS ceiling)
      -> 48 kHz stereo int16 wav
      -> ffmpeg loudnorm (-14 LUFS, TP -1.5) on mux

The limiter is a -1 dBFS peak ceiling: unity gain below it, a single hard
gain reduction above it. Never clips, never colours the signal.
"""

from __future__ import annotations

import argparse
import math
import random
import wave
from array import array
from pathlib import Path
from typing import Any

RATE = 48000
FULL_SCALE = 32767
PHI = 1.618033988749895

# ---------------------------------------------------------------------------
# SFX synthesis (mono float, -1..1)
# ---------------------------------------------------------------------------


def _env_decay(t: float, rate: float) -> float:
    return math.exp(-rate * t)


def synth_sfx(name: str, intensity: float = 1.0, rate: int = RATE) -> list[float]:
    intensity = min(1.0, max(0.05, float(intensity)))
    if name == "pop":
        n = int(0.10 * rate)
        return [
            (
                math.sin(2 * math.pi * 700 * (i / rate)) * _env_decay(i / rate, 45)
                + 0.35
                * math.sin(2 * math.pi * 1420 * (i / rate))
                * _env_decay(i / rate, 60)
            )
            * 0.8
            * intensity
            for i in range(n)
        ]
    if name == "chime":  # 528 Hz with golden-ratio partials
        n = int(1.4 * rate)
        partials = ((528.0, 1.0, 2.1), (528.0 * PHI, 0.5, 2.7), (528.0 * 2, 0.22, 3.4))
        return [
            sum(
                a * math.sin(2 * math.pi * f * (i / rate)) * _env_decay(i / rate, d)
                for f, a, d in partials
            )
            * 0.5
            * intensity
            for i in range(n)
        ]
    if name == "confirm":  # two-note confirmation: 528 → 528*φ
        note1 = synth_sfx("chime", intensity * 0.8, rate)
        note2 = synth_sfx("chime", intensity * 0.6, rate)
        gap = int(0.18 * rate)
        out = note1 + [0.0] * gap + note2
        return out
    if name == "whoosh":
        n = int(0.6 * rate)
        rng = random.Random(20261118)
        out = []
        low = 0.0
        for i in range(n):
            x = rng.uniform(-1.0, 1.0)
            sweep = (i / n) ** 1.6
            low += (0.02 + 0.35 * sweep) * (x - low)  # one-pole lowpass, opening up
            env = math.sin(math.pi * min(1.0, i / n)) ** 2
            out.append(low * env * 0.9 * intensity)
        return out
    if name == "type_click":
        n = int(0.05 * rate)
        return [
            math.copysign(1.0, math.sin(2 * math.pi * 2300 * (i / rate)))
            * _env_decay(i / rate, 95)
            * 0.5
            * intensity
            for i in range(n)
        ]
    if name == "error_buzz":
        n = int(0.45 * rate)
        return [
            (
                sum(
                    (1.0 / k) * math.sin(2 * math.pi * 110 * k * (i / rate))
                    for k in range(1, 8)
                )
                / 1.6
                * _env_decay(i / rate, 6.0)
                * (1.0 + 0.15 * math.sin(2 * math.pi * 27 * (i / rate)))
            )
            * 0.8
            * intensity
            for i in range(n)
        ]
    if name == "soft_chime":  # warm acoustic harp / celesta pentatonic bloom
        n = int(2.2 * rate)
        sc_partials = (
            (293.66, 0.55, 1.35),  # D4
            (440.00, 0.45, 1.55),  # A4
            (587.33, 0.35, 1.85),  # D5
            (739.99, 0.24, 2.20),  # F#5
            (1174.66, 0.10, 3.00),  # D6 shimmer
        )
        out_sc: list[float] = []
        for i in range(n):
            t = i / rate
            attack = 1.0 - math.exp(-t / 0.025)
            val = sum(
                a * math.sin(2 * math.pi * f * t) * _env_decay(t, d)
                for f, a, d in sc_partials
            )
            out_sc.append(val * attack * 0.36 * intensity)
        return out_sc
    raise ValueError(
        f"unknown sfx {name!r}; valid: pop, chime, confirm, whoosh, type_click, error_buzz, soft_chime"
    )


def pad_at(t_sec: float, level: float = 0.055) -> float:
    """Just-intonation drone: 110 Hz root + 3:2 fifth + detuned octave."""
    return level * (
        1.00 * math.sin(2 * math.pi * 110.0 * t_sec)
        + 0.55 * math.sin(2 * math.pi * 165.0 * t_sec + 0.6)  # 3:2 fifth
        + 0.18 * math.sin(2 * math.pi * 220.7 * t_sec + 1.2)  # detuned octave beats
    )


# D-major / B-minor lyrical progression for pastel_harp ambient score:
# Dmaj9 -> Gmaj9 -> Bm7 -> A6add9 (4.0 s per bar, 16 s seamless cycle)
_PASTEL_CHORDS: tuple[tuple[float, float, float, float, float], ...] = (
    (146.83, 220.00, 293.66, 369.99, 329.63),  # Dmaj9: D3 A3 D4 F#4 E4
    (98.00, 196.00, 246.94, 293.66, 369.99),  # Gmaj9: G2 G3 B3 D4 F#4
    (123.47, 185.00, 220.00, 293.66, 369.99),  # Bm7:   B2 F#3 A3 D4 F#4
    (110.00, 164.81, 220.00, 277.18, 329.63),  # A6:    A2 E3 A3 C#4 E4
)
_PASTEL_ARP_SEQ: tuple[int, ...] = (0, 2, 3, 4, 3, 2, 1, 3)


def pastel_harp_stereo_at(
    t_sec: float, total_sec: float, level: float = 0.085
) -> tuple[float, float]:
    """Warm stereo ambient strings + plucked acoustic harp arpeggio (D major 9)."""
    bar_dur = 4.0
    pos = t_sec / bar_dur
    bar_idx = int(pos) % len(_PASTEL_CHORDS)
    next_idx = (bar_idx + 1) % len(_PASTEL_CHORDS)
    bar_frac = pos - math.floor(pos)
    # smooth 0.6s chord crossfade at bar boundary so harmony glides silkily
    xfade = max(0.0, min(1.0, (bar_frac - 0.85) / 0.15))
    c_cur = _PASTEL_CHORDS[bar_idx]
    c_nxt = _PASTEL_CHORDS[next_idx]

    breath = 0.84 + 0.16 * math.sin(2.0 * math.pi * t_sec / 6.4)
    # Edge fade-in (2.0s) and fade-out (2.8s)
    fade_in = min(1.0, t_sec / 2.0) if t_sec < 2.0 else 1.0
    rem = max(0.0, total_sec - t_sec)
    fade_out = min(1.0, rem / 2.8) if rem < 2.8 else 1.0
    env_global = fade_in * fade_out * breath

    # Warm lush stereo string bed (root + 5th + 3rd/9th, soft stereo chorus detune)
    pad_l = 0.0
    pad_r = 0.0
    weights = (0.46, 0.24, 0.22, 0.18, 0.14)
    for k, w in enumerate(weights):
        f_cur = c_cur[k]
        f_nxt = c_nxt[k]
        if xfade <= 0.0:
            s_l = math.sin(2.0 * math.pi * (f_cur * 0.9992) * t_sec + k * 0.7)
            s_r = math.sin(2.0 * math.pi * (f_cur * 1.0008) * t_sec + k * 1.1)
        else:
            s_l = (1.0 - xfade) * math.sin(
                2.0 * math.pi * (f_cur * 0.9992) * t_sec + k * 0.7
            ) + xfade * math.sin(2.0 * math.pi * (f_nxt * 0.9992) * t_sec + k * 0.7)
            s_r = (1.0 - xfade) * math.sin(
                2.0 * math.pi * (f_cur * 1.0008) * t_sec + k * 1.1
            ) + xfade * math.sin(2.0 * math.pi * (f_nxt * 1.0008) * t_sec + k * 1.1)
        pad_l += w * s_l
        pad_r += w * s_r

    # Soft plucked acoustic harp notes every 0.5s with overlapping 2-note tail
    step_dur = 0.50
    step_idx = int(t_sec / step_dur)
    harp_l = 0.0
    harp_r = 0.0
    for back in (0, 1, 2):
        idx = step_idx - back
        if idx < 0:
            continue
        dt = t_sec - idx * step_dur
        if dt < 0.0 or dt > 1.65:
            continue
        note_bar = int((idx * step_dur) / bar_dur) % len(_PASTEL_CHORDS)
        chord = _PASTEL_CHORDS[note_bar]
        note_slot = _PASTEL_ARP_SEQ[idx % len(_PASTEL_ARP_SEQ)]
        freq = chord[note_slot] * (2.0 if (idx % 4 == 3) else 1.0)
        # Soft felt-harp envelope: smooth 14ms attack, warm exponential decay
        att = 1.0 - math.exp(-dt / 0.014)
        tone = (
            0.72 * math.sin(2.0 * math.pi * freq * dt) * math.exp(-2.1 * dt)
            + 0.24 * math.sin(2.0 * math.pi * freq * 2.0 * dt) * math.exp(-4.2 * dt)
            + 0.08 * math.sin(2.0 * math.pi * freq * 3.0 * dt) * math.exp(-7.0 * dt)
        ) * att
        # Subtle alternating stereo harp placement (-0.35..+0.35)
        pan = 0.5 + 0.30 * math.sin(idx * 1.15)
        harp_l += tone * (1.0 - pan) * 0.85
        harp_r += tone * pan * 0.85

    out_l = level * env_global * (0.58 * pad_l + 0.62 * harp_l)
    out_r = level * env_global * (0.58 * pad_r + 0.62 * harp_r)
    return out_l, out_r


# ---------------------------------------------------------------------------
# WAV helpers (16-bit PCM, any channel count)
# ---------------------------------------------------------------------------


def read_wav_mono(path: str | Path, target_rate: int = RATE) -> list[float]:
    """Decode a PCM wav to mono floats in [-1, 1], resampling linearly if needed."""
    with wave.open(str(path), "rb") as w:
        channels, sampwidth, rate, frames = (
            w.getnchannels(),
            w.getsampwidth(),
            w.getframerate(),
            w.getnframes(),
        )
        raw = w.readframes(frames)
    if sampwidth == 2:
        samples = array("h", raw)
        scale = 1.0 / FULL_SCALE
        mono = [
            sum(samples[i + c] for c in range(channels)) * scale / channels
            for i in range(0, len(samples), channels)
        ]
    elif sampwidth == 1:
        mono = [((b - 128) / 128.0) for b in raw]
        mono = [
            sum(mono[i + c] for c in range(channels)) / channels
            for i in range(0, len(mono), channels)
        ]
    elif sampwidth == 4:
        samples = array("i", raw)
        scale = 1.0 / 2147483648.0
        mono = [
            sum(samples[i + c] for c in range(channels)) * scale / channels
            for i in range(0, len(samples), channels)
        ]
    else:
        raise ValueError(f"unsupported sample width {sampwidth} in {path}")
    if rate == target_rate:
        return mono
    # linear resample (VO is already 48 kHz from ffmpeg; this path is a safety net)
    ratio = rate / target_rate
    out_len = int(len(mono) / ratio)
    return [mono[min(len(mono) - 1, int(i * ratio))] for i in range(out_len)]


def measure_duration(path: str | Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def write_wav_stereo(path: str | Path, interleaved: array[int]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(interleaved.tobytes())


# ---------------------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------------------


def duck_envelope(
    mono: list[float], attack: float = 0.004, release: float = 0.18
) -> list[float]:
    """Two-pass envelope follower: fast attack, slow release. Output in [0, 1]."""
    n = len(mono)
    if n == 0:
        return []
    a_att = math.exp(-1.0 / max(1.0, attack * RATE))
    a_rel = math.exp(-1.0 / max(1.0, release * RATE))
    env = [0.0] * n
    e = 0.0
    for i in range(n):
        x = abs(mono[i])
        coeff = a_att if x > e else a_rel
        e = coeff * e + (1.0 - coeff) * x
        env[i] = e
    peak = max(env) or 1.0
    return [min(1.0, v / peak) for v in env]


def mix_timeline(
    duration_sec: float,
    vo_path: str | Path | None = None,
    *,
    pad: bool = True,
    pad_level: float = 0.055,
    duck_depth: float = 0.72,
    pad_style: str = "drone",
    sfx_events: list[tuple[float, str, float]] | None = None,
    sample_rate: int = RATE,
) -> array[int]:
    """Render the full 48 kHz stereo master for one video or scene."""
    if sample_rate != RATE:
        raise ValueError(f"mix_timeline works at {RATE} Hz; got {sample_rate}")
    n = round(duration_sec * RATE)
    vo = read_wav_mono(vo_path, RATE) if vo_path else []
    env = duck_envelope(vo) if (vo and pad) else [0.0] * n

    left = [0.0] * n
    right = [0.0] * n
    peak = 0.0

    for i in range(n):
        t = i / RATE
        lv_s = 0.0
        rv_s = 0.0
        if vo and i < len(vo):
            v_s = vo[i] * 0.90
            lv_s += v_s
            rv_s += v_s
        if pad:
            gain = 1.0 - duck_depth * env[i] if i < len(env) else 1.0 - duck_depth
            if pad_style == "pastel_harp":
                pl, pr = pastel_harp_stereo_at(t, duration_sec, pad_level)
                lv_s += pl * gain
                rv_s += pr * gain
            else:
                p_s = pad_at(t, pad_level) * gain
                lv_s += p_s
                rv_s += p_s
        left[i] = lv_s
        right[i] = rv_s
        a = max(abs(lv_s), abs(rv_s))
        peak = max(peak, a)

    for t_sec, name, intensity in sfx_events or []:
        if name == "trauma":  # camera-only event, no audio component
            continue
        sfx = synth_sfx(name, intensity, RATE)
        offset = int(t_sec * RATE)
        for j, s in enumerate(sfx):
            idx = offset + j
            if idx >= n:
                break
            lv, rv = left[idx] + s, right[idx] + s
            left[idx] = lv
            right[idx] = rv
            a = max(abs(lv), abs(rv))
            peak = max(peak, a)
    gain = (0.891 / peak) if peak > 0.891 else 1.0

    interleaved = array("h")
    append = interleaved.append
    for i in range(n):
        lv = int(left[i] * gain * FULL_SCALE)
        rv = int(right[i] * gain * FULL_SCALE)
        append(max(-FULL_SCALE - 1, min(FULL_SCALE, lv)))
        append(max(-FULL_SCALE - 1, min(FULL_SCALE, rv)))
    return interleaved


def build_master_wav(
    scenes: list[dict[str, Any]],
    output_path: str | Path,
    *,
    pad: bool = True,
    pad_level: float = 0.055,
    duck_depth: float = 0.72,
    pad_style: str = "drone",
) -> float:
    """Mix every scene's VO stem + SFX into one continuous master wav.

    ``scenes`` are storyboard scene dicts with absolute ``start_sec`` /
    ``duration_sec`` and optional ``vo_wav`` + ``sfx_events``.
    Returns total duration in seconds.
    """
    total = 0.0
    for sc in scenes:
        total = max(total, float(sc.get("start_sec", 0.0)) + float(sc["duration_sec"]))

    n = round(total * RATE)
    left = [0.0] * n
    right = [0.0] * n

    peak = 0.0

    for sc in scenes:
        start = int(float(sc.get("start_sec", 0.0)) * RATE)
        dur_n = int(float(sc["duration_sec"]) * RATE)
        vo = read_wav_mono(sc["vo_wav"], RATE) if sc.get("vo_wav") else []
        # VO stems may be shorter than the scene (e.g. after --trim-silence or --pad-tail):
        # hold the last envelope value (0 once VO finishes so the music swells gently).
        env = duck_envelope(vo) if (vo and pad) else [0.0] * dur_n
        if len(env) < dur_n:
            tail_start = env[-1] if env else 0.0
            tail_n = dur_n - len(env)
            release_n = max(1, int(0.45 * RATE))
            tail = [tail_start * max(0.0, 1.0 - k / release_n) for k in range(tail_n)]
            env = env + tail

        for j in range(dur_n):
            i = start + j
            if i >= n:
                break
            lv_s = 0.0
            rv_s = 0.0
            if j < len(vo):
                v_s = vo[j] * 0.90
                lv_s += v_s
                rv_s += v_s
            if pad:
                gain = 1.0 - duck_depth * env[j]
                t_now = (start + j) / RATE
                if pad_style == "pastel_harp":
                    pl, pr = pastel_harp_stereo_at(t_now, total, pad_level)
                    lv_s += pl * gain
                    rv_s += pr * gain
                else:
                    p_s = pad_at(t_now, pad_level) * gain
                    lv_s += p_s
                    rv_s += p_s
            lv, rv = left[i] + lv_s, right[i] + rv_s
            left[i] = lv
            right[i] = rv
            a = max(abs(lv), abs(rv))
            peak = max(peak, a)

        for ev in sc.get("sfx_events", []):
            name = ev.get("sfx")
            if name == "trauma":
                continue
            sfx = synth_sfx(name, float(ev.get("intensity", 1.0)), RATE)
            offset = start + int(float(ev["t_sec"]) * RATE)
            for j, s in enumerate(sfx):
                idx = offset + j
                if idx >= n:
                    break
                lv, rv = left[idx] + s, right[idx] + s
                left[idx] = lv
                right[idx] = rv
                a = max(abs(lv), abs(rv))
                peak = max(peak, a)

    gain = (0.891 / peak) if peak > 0.891 else 1.0

    interleaved = array("h")
    append = interleaved.append
    for i in range(n):
        lv = int(left[i] * gain * FULL_SCALE)
        rv = int(right[i] * gain * FULL_SCALE)
        append(max(-FULL_SCALE - 1, min(FULL_SCALE, lv)))
        append(max(-FULL_SCALE - 1, min(FULL_SCALE, rv)))
    write_wav_stereo(output_path, interleaved)
    return total


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit or synthesize surgical-media audio stems."
    )
    parser.add_argument(
        "--probe", metavar="WAV", help="Print duration of a wav and exit."
    )
    parser.add_argument(
        "--sfx",
        choices=[
            "pop",
            "chime",
            "confirm",
            "whoosh",
            "type_click",
            "error_buzz",
            "soft_chime",
        ],
    )
    parser.add_argument("--out", metavar="WAV", help="Output path for --sfx render.")
    args = parser.parse_args()

    if args.probe:
        print(f"{measure_duration(args.probe):.3f}s")
        return 0
    if args.sfx:
        if not args.out:
            parser.error("--sfx requires --out")
        mono = synth_sfx(args.sfx)
        stereo = array("h")
        for s in mono:
            v = max(-FULL_SCALE - 1, min(FULL_SCALE, int(s * FULL_SCALE)))
            stereo.append(v)
            stereo.append(v)
        write_wav_stereo(args.out, stereo)
        print(f"wrote {args.out} ({len(mono) / RATE:.2f}s)")
        return 0
    parser.error("nothing to do: pass --probe or --sfx")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
