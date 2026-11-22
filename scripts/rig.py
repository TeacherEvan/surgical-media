#!/usr/bin/env python3
"""rig.py — articulated 2-bone inverse kinematics & stick-figure rendering.

Analytical two-bone IK (shoulder→elbow→hand) via the law of cosines. When the
target is out of reach the limb is stretched toward it (clamped to full
extension), so poses never explode numerically.

``draw_stick_figure`` renders Alan Becker-style hollow-head vector figures
onto a SupersampledCanvas. Motion is driven purely by scene time ``t`` plus a
bending bias — deterministic, no physics state.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from canvas import SupersampledCanvas

ORANGE = "#FF6B00"
WHITE = "#FFFFFF"


def two_bone_ik(
    shoulder: tuple[float, float],
    target: tuple[float, float],
    upper: float,
    lower: float,
    bend: int = 1,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Solve elbow/hand positions for a 2-bone limb.

    Returns (elbow, hand). ``bend`` = +1/-1 selects which side the elbow
    folds to (mirrored for left vs. right limbs).
    """
    if upper <= 0.0 or lower <= 0.0:
        raise ValueError("limb lengths must be positive")
    sx, sy = shoulder
    tx, ty = target
    dx, dy = tx - sx, ty - sy
    dist_raw = math.hypot(dx, dy)
    eps = 1e-6
    if dist_raw < eps:  # degenerate: aim straight up
        dx, dy, dist_raw = 0.0, -1.0, 1.0
    dist = min(max(dist_raw, abs(upper - lower) + eps), upper + lower - eps)
    # interior angle at the shoulder between the shoulder→target axis and shoulder→elbow
    cos_a = (upper * upper + dist * dist - lower * lower) / (2.0 * upper * dist)
    cos_a = min(1.0, max(-1.0, cos_a))
    alpha = math.acos(cos_a)
    base = math.atan2(dy, dx)
    elbow_angle = base + bend * alpha
    ex = sx + upper * math.cos(elbow_angle)
    ey = sy + upper * math.sin(elbow_angle)
    # hand is exactly at the clamped target along the axis
    hx = sx + math.cos(base) * dist
    hy = sy + math.sin(base) * dist
    return (ex, ey), (hx, hy)


def draw_stick_figure(
    canvas: SupersampledCanvas,
    root_x: float,
    root_y: float,
    height: float,
    t: float,
    *,
    reach_target: tuple[float, float] | None = None,
    reach_side: str = "right",
    bob_amplitude: float = 6.0,
    bob_hz: float = 1.6,
    lean: float = 0.08,
    color: str = ORANGE,
    head_radius: float | None = None,
) -> dict[str, tuple[float, float]]:
    """Draw a hollow-head stick figure. Returns the joint map (design px).

    ``root_x, root_y`` is the ground point between the feet. ``height`` is
    total head-to-foot height in design px. ``reach_target`` in design px
    gives the hand a world-space point to track via IK (e.g. a φ divider).
    """
    bob = math.sin(t * math.tau * bob_hz) * bob_amplitude
    hip_y = root_y - height * 0.52 + bob * 0.4
    shoulder_y = root_y - height * 0.86 + bob
    head_cy = root_y - height * 0.945 + bob
    head_r = head_radius if head_radius is not None else height * 0.055

    hip = (root_x, hip_y)
    shoulder_c = (root_x + math.sin(lean) * height * 0.06, shoulder_y)

    # legs: static wide stance, knees forward via IK to fixed feet
    foot_l = (root_x - height * 0.22, root_y)
    foot_r = (root_x + height * 0.22, root_y)
    hip_l = (hip[0] - height * 0.07, hip_y)
    hip_r = (hip[0] + height * 0.07, hip_y)
    leg_l1, leg_l2 = height * 0.28, height * 0.28
    knee_l, _ = two_bone_ik(hip_l, foot_l, leg_l1, leg_l2, bend=-1)
    knee_r, _ = two_bone_ik(hip_r, foot_r, leg_l1, leg_l2, bend=1)

    # arms: reaching arm tracks the target, other arm relaxes downward
    shoulder_l = (shoulder_c[0] - height * 0.17, shoulder_y + height * 0.02)
    shoulder_r = (shoulder_c[0] + height * 0.17, shoulder_y + height * 0.02)
    arm_l1 = arm_l2 = height * 0.24

    def relaxed_hand(side: str) -> tuple[float, float]:
        sway = math.sin(t * math.tau * bob_hz * 0.5 + (0.0 if side == "left" else 1.7))
        if side == "left":
            return (
                shoulder_l[0] - height * 0.10 + sway * 4.0,
                shoulder_l[1] + height * 0.30,
            )
        return (
            shoulder_r[0] + height * 0.10 - sway * 4.0,
            shoulder_r[1] + height * 0.30,
        )

    if reach_target is not None:
        if reach_side == "left":
            target_l = reach_target
            target_r = relaxed_hand("right")
        else:
            target_l = relaxed_hand("left")
            target_r = reach_target
    else:
        target_l, target_r = relaxed_hand("left"), relaxed_hand("right")

    elbow_l, hand_l = two_bone_ik(shoulder_l, target_l, arm_l1, arm_l2, bend=-1)
    elbow_r, hand_r = two_bone_ik(shoulder_r, target_r, arm_l1, arm_l2, bend=1)

    spine_w = max(2.0, height * 0.018)
    limb_w = max(2.0, height * 0.014)
    # torso
    canvas.line(hip, shoulder_c, color, spine_w)
    # pelvis bar
    canvas.line(
        (hip[0] - height * 0.10, hip_y), (hip[0] + height * 0.10, hip_y), color, limb_w
    )
    # legs
    canvas.polyline([hip_l, knee_l, foot_l], color, limb_w)
    canvas.polyline([hip_r, knee_r, foot_r], color, limb_w)
    # arms
    canvas.polyline([shoulder_l, elbow_l, hand_l], color, limb_w)
    canvas.polyline([shoulder_r, elbow_r, hand_r], color, limb_w)
    # shoulder bar
    canvas.line(shoulder_l, shoulder_r, color, limb_w)
    # hollow head: orange ring, void interior
    hx, hy = shoulder_c[0], head_cy
    canvas.line((shoulder_c[0], shoulder_y), (hx, hy + head_r), color, limb_w)
    canvas.ellipse(
        (hx - head_r, hy - head_r, hx + head_r, hy + head_r),
        outline=color,
        fill="#050508",
        width=spine_w,
    )

    return {
        "hip": hip,
        "shoulder": shoulder_c,
        "head": (hx, hy),
        "elbow_l": elbow_l,
        "hand_l": hand_l,
        "elbow_r": elbow_r,
        "hand_r": hand_r,
        "knee_l": knee_l,
        "knee_r": knee_r,
        "foot_l": foot_l,
        "foot_r": foot_r,
    }
