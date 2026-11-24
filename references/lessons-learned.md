# Lessons learned (operator preferences + field fixes)

## 1. User preference — MAXIMISE REAL PHOTOGRAPHY

**Always use as many authentic, licensed photographs as possible. Target one real
photo in every scene (100% coverage), not the 60% gate minimum.**

Reason given by the user: AI slop is rampant; content without real imagery looks
generated and untrustworthy. Procedural overlays, charts, UI mockups and 3D are
**accents on top of photographs**, never substitutes for them.

Practical rules:
- Never pass the `subject_imagery` gate with fabricated `chat_bubble`, `social_post`,
  `phone_frame`, `map` or `app_toast` elements standing in for a real person. That
  games the check and produces exactly the "no images" result the user rejects.
- Fetch licensed plates for **every named subject** before scripting; wire one plate
  per beat. Multiple distinct photos per subject are better than reusing one.
- Keep `attribution` on every `image` element and list every plate in `CREDITS.md`.

## 2. Imagery acquisition gotchas

- `media_harvester.py` requires `--people` values to be **real full names** (first +
  last). Mononyms such as `Sneako`, `Asmongold`, `Tectone`, `QTCinderella`, `Emiru`
  are rejected outright. Either supply a verified full name or use
  `fetch_assets.py --query "<name>" --source commons`.
- `fetch_assets.py` returns **false positives**. Real examples: query "Tectone"
  returned a guitar amplifier ("Angeltone DM-280") and "Eggy Ley Smoking Sax";
  "QTCinderella" returned Blaire White. ** visually curate every plate** (contact
  sheet) before wiring. Discard wrong subjects rather than using them.
- Wikimedia Commons exact-title search finds plates the keyword search misses:
  `https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=<name>&srnamespace=6&format=json`
  then fetch by exact file title. For group shots (e.g. OTK lineup) credit honestly
  as a group photo — do not claim it is a portrait of one person.
- CC0 / Public Domain Mark / CC BY / CC BY-SA are all commercial-safe with
  attribution (`monetization_gate` allowlist). Log license + source URL per plate.
- Normalise harvested originals to full-bleed 1080x1920 plates: cover-crop portraits,
  contain-over-blurred-cover for landscape group shots (avoid black bars), then wire
  with `fit: "cover"`, `kb_zoom`, `attribution`, `attribution_y: 1060`.

## 3. TTS pronunciation must be verified before a long render

- Kokoro (`af_heart`) is the default female local voice, but it mangles proper nouns.
  The user heard **"lawyers" pronounced as "liers"**; names like Hasan/Emiru were also
  affected. Never commit to a 25-min render without checking the VO.
- Use Kokoro's own phonemiser for objective checks:
  `engine.tokenizer.phonemize(word, "en-us")`. It showed `lawyers` → `lˈɔɪɚz`
  (correct) while `loy-ers` → `lˈɔɪˈɜːz` and `law-yers` → `lˈɔːjˈɚz`. Aggressive
  hyphenation often makes pronunciation **worse**; respell only where the default is
  demonstrably wrong (e.g. `Hasan → ha-sahn` because default is `hˈæsən`).
- Respelling pattern that worked: apply a 1-token-in/1-token-out map to the spoken
  script only, run `tts_normalizer` + `tts_align`, then restore the original tokens
  in `narration` and `words[].word` from a reverse map so captions stay correctly
  spelled.
- Generate a short sample (hook + names + optional female edge voice comparison),
  give the user the path, and get an explicit go/no-go **before** rendering.
- If the user says pronunciation is bad, believe them — do not argue from G2P output.

## 4. Rendering reliability

- Do **not** run multiple full `render_engine.py` jobs in parallel. A parallel 4:5
  job died with `ffmpeg died mid-render` at ~1/5 of the frames. Render sequentially.
- Always run `--thumbnails` and inspect a contact sheet before a full render; this
  caught clipped headlines, overflowing terminal lines, stock mockup text and a
  washed-out threejs plate.
- Adapted exports should be **native reflows**, not pillarboxed masters. Map the 9:16
  safe rectangle onto each target safe rectangle (see `canvas.safe_rect`), scale
  font/coordinates, and set `kinetic_captions.y_anchor` from that format's captions
  zone. Drop 9:16-only evidence cards that would collide with adapted captions.

## 5. Working with the user

- If outputs are in Trash, treat that as **intentional rejection**, not cleanup.
  Ask why before restoring them. In this project the male-TTS renders were trashed
  because the user hated the voice.
- Keep critique responses short, own the mistake, and fix the root cause rather
  than defending the previous attempt.
- The user writes in enthusiastic/all-caps broken English when frustrated; it is
  not a request for clarification. Respond calmly and concretely.
- `qc_gate`'s `no_dead_air` may flag one natural ~0.7 s narration pause. That is an
  advisory; do not add a synthetic pad to silence it (clean-audio invariant wins).

## 6. Credits & disclosure for this workflow

- Disclose AI voice (engine + voice name), any phonetic respellings, and that
  on-screen captions keep correct spelling.
- Disclose that all imagery is licensed photography (no AI-generated likenesses).
- Update `publish_kit.md` per export with format, safe-zone verification and the
  disclosure line.

## 7. No black/opaque boxes on photographs

The user reacted strongly to dark cards layered over the photos (map panels,
terminal windows, social-post cards, chat bubbles, phone frames, dark HUD/source
pills). Rule: **photograph first, boxless stroked text only.**

- Set `hud_badge` and `source_tag` to `fill: "none"`, `outline: "none"`, `alpha: 0`
  — the renderers then draw boxless stroked text with a small accent underline.
- Remove `map`, `map_callout`, `map_arrow`, `code_terminal`, `social_post`,
  `chat_bubble`, `phone_frame`, `app_toast`, `scaling_chart` and
  `system_architecture` elements from photo-led beats rather than restyling them.
  The spoken captions already carry the facts.
- Keep only decorative primitives (`orb_pulse`, `dot_field`, `orbit_ring`,
  `equalizer`, `stick_rig`, simple `svg` outlines), `typewriter_text` and
  `kinetic_captions` on top of the plate.
- Inspect a contact sheet of all 16 thumbnails before rendering: a single black
  card is enough to make the whole piece feel like "AI slop" to the user.
