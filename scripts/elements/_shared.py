"""elements/_shared.py — shared constants, ElementContext and layout math.

Imported by every painter module. Keep painter-free: no drawing here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from canvas import layout_zones

TAU = math.tau
GOLD = "#FFD700"
CYAN = "#38BDF8"
GREEN = "#50FA7B"
RED = "#FF5555"
PURPLE = "#BD93F9"
INK = "#E5E9F0"
DIM = "#64748B"
PANEL = "#0F172A"
PANEL_EDGE = "#1E293B"
TERMINAL_BG = "#161B22"
TERMINAL_EDGE = "#30363D"


@dataclass
class ElementContext:
    width: int
    height: int
    t: float  # scene-local normalized progress [0, 1]
    scene_time: float  # absolute seconds from video start
    local_time: float  # seconds into this scene
    words: list[dict]  # karaoke words for this scene (may be empty)
    seed: int = 0
    trauma: float = 0.0
    zones: dict = field(default_factory=dict)
    base_dir: str | None = None

    def __post_init__(self) -> None:
        if not self.zones:
            self.zones = layout_zones(self.width, self.height)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _wrap_text(text: str, font, max_width_px: float) -> list[str]:
    """Greedy word wrap measured with the actual font metrics."""
    words = str(text).split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if font.getlength(f"{current} {word}") <= max_width_px:
            current += f" {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 1.0
    u = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return u * u * (3.0 - 2.0 * u)


def _bezier(p0, p1, p2, p3, t: float):
    mt = 1.0 - t
    x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
    return (x, y)
