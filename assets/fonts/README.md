# Bundled fonts — Inter & JetBrains Mono (SIL Open Font License 1.1)

Bundled-to-repo copies of [Inter v4.1](https://github.com/rsms/inter/releases/tag/v4.1)
(static TTF masters from `extras/ttf/`), retrieved 2026-11-18, and
[JetBrains Mono v2.304](https://github.com/JetBrains/JetBrainsMono/releases/tag/v2.304)
(static TTFs from `fonts/ttf/`), retrieved 2026-11-18.

## Sans — Inter

| File | Size (bytes) | SHA-256 |
|---|---|---|
| Inter-Regular.ttf | 411,640 | `40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82` |
| Inter-SemiBold.ttf | 419,744 | `78a843fade9d4612a5567302fb595b56976eb5fcebf4fea5a5912d638bafcde3` |
| Inter-Bold.ttf | 420,428 | `288316099b1e0a47a4716d159098005eef7c0066921f34e3200393dbdb01947f` |
| LICENSE.Inter.txt | 4,380 | `262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a` |

Full license text: `LICENSE.Inter.txt` (OFL 1.1 — redistribution allowed, no
restrictions beyond retaining the license; no modified versions are
distributed).

**Why:** the system font pool (DejaVu/Liberation/Arial) is generic. Inter is
the display face the archetype field guide calls for — tighter apertures and
a more confident default letterform than DejaVu, so captions, HUD badges and
letterspaced kickers all render in one voice. `canvas.py` prefers this directory over system fonts; DejaVu remains
the system fallback.

## Mono — JetBrains Mono

| File | Size (bytes) | SHA-256 |
|---|---|---|
| JetBrainsMono-Regular.ttf | 273,900 | `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f` |
| JetBrainsMono-Bold.ttf | 277,828 | `5590990c82e097397517f275f430af4546e1c45cff408bde4255dad142479dcb` |
| LICENSE.JetBrainsMono.txt | 4,399 | `30f0c136e3c88e422d0791acd97238870f9054a9729bc34cf2ff0d4ed8cac4ad` |

Full license text: `LICENSE.JetBrainsMono.txt` (OFL 1.1, same terms as above).

**Why:** the `code_report` archetype and HUD badges need deterministic
character-cell alignment across operating systems. A bundled mono face removes
the DejaVu/Menlo/Consola cross-OS drift — code indentation, cursor columns and
the code-terminal element render identically everywhere. `canvas.py` prefers
this directory for `get_font(mono=True)`; DejaVu Sans Mono remains the system
fallback.

Verification:

```bash
python3 -c "from PIL import ImageFont; f = ImageFont.truetype('assets/fonts/Inter-Bold.ttf', 24); print(f.getname())"
python3 -c "from PIL import ImageFont; f = ImageFont.truetype('assets/fonts/JetBrainsMono-Regular.ttf', 24); print(f.getname())"
```
