import math
import wave
from array import array

import audio_dsp
import pytest


def test_sfx_synth_lengths_and_bounds():
    for name in (
        "pop",
        "thud",
        "chime",
        "confirm",
        "whoosh",
        "type_click",
        "error_buzz",
        "soft_chime",
    ):
        samples = audio_dsp.synth_sfx(name, 0.8)
        assert samples, name
        assert max(abs(s) for s in samples) <= 0.45, name
        assert len(samples) > 100
    assert len(audio_dsp.synth_sfx("confirm")) < int(0.6 * audio_dsp.RATE)
    assert len(audio_dsp.synth_sfx("chime")) < int(0.7 * audio_dsp.RATE)


def test_unknown_sfx_rejected():
    with pytest.raises(ValueError):
        audio_dsp.synth_sfx("kazoo")


def test_whoosh_deterministic():
    assert audio_dsp.synth_sfx("whoosh") == audio_dsp.synth_sfx("whoosh")


def test_pad_is_quiet():
    peak = max(
        abs(audio_dsp.pad_at(t / 100.0)) for t in range(630)
    )  # ~5.7s at 110 Hz root
    assert peak < 0.1


def test_duck_envelope_range_and_shape():
    vo = [
        math.sin(2 * math.pi * 220 * i / audio_dsp.RATE)
        * (0.8 if i > audio_dsp.RATE / 2 else 0.0)
        for i in range(audio_dsp.RATE)
    ]
    env = audio_dsp.duck_envelope(vo)
    assert len(env) == len(vo)
    assert max(env) <= 1.0 and min(env) >= 0.0
    # first half should sit well below the second half (signal starts silent)
    first = sum(env[: audio_dsp.RATE // 4]) / (audio_dsp.RATE // 4)
    second = sum(env[3 * audio_dsp.RATE // 4 :]) / (audio_dsp.RATE // 4)
    assert second > first * 2


def test_mix_timeline_bounds_and_ducking(tmp_path):
    wav = tmp_path / "vo.wav"
    vo_samples = array(
        "h",
        [
            int(0.5 * math.sin(2 * math.pi * 180 * i / audio_dsp.RATE) * 32767)
            for i in range(audio_dsp.RATE)
        ],
    )
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio_dsp.RATE)
        w.writeframes(vo_samples.tobytes())

    mixed = audio_dsp.mix_timeline(1.0, wav, pad=True, sfx_events=[(0.1, "pop", 0.9)])
    assert len(mixed) == audio_dsp.RATE * 2  # stereo interleaved
    peak = max(abs(s) for s in mixed)
    assert peak <= int(0.891 * audio_dsp.FULL_SCALE) + 1


def test_write_wav_stereo_roundtrip(tmp_path):
    out = tmp_path / "master.wav"
    interleaved = array("h", [0, 0, 1000, -1000, -2000, 2000] * 100)
    audio_dsp.write_wav_stereo(out, interleaved)
    with wave.open(str(out), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (
            2,
            2,
            audio_dsp.RATE,
        )


def test_build_master_wav_multi_scene(tmp_path):
    scenes = [
        {
            "start_sec": 0.0,
            "duration_sec": 0.5,
            "sfx_events": [{"t_sec": 0.1, "sfx": "chime", "intensity": 0.7}],
        },
        {
            "start_sec": 0.5,
            "duration_sec": 0.5,
            "sfx_events": [{"t_sec": 0.1, "sfx": "pop", "intensity": 0.7}],
        },
    ]
    out = tmp_path / "master.wav"
    total = audio_dsp.build_master_wav(scenes, out, pad=True)
    assert total == pytest.approx(1.0, abs=0.01)
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() == pytest.approx(audio_dsp.RATE, rel=0.01)


def test_build_master_wav_tolerates_short_vo_stem(tmp_path):
    """VO stems trimmed shorter than duration_sec must still mix (--trim-silence edge)."""
    wav = tmp_path / "vo.wav"
    vo_samples = array(
        "h",
        [
            int(0.5 * math.sin(2 * math.pi * 180 * i / audio_dsp.RATE) * 32767)
            for i in range(
                audio_dsp.RATE // 5
            )  # 0.2 s, much shorter than the 1 s scene
        ],
    )
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio_dsp.RATE)
        w.writeframes(vo_samples.tobytes())

    scenes = [
        {
            "start_sec": 0.0,
            "duration_sec": 1.0,
            "vo_wav": str(wav),
            "sfx_events": [{"t_sec": 0.5, "sfx": "pop", "intensity": 0.5}],
        }
    ]
    out = tmp_path / "master.wav"
    total = audio_dsp.build_master_wav(scenes, out, pad=True)
    assert total == pytest.approx(1.0, abs=0.01)


def test_mix_timeline_and_build_master_default_to_no_pad(tmp_path):
    mixed = audio_dsp.mix_timeline(0.2)
    assert all(s == 0 for s in mixed)

    out = tmp_path / "silent_default.wav"
    audio_dsp.build_master_wav([{"start_sec": 0.0, "duration_sec": 0.2}], out)
    with wave.open(str(out), "rb") as w:
        frames = array("h", w.readframes(w.getnframes()))
    assert all(s == 0 for s in frames)


def test_synth_room_tone_deterministic_and_ducks(tmp_path):
    l1, r1 = audio_dsp.synth_room_tone(2000, level=0.035)
    l2, r2 = audio_dsp.synth_room_tone(2000, level=0.035)
    assert l1 == l2 and r1 == r2
    assert max(abs(x) for x in l1) > 0.0
    assert max(abs(x) for x in l1) < 0.15

    mixed = audio_dsp.mix_timeline(
        0.25, pad=True, pad_style="room_tone", pad_level=0.035
    )
    assert max(abs(s) for s in mixed) > 0


def test_build_master_wav_with_music_wav_loops_and_ducks(tmp_path):
    music = tmp_path / "music.wav"
    m_samples = array(
        "h",
        [
            int(0.4 * math.sin(2 * math.pi * 220 * i / audio_dsp.RATE) * 32767)
            for i in range(audio_dsp.RATE // 4)
        ],
    )
    with wave.open(str(music), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio_dsp.RATE)
        w.writeframes(m_samples.tobytes())

    out = tmp_path / "with_music.wav"
    total = audio_dsp.build_master_wav(
        [{"start_sec": 0.0, "duration_sec": 0.6}],
        out,
        pad=False,
        music_wav=music,
        music_level=0.14,
    )
    assert total == pytest.approx(0.6, abs=0.01)
    with wave.open(str(out), "rb") as w:
        frames = array("h", w.readframes(w.getnframes()))
    assert max(abs(s) for s in frames[-audio_dsp.RATE // 5 :]) > 0


def test_build_master_wav_mutes_synth_sfx_and_tonal_pads_by_default(tmp_path):
    out = tmp_path / "muted_synth.wav"
    audio_dsp.build_master_wav(
        [
            {
                "start_sec": 0.0,
                "duration_sec": 0.5,
                "sfx_events": [
                    {"t_sec": 0.05, "sfx": "chime", "intensity": 1.0},
                    {"t_sec": 0.15, "sfx": "whoosh", "intensity": 1.0},
                    {"t_sec": 0.25, "sfx": "pop", "intensity": 1.0},
                ],
            }
        ],
        out,
        pad=True,
        pad_style="drone",
    )
    with wave.open(str(out), "rb") as w:
        frames = array("h", w.readframes(w.getnframes()))
    assert all(s == 0 for s in frames)


def test_build_master_wav_mixes_real_sfx_wav(tmp_path):
    sfx_wav = tmp_path / "real_hit.wav"
    hit_samples = array(
        "h",
        [int(0.5 * 32767) for _ in range(audio_dsp.RATE // 20)],
    )
    with wave.open(str(sfx_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio_dsp.RATE)
        w.writeframes(hit_samples.tobytes())

    out = tmp_path / "with_real_sfx.wav"
    audio_dsp.build_master_wav(
        [
            {
                "start_sec": 0.0,
                "duration_sec": 0.4,
                "sfx_events": [
                    {"t_sec": 0.1, "sfx": "pop", "wav": str(sfx_wav), "intensity": 0.8}
                ],
            }
        ],
        out,
    )
    with wave.open(str(out), "rb") as w:
        frames = array("h", w.readframes(w.getnframes()))
    assert max(abs(s) for s in frames) > 0
