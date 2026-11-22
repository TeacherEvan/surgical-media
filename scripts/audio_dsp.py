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
import os
import random
import tempfile
import wave
from array import array
from functools import lru_cache
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
        # Short damped low-mid bubble/wood pop (240 -> 115 Hz)
        n = int(0.065 * rate)
        out_pop: list[float] = []
        phase = 0.0
        for i in range(n):
            t = i / rate
            freq = 115.0 + 125.0 * math.exp(-38.0 * t)
            phase += 2.0 * math.pi * freq / rate
            att = 1.0 - math.exp(-t / 0.003)
            out_pop.append(
                math.sin(phase) * _env_decay(t, 55.0) * att * 0.28 * intensity
            )
        return out_pop
    if name == "thud":
        # Soft low percussive transition hit (115 -> 46 Hz)
        n = int(0.11 * rate)
        out_thud: list[float] = []
        phase = 0.0
        for i in range(n):
            t = i / rate
            freq = 46.0 + 69.0 * math.exp(-26.0 * t)
            phase += 2.0 * math.pi * freq / rate
            att = 1.0 - math.exp(-t / 0.003)
            out_thud.append(
                math.sin(phase) * _env_decay(t, 32.0) * att * 0.34 * intensity
            )
        return out_thud
    if name == "chime":  # Short warm damped single-bell tap (440 Hz + soft octave)
        n = int(0.45 * rate)
        out_chime: list[float] = []
        for i in range(n):
            t = i / rate
            att = 1.0 - math.exp(-t / 0.008)
            val = math.sin(2.0 * math.pi * 440.0 * t) * _env_decay(
                t, 7.5
            ) + 0.18 * math.sin(2.0 * math.pi * 880.0 * t) * _env_decay(t, 11.0)
            out_chime.append(val * att * 0.22 * intensity)
        return out_chime
    if name == "confirm":  # Two short gentle damped taps (440 -> 523.25 Hz)
        n1 = int(0.16 * rate)
        n2 = int(0.22 * rate)
        gap = int(0.08 * rate)
        tap1 = [
            math.sin(2.0 * math.pi * 440.0 * (i / rate))
            * _env_decay(i / rate, 12.0)
            * (1.0 - math.exp(-(i / rate) / 0.006))
            * 0.22
            * intensity
            for i in range(n1)
        ]
        tap2 = [
            math.sin(2.0 * math.pi * 523.25 * (i / rate))
            * _env_decay(i / rate, 10.0)
            * (1.0 - math.exp(-(i / rate) / 0.006))
            * 0.20
            * intensity
            for i in range(n2)
        ]
        return tap1 + [0.0] * gap + tap2
    if name == "whoosh":
        n = int(0.55 * rate)
        rng = random.Random(20261118)
        out = []
        low = 0.0
        for i in range(n):
            x = rng.uniform(-1.0, 1.0)
            sweep = (i / n) ** 1.6
            low += (0.02 + 0.35 * sweep) * (x - low)  # one-pole lowpass, opening up
            env = math.sin(math.pi * min(1.0, i / n)) ** 2
            out.append(low * env * 0.36 * intensity)
        return out
    if name == "type_click":
        # Band-limited tactile noise click (no harsh square-wave tone)
        n = int(0.020 * rate)
        rng = random.Random(20261121)
        out_tc: list[float] = []
        prev_x = 0.0
        lp = 0.0
        for i in range(n):
            t = i / rate
            x = rng.uniform(-1.0, 1.0)
            hp = x - prev_x
            prev_x = x
            lp += 0.38 * (hp - lp)
            out_tc.append(lp * _env_decay(t, 220.0) * 0.26 * intensity)
        return out_tc
    if name == "error_buzz":
        # Short low muted double-thud (no harsh sawtooth buzzer)
        n = int(0.22 * rate)
        out_eb: list[float] = []
        pulse2_start = 0.08
        for i in range(n):
            t = i / rate
            p1 = (
                (
                    math.sin(2.0 * math.pi * 110.0 * t)
                    + 0.35 * math.sin(2.0 * math.pi * 165.0 * t)
                )
                * _env_decay(t, 26.0)
                * (1.0 - math.exp(-t / 0.003))
            )
            p2 = 0.0
            if t >= pulse2_start:
                t2 = t - pulse2_start
                p2 = (
                    (
                        math.sin(2.0 * math.pi * 110.0 * t2)
                        + 0.35 * math.sin(2.0 * math.pi * 165.0 * t2)
                    )
                    * _env_decay(t2, 26.0)
                    * (1.0 - math.exp(-t2 / 0.003))
                )
            out_eb.append((p1 + p2) * 0.22 * intensity)
        return out_eb
    if name == "soft_chime":  # Short warm single-note bell (329.63 Hz + soft octave)
        n = int(0.55 * rate)
        out_sc: list[float] = []
        for i in range(n):
            t = i / rate
            attack = 1.0 - math.exp(-t / 0.012)
            val = math.sin(2.0 * math.pi * 329.63 * t) * _env_decay(
                t, 6.0
            ) + 0.15 * math.sin(2.0 * math.pi * 659.25 * t) * _env_decay(t, 9.0)
            out_sc.append(val * attack * 0.18 * intensity)
        return out_sc
    raise ValueError(
        f"unknown sfx {name!r}; valid: pop, thud, chime, confirm, whoosh, type_click, error_buzz, soft_chime"
    )


def synth_room_tone(
    n: int, level: float = 0.03, rate: int = RATE
) -> tuple[list[float], list[float]]:
    """Pitchless warm studio air (two-pole 400 Hz low-pass noise, stereo)."""
    if n <= 0 or level <= 0.0:
        return [0.0] * max(0, n), [0.0] * max(0, n)
    rng = random.Random(20261122)
    alpha = 1.0 - math.exp(-2.0 * math.pi * 400.0 / rate)
    l1 = l2 = 0.0
    r1 = r2 = 0.0
    left = [0.0] * n
    right = [0.0] * n
    sq_sum = 0.0
    for i in range(n):
        c = rng.uniform(-1.0, 1.0)
        s = rng.uniform(-1.0, 1.0)
        wl = 0.85 * c + 0.15 * s
        wr = 0.85 * c - 0.15 * s
        l1 += alpha * (wl - l1)
        l2 += alpha * (l1 - l2)
        r1 += alpha * (wr - r1)
        r2 += alpha * (r1 - r2)
        left[i] = l2
        right[i] = r2
        sq_sum += 0.5 * (l2 * l2 + r2 * r2)
    rms = math.sqrt(sq_sum / max(1, n)) or 1.0
    gain = (0.35 * level) / rms
    cap = 0.91 * level
    fade = min(n // 4, int(0.08 * rate))
    for i in range(n):
        env = 1.0
        if fade > 0:
            if i < fade:
                env = i / fade
            elif i >= n - fade:
                env = (n - 1 - i) / fade
        g = gain * env
        lv = left[i] * g
        rv = right[i] * g
        if cap > 0.0:
            lv = math.tanh(lv / cap) * cap
            rv = math.tanh(rv / cap) * cap
        left[i] = lv
        right[i] = rv
    return left, right


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
    if not mono:
        return []
    if rate == target_rate:
        return mono
    # linear interpolation resample (VO is already 48 kHz from ffmpeg; this path is a safety net)
    ratio = rate / target_rate
    out_len = int(len(mono) / ratio)
    out: list[float] = []
    last = len(mono) - 1
    for i in range(out_len):
        pos = i * ratio
        lo = int(pos)
        if lo >= last:
            out.append(mono[last])
        else:
            frac = pos - lo
            out.append(mono[lo] + frac * (mono[lo + 1] - mono[lo]))
    return out


def read_wav_stereo(
    path: str | Path, target_rate: int = RATE
) -> tuple[list[float], list[float]]:
    """Decode a PCM wav to stereo (left, right) floats in [-1, 1], resampling if needed."""
    with wave.open(str(path), "rb") as w:
        channels, sampwidth, rate, frames = (
            w.getnchannels(),
            w.getsampwidth(),
            w.getframerate(),
            w.getnframes(),
        )
        raw = w.readframes(frames)
    if frames == 0:
        return [], []
    if sampwidth == 2:
        samples = array("h", raw)
        scale = 1.0 / FULL_SCALE
        left = [samples[i] * scale for i in range(0, len(samples), channels)]
        right = (
            [samples[i + 1] * scale for i in range(0, len(samples), channels)]
            if channels >= 2
            else list(left)
        )
    elif sampwidth == 1:
        left = [((raw[i] - 128) / 128.0) for i in range(0, len(raw), channels)]
        right = (
            [((raw[i + 1] - 128) / 128.0) for i in range(0, len(raw), channels)]
            if channels >= 2
            else list(left)
        )
    elif sampwidth == 4:
        samples_i = array("i", raw)
        scale = 1.0 / 2147483648.0
        left = [samples_i[i] * scale for i in range(0, len(samples_i), channels)]
        right = (
            [samples_i[i + 1] * scale for i in range(0, len(samples_i), channels)]
            if channels >= 2
            else list(left)
        )
    else:
        raise ValueError(f"unsupported sample width {sampwidth} in {path}")
    if not left:
        return [], []
    if rate == target_rate:
        return left, right
    ratio = rate / target_rate
    out_len = int(len(left) / ratio)
    last = len(left) - 1
    out_l: list[float] = []
    out_r: list[float] = []
    for i in range(out_len):
        pos = i * ratio
        lo = int(pos)
        if lo >= last:
            out_l.append(left[last])
            out_r.append(right[last])
        else:
            frac = pos - lo
            out_l.append(left[lo] + frac * (left[lo + 1] - left[lo]))
            out_r.append(right[lo] + frac * (right[lo + 1] - right[lo]))
    return out_l, out_r


def measure_duration(path: str | Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def write_wav_stereo(path: str | Path, interleaved: array[int]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as fh:
        tmp_path = Path(fh.name)
    try:
        with wave.open(str(tmp_path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(interleaved.tobytes())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def _cached_sfx(name: str, intensity_q: float, rate: int) -> tuple[float, ...]:
    return tuple(synth_sfx(name, intensity_q, rate))


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
    pad: bool = False,
    pad_level: float = 0.03,
    duck_depth: float = 0.72,
    pad_style: str = "room_tone",
    music_wav: str | Path | None = None,
    music_level: float = 0.14,
    sfx_events: list[tuple[float, str, float]] | None = None,
    sample_rate: int = RATE,
) -> array[int]:
    """Render the full 48 kHz stereo master for one video or scene."""
    if sample_rate != RATE:
        raise ValueError(f"mix_timeline works at {RATE} Hz; got {sample_rate}")
    n = round(duration_sec * RATE)
    vo = read_wav_mono(vo_path, RATE) if vo_path else []
    ml: list[float] = []
    mr: list[float] = []
    if music_wav and Path(music_wav).is_file():
        ml, mr = read_wav_stereo(music_wav, RATE)
    has_music = bool(ml)
    env = duck_envelope(vo) if (vo and (pad or has_music)) else [0.0] * n
    if len(env) < n:
        tail_start = env[-1] if env else 0.0
        tail_n = n - len(env)
        release_n = max(1, int(0.45 * RATE))
        env = env + [tail_start * max(0.0, 1.0 - k / release_n) for k in range(tail_n)]

    rt_l: list[float] = []
    rt_r: list[float] = []
    if pad and pad_style == "room_tone":
        rt_l, rt_r = synth_room_tone(n, pad_level, RATE)

    left = [0.0] * n
    right = [0.0] * n
    peak = 0.0
    m_len = len(ml)

    for i in range(n):
        t = i / RATE
        lv_s = 0.0
        rv_s = 0.0
        if vo and i < len(vo):
            v_s = vo[i] * 0.90
            lv_s += v_s
            rv_s += v_s
        gain = 1.0 - duck_depth * env[i]
        if pad:
            if pad_style == "room_tone":
                lv_s += rt_l[i] * gain
                rv_s += rt_r[i] * gain
            elif pad_style == "pastel_harp":
                pl, pr = pastel_harp_stereo_at(t, duration_sec, pad_level)
                lv_s += pl * gain
                rv_s += pr * gain
            else:
                p_s = pad_at(t, pad_level) * gain
                lv_s += p_s
                rv_s += p_s
        if has_music:
            lv_s += ml[i % m_len] * music_level * gain
            rv_s += mr[i % m_len] * music_level * gain
        left[i] = lv_s
        right[i] = rv_s
        a = max(abs(lv_s), abs(rv_s))
        peak = max(peak, a)

    for t_sec, name, intensity in sfx_events or []:
        if name == "trauma":  # camera-only event, no audio component
            continue
        sfx = _cached_sfx(name, round(float(intensity), 3), RATE)
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
    pad: bool = False,
    pad_level: float = 0.03,
    duck_depth: float = 0.72,
    pad_style: str = "room_tone",
    music_wav: str | Path | None = None,
    music_level: float = 0.14,
    allow_synth_sfx: bool = False,
    allow_synth_pad: bool = False,
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
    vo_mix = [0.0] * n
    any_vo = False
    for sc in scenes:
        start = max(0, int(float(sc.get("start_sec", 0.0)) * RATE))
        vo = read_wav_mono(sc["vo_wav"], RATE) if sc.get("vo_wav") else []
        if vo:
            any_vo = True
            limit = min(len(vo), max(0, n - start))
            for j in range(limit):
                vo_mix[start + j] += vo[j]

    ml: list[float] = []
    mr: list[float] = []
    if music_wav and Path(music_wav).is_file():
        ml, mr = read_wav_stereo(music_wav, RATE)
    has_music = bool(ml)
    m_len = len(ml)

    rt_l: list[float] = []
    rt_r: list[float] = []
    if pad and pad_style == "room_tone":
        rt_l, rt_r = synth_room_tone(n, pad_level, RATE)

    env = duck_envelope(vo_mix) if (any_vo and (pad or has_music)) else [0.0] * n
    left = [0.0] * n
    right = [0.0] * n
    peak = 0.0

    for i in range(n):
        v_s = vo_mix[i] * 0.90
        lv_s = v_s
        rv_s = v_s
        gain = 1.0 - duck_depth * env[i]
        if pad:
            t_now = i / RATE
            if pad_style == "room_tone":
                lv_s += rt_l[i] * gain
                rv_s += rt_r[i] * gain
            elif allow_synth_pad and pad_style == "pastel_harp":
                pl, pr = pastel_harp_stereo_at(t_now, total, pad_level)
                lv_s += pl * gain
                rv_s += pr * gain
            elif allow_synth_pad:
                p_s = pad_at(t_now, pad_level) * gain
                lv_s += p_s
                rv_s += p_s
        if has_music:
            lv_s += ml[i % m_len] * music_level * gain
            rv_s += mr[i % m_len] * music_level * gain
        left[i] = lv_s
        right[i] = rv_s
        a = max(abs(lv_s), abs(rv_s))
        peak = max(peak, a)

    for sc in scenes:
        start = int(float(sc.get("start_sec", 0.0)) * RATE)
        for ev in sc.get("sfx_events", []):
            name = ev.get("sfx")
            if name == "trauma":
                continue
            intensity = min(1.0, max(0.05, float(ev.get("intensity", 1.0))))
            offset = start + int(float(ev["t_sec"]) * RATE)
            wav_src = ev.get("wav")
            if isinstance(wav_src, str) and wav_src.strip() and Path(wav_src).is_file():
                sl, sr = read_wav_stereo(wav_src, RATE)
                for j in range(len(sl)):
                    idx = offset + j
                    if idx < 0:
                        continue
                    if idx >= n:
                        break
                    lv = left[idx] + sl[j] * intensity
                    rv = right[idx] + sr[j] * intensity
                    left[idx] = lv
                    right[idx] = rv
                    peak = max(peak, abs(lv), abs(rv))
            elif allow_synth_sfx and name:
                sfx = _cached_sfx(name, round(intensity, 3), RATE)
                for j, s in enumerate(sfx):
                    idx = offset + j
                    if idx < 0:
                        continue
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
            "thud",
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
