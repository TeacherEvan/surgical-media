# Example plates (CC0 fixtures)

These three JPEGs are **deterministic procedural gradient fixtures** generated
with Pillow — not photographs and not AI-generated imagery. They exist so
`examples/photo_essay_storyboard.json` renders offline in CI (gate 8) and
demonstrates the image-first layout: full-bleed `cover`, `backdrop_blur`
"social bleed" on 9:16, Ken Burns drift, and safe-zone credit lines.

**Real productions never use these.** Fetch licensed subject photography:

```bash
python3 scripts/fetch_assets.py --query "<subject>" --out-dir assets --count 6
python3 scripts/tts_align.py --input script.spoken.json --output storyboard.json \
    --assets-manifest assets/manifest.json --aspect 9:16
```

The manifest's `attribution` strings travel onto every plate automatically.
