#!/usr/bin/env python3
"""layout_solver.py — deterministic AABB collision solver for HUD card layout.

Purpose: position small axis-aligned "telemetry card" boxes around locked
"obstacle" zones (a locked central stage repulsion zone and a locked HUD
header) on a fixed canvas, with zero overlap, hard clamping to the canvas
bounds, and byte-for-byte deterministic output.

How it works, plainly:

1. Each box is tested as a padded axis-aligned bounding box (``padding`` is
   inflated around the box for collision tests only; the returned rect never
   changes ``width``/``height``).
2. For every overlapping pair, the penetration depth is measured on both the
   x and y axes; the *minimum* axis is the one to resolve along. This is the
   separating-axis idea applied to exactly two axes, which is all an
   axis-aligned box has. This is intentionally NOT a general polygon SAT —
   there are no rotated axes, no arbitrary polygons, and no edge normals to
   project onto. Boxes only.
3. Non-locked vs non-locked pairs split the minimal-axis correction 50/50.
   Locked boxes are immovable obstacles: a non-locked box that overlaps a
   locked box is pushed fully out along the minimal axis. Locked vs locked
   pairs are left alone. If one side of a 50/50 split is pinned by the canvas
   clamp, the unapplied share transfers to the other side so separation
   still happens; if both sides are pinned, the result is best effort.
4. After each pass, every non-locked box is clamped back inside the canvas
   with a 24 px margin. A box larger than the clamp box keeps its size and is
   pinned to the margin; nothing raises for oversized or invalid inputs.
5. The minimal-axis loop can stall on a zero-net-progress fixed point when a
   box is pinched between the canvas clamp and a locked obstacle (one side
   pinned below, the other pinned against the obstacle's padded edge). If —
   and only if — overlap remains after the minimal-axis rounds, a bounded
   rescue phase runs additional passes resolving pairs on the *other* axis,
   with the same correction and clamp rules. It is a no-op when the main
   loop converged and keeps the solver honest to the "non-locked boxes never
   overlap" contract.

Iterate ``iterations`` rounds (Gauss-Seidel style: pairs are applied in place
in sorted ``box_id`` order, so later pairs see earlier corrections). Output is
deterministic: pairs are processed in sorted order, there is no randomness
anywhere, and inputs are never mutated — fresh ``LayoutBox`` instances are
returned in a ``box_id -> LayoutBox`` dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

CANVAS_MARGIN = 24.0
_EPSILON = 1e-9
_RESCUE_ROUNDS = 25


@dataclass
class LayoutBox:
    """Axis-aligned box used by the layout solver.

    ``locked`` marks an immovable obstacle (stage zone, HUD header).
    ``padding`` inflates the box for collision tests only; it never changes
    ``width``/``height``.
    """

    box_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    locked: bool = False
    padding: float = 0.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def _padded(box: LayoutBox) -> tuple[float, float, float, float]:
    """Collision rect: the box inflated by its own (non-negative) padding."""
    p = max(0.0, box.padding)
    return (box.x0 - p, box.y0 - p, box.x1 + p, box.y1 + p)


def _axis_penetration(a: LayoutBox, b: LayoutBox) -> tuple[float, float] | None:
    """Return (px, py) padded penetration depths, or None when separated."""
    ax0, ay0, ax1, ay1 = _padded(a)
    bx0, by0, bx1, by1 = _padded(b)
    px = min(ax1, bx1) - max(ax0, bx0)
    py = min(ay1, by1) - max(ay0, by0)
    if px > 0.0 and py > 0.0:
        return (px, py)
    return None


def _sign_away(delta: float, a_id: str, b_id: str) -> float:
    """Direction for a box with ``delta`` to its neighbour to move away.

    On an exact tie the lexicographically smaller id moves in the negative
    direction, keeping the outcome deterministic.
    """
    if delta > 0.0:
        return 1.0
    if delta < 0.0:
        return -1.0
    return -1.0 if a_id < b_id else 1.0


def _with_offset(box: LayoutBox, dx: float, dy: float) -> LayoutBox:
    return LayoutBox(
        box_id=box.box_id,
        x0=box.x0 + dx,
        y0=box.y0 + dy,
        x1=box.x1 + dx,
        y1=box.y1 + dy,
        locked=box.locked,
        padding=box.padding,
    )


def _clamp_to_canvas(box: LayoutBox, width: int, height: int) -> LayoutBox:
    """Clamp a non-locked box into the canvas with a 24 px margin.

    Keeps the box size; a box larger than the clamp box is pinned to the
    margin instead of raised or resized.
    """
    box_w = box.width
    box_h = box.height
    limit_x = width - 2.0 * CANVAS_MARGIN
    limit_y = height - 2.0 * CANVAS_MARGIN
    if box_w <= limit_x:
        x0 = min(max(box.x0, CANVAS_MARGIN), width - CANVAS_MARGIN - box_w)
    else:
        x0 = CANVAS_MARGIN
    if box_h <= limit_y:
        y0 = min(max(box.y0, CANVAS_MARGIN), height - CANVAS_MARGIN - box_h)
    else:
        y0 = CANVAS_MARGIN
    if x0 == box.x0 and y0 == box.y0:
        return box
    return LayoutBox(
        box_id=box.box_id,
        x0=x0,
        y0=y0,
        x1=x0 + box_w,
        y1=y0 + box_h,
        locked=box.locked,
        padding=box.padding,
    )


def _parse_aspect(aspect_ratio: str) -> float | None:
    """Parse ``"W:H"`` into a width/height ratio; None when unparsable."""
    try:
        w_s, h_s = aspect_ratio.split(":", 1)
        w = float(w_s)
        h = float(h_s)
    except (AttributeError, ValueError):
        return None
    if w > 0.0 and h > 0.0:
        return w / h
    return None


def _resolve_canvas(aspect_ratio: str, width: int, height: int) -> tuple[int, int]:
    """Width/height govern; aspect_ratio is a fallback for invalid values."""
    if width > 0 and height > 0:
        return width, height
    ratio = _parse_aspect(aspect_ratio)
    if ratio is not None:
        fallback_h = 1080
        return max(1, round(fallback_h * ratio)), fallback_h
    return 1920, 1080


def _apply_pairs(
    current: list[LayoutBox],
    width: int,
    height: int,
    *,
    prefer_min_axis: bool,
) -> bool:
    """One relaxation pass over every overlapping pair, in sorted order.

    With ``prefer_min_axis=True`` each pair separates along the axis of
    least penetration; with ``False`` along the axis of greatest penetration
    (rescue phase). Every non-locked box is clamped into the canvas after the
    pass. Returns True when at least one overlapping pair was found.
    """
    any_overlap = False
    pairs = sorted(
        combinations(range(len(current)), 2),
        key=lambda idx: (
            current[idx[0]].box_id,
            current[idx[1]].box_id,
        ),
    )
    for i, j in pairs:
        a = current[i]
        b = current[j]
        penetration = _axis_penetration(a, b)
        if penetration is None:
            continue
        any_overlap = True
        px, py = penetration
        resolve_x = (px <= py) if prefer_min_axis else (px > py)
        if a.locked and b.locked:
            continue
        if a.locked:
            move = _sign_away(
                b.cx - a.cx if resolve_x else b.cy - a.cy,
                b.box_id,
                a.box_id,
            ) * ((px if resolve_x else py) + _EPSILON)
            current[j] = (
                _with_offset(b, move, 0.0) if resolve_x else _with_offset(b, 0.0, move)
            )
        elif b.locked:
            move = _sign_away(
                a.cx - b.cx if resolve_x else a.cy - b.cy,
                a.box_id,
                b.box_id,
            ) * ((px if resolve_x else py) + _EPSILON)
            current[i] = (
                _with_offset(a, move, 0.0) if resolve_x else _with_offset(a, 0.0, move)
            )
        else:
            # 50/50 split of the resolved axis. When one side is pinned by
            # the canvas clamp, the unapplied share transfers to the other
            # side so separation still happens (clamp-aware).
            depth = px if resolve_x else py
            half = depth / 2.0 + _EPSILON / 2.0
            if resolve_x:
                direction = _sign_away(a.cx - b.cx, a.box_id, b.box_id)
                da, db = direction * half, -direction * half
                moved_a = _clamp_to_canvas(_with_offset(a, da, 0.0), width, height)
                absorbed = da - (moved_a.x0 - a.x0)
                moved_b = _clamp_to_canvas(
                    _with_offset(b, db - absorbed, 0.0), width, height
                )
                current[i], current[j] = moved_a, moved_b
            else:
                direction = _sign_away(a.cy - b.cy, a.box_id, b.box_id)
                da, db = direction * half, -direction * half
                moved_a = _clamp_to_canvas(_with_offset(a, 0.0, da), width, height)
                absorbed = da - (moved_a.y0 - a.y0)
                moved_b = _clamp_to_canvas(
                    _with_offset(b, 0.0, db - absorbed), width, height
                )
                current[i], current[j] = moved_a, moved_b
    current[:] = [
        box if box.locked else _clamp_to_canvas(box, width, height) for box in current
    ]
    return any_overlap


class SATLayoutSolver:
    """Constraint-projecting AABB layout solver (see module docstring)."""

    @staticmethod
    def solve(
        boxes: list[LayoutBox],
        aspect_ratio: str = "16:9",
        width: int = 1920,
        height: int = 1080,
        iterations: int = 50,
    ) -> dict[str, LayoutBox]:
        """Resolve overlaps and return fresh boxes keyed by ``box_id``.

        Raises ``ValueError`` on duplicate ``box_id`` values. Never raises for
        oversized boxes or invalid canvas dimensions — those are clamped as
        best effort with the box size preserved.
        """
        seen: set[str] = set()
        for box in boxes:
            if box.box_id in seen:
                raise ValueError(f"duplicate box_id: {box.box_id!r}")
            seen.add(box.box_id)

        width, height = _resolve_canvas(aspect_ratio, width, height)
        current = [
            LayoutBox(b.box_id, b.x0, b.y0, b.x1, b.y1, b.locked, b.padding)
            for b in boxes
        ]

        rounds = max(0, iterations)
        for _ in range(rounds):
            if not _apply_pairs(current, width, height, prefer_min_axis=True):
                break
        # Rescue: only when overlap survived the minimal-axis rounds.
        for _ in range(_RESCUE_ROUNDS):
            if not _apply_pairs(current, width, height, prefer_min_axis=False):
                break

        return {box.box_id: box for box in current}
