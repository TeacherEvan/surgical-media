# FFmpeg Encoding & Loudness Reference

Encode is a fixed contract. Deviating from it predictably breaks platform playback.

## The contract (enforced by `render_engine.py`)

| Stream | Setting | Why |
| :--- | :--- | :--- |
| Video codec | `libx264`, `-profile:v high`, `-level 4.2` | universal HW decode |
| Pixel format | `-pix_fmt yuv420p` | **non-negotiable** — yuv444p/RGBA fails silently on iOS, Safari, IG, TikTok |
| CRF / preset | crf `18` / `medium` (final) · crf `26` / `veryfast` (draft) | draft exists for iteration; final is the deliverable |
| Flags | `-movflags +faststart` | moov atom up front ⇒ instant first-frame on social platforms |
| Raw input | `-f rawvideo -pix_fmt rgb24 -s WxH -r FPS -i -` | zero temp files; RGB because Pillow emits RGB (no alpha after `final()`) |
| Audio codec | `aac`, `192k`, `48000` Hz stereo | platform sweet spot; 44.1 kHz adds nothing |
| Loudness | `loudnorm=I=-14:TP=-1.5:LRA=11` on `-af` at mux time | −14 LUFS integrated / −1.5 dBTP is the YT/Spotify/IG consensus |
| A/V length | `-shortest` | trims the tail pad past the last video frame |

Changing `-pix_fmt` without changing `frame.tobytes()` corrupts every frame (byte-stride mismatch) — that is why `rgb24` and the RGB export path in `SupersampledCanvas.final()` are welded together in review.

## FPS

30 fps default. 60 only when the motion demands it (fast packet cascades, φ-spiral locks) — it doubles rasterization cost. 24/25/50 are legal in the schema; renderer handles them.

## Loudness reality

| Platform | Target | Our output |
| :--- | :--- | :--- |
| YouTube / Shorts | −14 LUFS integrated | −14 (loudnorm pass) |
| Instagram / TikTok / Reels | −14…−16 LUFS | −14 (within ±2; both accept) |
| Spotify Video | −14 LUFS, ≤ −1.5 dBTP | −14 / −1.5 TP ✓ |
| Apple Podcasts | −16 LUFS | −14 source; Apple normalizes down cleanly |

True-peak vs sample-peak: `loudnorm` handles inter-sample peaks; the pre-mux mix already sits under −1 dBFS (limiter in `audio_dsp.build_master_wav`), so loudnorm only trims integrated level, never pumps.

## Sidechain ducking (VO under pad)

`audio_dsp` follows the concept spec: one-pole rectified envelope follower (fast attack ~4 ms, release ~180 ms), pad attenuated by `duck_depth` (default 0.72 ≈ −11 dB) during active speech, restored in gaps. Pad = 110 Hz root + 3:2 just fifth + detuned octave at −25 dBFS-ish (`pad_level 0.055`).

## QC gate (`verify_output.py`)

Exit 1 unless **all** hold: video stream present · audio stream present · `codec_name == h264` · `pix_fmt == yuv420p` · width/height match · `r_frame_rate` matches · `aac` @ 48 kHz · `|duration − storyboard.total| ≤ 150 ms`. Duration drift > 150 ms almost always means VO stems were re-trimmed after storyboard generation — re-run `tts_align.py`, never hand-edit `duration_sec` to match.

## Useful probes

```bash
ffprobe -v error -print_format json -show_format -show_streams out.mp4
ffmpeg -i out.mp4 -af ebur128 -f null -          # integrated LUFS readout
ffmpeg -i out.mp4 -map 0:v -c copy -f null -     # hardware-decode sanity
```

## Hardware acceleration

Not wired in by default (portability). If needed, swap `libx264` for `h264_nvenc`/`h264_videotoolbox` **and keep `-pix_fmt yuv420p`** — never `h264_nvenc` defaults, which can emit yuv444p.
