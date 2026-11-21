# Platform specs, safe zones & licensing compliance

**Baseline verified 2026-11-21. This is a snapshot, not a permanent truth.** Before every
production run, do the live refresh at the bottom of this file and update the date here if
anything changed. The orchestrator in `SKILL.md` Step 2 requires that check.

## 1. Platform limits

| Platform / format | Ratio & resolution | Duration cap | Max upload | FPS / codec |
| :--- | :--- | :--- | :--- | :--- |
| YouTube Long-form | 16:9, 1920x1080 → 3840x2160 (8K accepted) | 15 min unverified / 12 h verified | 256 GB | 24–60 fps, H.264/HEVC + AAC-LC |
| YouTube Shorts | 9:16, 1080x1920 | 3 min | 256 GB (account cap) | 30–60 fps, H.264 MP4 |
| TikTok | 9:16, 1080x1920 | 10 min in-app / 60 min web | ~72 MB Android / ~287 MB iOS / 4 GB web | 23–60 fps, H.264 MP4/MOV |
| Facebook Reels | 9:16, 1080x1920 (up to 1440x2560) | 90 s via most schedulers | 4 GB | 30 fps, H.264 MP4/MOV |
| Facebook Feed | 4:5 1440x1800 or 16:9 1920x1080 | ~240 min | 4 GB standard / 10 GB ads | ≤30 fps, H.264 MP4/MOV |

This renderer emits `1920x1080@30/60`, `1080x1920@30/60`, `1080x1080@30`, or
`1440x1800@30` (4:5). Longer exports must stay inside the table's caps or be split.

## 2. Encoding & audio targets (baked into `render_engine.py`)

- Video: `libx264`, `-profile:v high -level 4.2 -pix_fmt yuv420p -movflags +faststart`,
  `-colorspace bt709 -color_primaries bt709 -color_trc bt709`, CFR at the board's `format.fps`.
- Bitrate: 8–12 Mbps for 1080p16:9, 15–20 Mbps for high-motion 9:16 (survives platform
  re-compression), 35–45 Mbps for 4K. `-crf 18` final / `-crf 26` demo.
- Audio: AAC-LC 48 kHz stereo, 192 kbps shipped, integrated −14 LUFS ±1, true peak ≤ −1.0 dBTP.
  The encoder measures the master, then applies two-pass `loudnorm` with a gentle
  `acompressor` (crest-factor control) and a −1 dBFS `alimiter`; this keeps the result
  near −14 LUFS / ≤ −1 dBTP across short and long boards. Verified by gate 12.
- Music under narration: duck −18 to −24 dB (this repo's `audio_dsp.py` sidechains
  −12 dB by default; go deeper for 9:16 voice-led cuts).

## 3. 9:16 safe zones — two masks, not one

Platform UI coverage differs by placement. Build against the **organic** box and audit
against the **strict** box. Coordinates are for 1080x1920; scale ×2/3 for 720x1280 and
×4/3 for 1440x2560.

| Mask | Top | Bottom | Left | Right | Safe rectangle |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Organic cross-app (TikTok + Reels + Shorts) | 180 px | 380 px (captions ≥400 px up) | 60 px | 150 px | x=60..930, y=180..1540 → 870×1360 |
| Strict worst-case / boosted / ad-safe | 288 px (15%) | 672 px (35%) | 65 px (6%) | 192 px (18%) | x=65..888, y=288..1248 → 823×960 |

- Facebook/IG Reels add right-side buttons at x=920..1020, y=1130..1870 — already inside
  the strict right band.
- This repo's historical default (`canvas.layout_zones`) is `(84, 220) → (w-150, h-440)`,
  i.e. x=84..930, y=220..1480 on 1080x1920. It fits **organic** but breaches the strict
  top band by 68 px and the strict bottom by 292 px. For boosted/ad-safe or text-critical
  work, override with the strict rectangle and let `qc_gate.py` draw both masks.
- Put captions, faces, CTAs, and subtle credits inside the intersection. Never anchor a
  credit to the raw frame bottom; use the `image` element's `attribution_y` or the harvester's
  safe-zone badge.

## 4. Copyright, originality & AI disclosure (verify live — these moved in 2026)

- **Shorts + Content ID:** Since **2026-09-24**, new Shorts over 1 minute with an active
  claim are no longer automatically blocked worldwide; they stay up under the owner's policy
  and monetize once resolved ([Google Help](https://support.google.com/youtube/answer/6013276)).
  Background commercial music still draws claims almost instantly, so prefer royalty-free
  or procedural audio and do a **Private upload** pre-check before publishing.
- **Originality:** Since **2026-10**, YouTube has throttled channel-level Shorts reach for
  repurposed clips with bare descriptive narration, minor crops/filters, or bulk templates.
  Pass the 5-point originality gate in `references/style-and-architecture.md` before scripting.
- **AI disclosure / C2PA:** YouTube Studio, TikTok's AI label, and Meta's "AI info" inspect
  C2PA metadata and expect manual disclosure for realistic synthetic footage or realistic
  altered/cloned voices, even when FFmpeg strips metadata. TikTok prohibits (labeled or not)
  likenesses of anyone under 18, private adults without consent, and fake endorsements by
  public figures. Record required disclosure flags in `CREDITS.md` and the handoff summary.
- **Real people:** use authentic high-resolution photos (≥1080 px short edge when available)
  from Wikimedia Commons, Wikipedia media, official press rooms, or public-domain archives.
  Never substitute a generated portrait for a named person without explicit user approval.

## 5. Commercial-safe model / renderer matrix

| Category | Safe | Caution / banned |
| :--- | :--- | :--- |
| Local TTS | Kokoro-82M (Apache-2.0, 24 kHz, 54 voices, CPU-fast — spell dates/numbers out), Qwen3-TTS 0.6B/1.7B (Apache-2.0, 3 s cloning, ~97 ms first packet), Orpheus-3B (Apache-2.0, expressive tags), Pocket TTS (check per-voice CC BY 4.0) | XTTS-v2 (Coqui CPML, non-commercial), F5-TTS (CC BY-NC 4.0), VibeVoice Realtime (research-only), Fish Audio S2-Pro (paid). Chatterbox (MIT) retired upstream Aug 2026 and PerTh-watermarked. |
| Hosted TTS | edge-tts (LGPL-3.0 code; service terms apply), licensed API voices | Unlicensed voice cloning of real people. |
| Renderers | Three.js (MIT), Blender (GPLv3 tool — output is yours), Pillow (MIT/HPND), Manim CE (MIT), Revideo / Motion Canvas (MIT) | Remotion: free for individuals/companies ≤3 people; $25/seat/mo Company, or $0.01/render with $100/mo minimum for Automators/batch ([pricing](https://www.remotion.dev/pricing)). |

## 6. Live refresh checklist (Step 2 of `SKILL.md`)

Run these before scriptwriting; paste any change into this file with today's date:

```bash
# platform / policy: check YouTube Help, TikTok Creative Center, Meta business docs
# libraries: check release notes for three.js, blender, revideo, whisperx, kokoro, qwen3-tts
python3 scripts/tool_probe.py --out capabilities.json     # local tool/model availability
python3 scripts/qc_gate.py --help                          # confirm gate flags still match
```

If a source cannot be reached, say so in the handoff and fall back to the conservative
(strict safe box + royalty-free audio) path rather than guessing.
