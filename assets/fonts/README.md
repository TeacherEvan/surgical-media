# Bundled fonts — Inter (SIL Open Font License 1.1)

Bundled-to-repo copies of [Inter v4.1](https://github.com/rsms/inter/releases/tag/v4.1)
(static TTF masters from `extras/ttf/`), retrieved 2026-11-18.

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
the mono + system fallback.

Mono note: Inter has no monospaced cut; `get_font(mono=True)` keeps the
system mono stack unchanged.

Verification:

```bash
python3 -c "from PIL import ImageFont; f = ImageFont.truetype('assets/fonts/Inter-Bold.ttf', 24); print(f.getname())"
```
