"""elements/ui_mockups.py — comedy/satire UI mockups.

Phone frames, dating-app swipe cards, social posts, chat bubbles, and toast
notifications — the visual objects Horse Tenny-style comedy boards need.
Painters are deterministic pure functions of ``ElementContext`` (spring pops
and gentle wobble on ``local_time``); defaults come from the style preset
palette when the board supplies one (``style.py`` resolves ``@role`` refs).

Element types: ``phone_frame``, ``swipe_card``, ``social_post``,
``chat_bubble``, ``app_toast``.
"""

from __future__ import annotations

import math
from typing import Any

from canvas import SupersampledCanvas, get_font

from elements._shared import TAU, ElementContext


def _smoothstep(lo: float, hi: float, t: float) -> float:
    tt = (t - lo) / (hi - lo) if hi > lo else 0.0
    return max(0.0, min(1.0, tt))


def _wobble(t: float, period: float, amp: float) -> float:
    """Deterministic wobble in ``[1 - amp, 1 + amp]`` on scene time."""
    return 1.0 + amp * math.sin(TAU * t / period)


# ---------------------------------------------------------------------------
# phone_frame — device outline with notch and corner chrome
# ---------------------------------------------------------------------------


def paint_phone_frame(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    x0, y0, x1, y1 = (float(v) for v in el.get("box", [0, 0, ctx.width, ctx.height]))
    bg = str(el.get("bg", el.get("ground", "#FFF4D6")))
    outline = str(el.get("outline", el.get("ink", "#1B1B1F")))
    notch_h = float(el.get("notch_h", 56))
    notch_w = float(el.get("notch_w", 150))
    pad = float(el.get("pad", 22))
    # The bezel: frame draws the outer silhouette
    cv.rectangle((x0, y0, x1, y1), fill=outline, radius=14)
    # Screen interior (inset by the bezel)
    sx0, sy0, sx1, sy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    cv.rectangle((sx0, sy0, sx1, sy1), fill=bg, radius=8)
    # Notch + top corner bezel
    notch_cx = (sx0 + sx1) / 2
    cv.rectangle((sx0, sy0 + 3, sx1, sy0 + notch_h + 8), fill=bg)
    cv.rectangle(
        (notch_cx - notch_w / 2, sy0 + 8, notch_cx + notch_w / 2, sy0 + notch_h + 3),
        fill=bg,
    )
    cv.rectangle(
        (sx0 - 2, y0 + notch_h + 8, sx0, sy1 - pad), outline=outline, width=2.0
    )
    cv.rectangle(
        (sx1, y0 + notch_h + 8, sx1 + 2, sy1 - pad), outline=outline, width=2.0
    )


# ---------------------------------------------------------------------------
# swipe_card — stacked dating-app cards, pop wobble on scene time
# ---------------------------------------------------------------------------


def paint_swipe_card(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    x0, y0, x1, y1 = (float(v) for v in el.get("box", [60, 420, 1020, 1400]))
    default_accent = str(el.get("accent", "#FFD23F"))
    cards = [c for c in el.get("cards", []) if isinstance(c, dict)]
    if not cards:
        cards = [{"label": "Stallion. 7/10. Owns a garden."}]
    pop = float(el.get("pop", 0.1))
    pop_period = max(1e-3, float(el.get("pop_period", 0.55)))
    scale = _wobble(ctx.local_time, pop_period, pop)

    gap = (y1 - y0) * 0.08
    top = cards[-1]
    backs = cards[:-1]
    top_top = y0 + gap * len(backs)
    top_h = min(y1 - top_top, (y1 - y0) * 0.26)

    # back cards (static, behind the top card)
    for i, back in enumerate(reversed(backs)):
        b_y0 = top_top - gap * (len(backs) - i)
        b_y1 = top_top - gap * (len(backs) - i - 1)
        cv.rectangle(
            (x0, b_y0, x1, b_y1),
            fill=str(back.get("accent", default_accent)),
            radius=14,
        )

    # top card — wobbles with the pop beat
    cx = (x0 + x1) / 2
    tw = (x1 - x0) * scale
    t0 = cx - tw / 2
    cv.rectangle(
        (t0, top_top, t0 + tw, top_top + top_h),
        fill=str(top.get("accent", default_accent)),
        radius=18,
    )

    # label centred on the top card
    text = str(top.get("label", ""))
    cv.text(
        (t0 + tw / 2, top_top + top_h / 2),
        text,
        str(top.get("text_color", "#000000")),
        size=float(el.get("size", 34)),
        anchor="mm",
    )
    if str(top.get("mark", "#FF4D6D")):
        cv.ellipse(
            (t0 + tw - 60, top_top + 30, t0 + tw - 30, top_top + 60),
            fill=str(top.get("mark", "#FF4D6D")),
        )


# ---------------------------------------------------------------------------
# social_post — feed card: header, body, heart + comments + share
# ---------------------------------------------------------------------------


def paint_social_post(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    x0, y0, x1, y1 = (float(v) for v in el.get("box", [40, 220, 1040, 620]))
    post = el.get("post") or {}
    name = str(post.get("name", "Whinny & Hooves"))
    avatar = str(post.get("avatar", el.get("accent", "#A65A38")))
    body = post.get("body") or ["Garden done.", "Photos inside."]
    likes = int(post.get("likes", 3))
    heart_bob = 0.055 * math.sin(TAU * ctx.local_time / 0.9)
    body_top = y0 + 96

    # header: avatar + name
    cv.ellipse((x0 + 60, y0 + 44, x0 + 104, y0 + 88), fill=avatar)
    cv.text(
        (x0 + 112, y0 + 66), name, str(el.get("ink", "#1B1B1F")), size=34, bold=True
    )

    # card
    cv.rectangle((x0, body_top, x1, y1), fill=str(el.get("bg", "#FFF4D6")), radius=16)

    # body lines
    for i, line in enumerate(body[:4]):
        cv.text(
            (x0 + 48, body_top + 24 + i * 50),
            str(line),
            str(el.get("ink", "#1B1B1F")),
            size=34,
            bold=False,
        )

    # heart + comments + share, footer area
    footer_y = y1 - 96
    hx = (x0 + x1) / 2 - 196 + heart_bob
    cv.ellipse(
        (hx - 17, footer_y - 17, hx + 17, footer_y + 17),
        fill=str(el.get("accent", "#FF4D6D")),
    )
    cv.text((hx, footer_y + 6), "0", str(el.get("ink", "#1B1B1F")), size=30, bold=True)
    cv.text(
        (hx + 34, footer_y),
        f"{likes} comments",
        str(el.get("dim_color", "#5A4A44")),
        size=30,
        bold=False,
    )
    cv.text(
        (hx + 262, footer_y),
        "share",
        str(el.get("dim_color", "#5A4A44")),
        size=30,
        bold=False,
    )


# ---------------------------------------------------------------------------
# chat_bubble — message bubbles with tails, entry fade per bubble
# ---------------------------------------------------------------------------


def paint_chat_bubble(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    x0, y0, x1, _y1 = (float(v) for v in el.get("box", [0, 0, ctx.width, ctx.height]))
    bubbles = el.get("bubbles") or [
        {"side": "left", "text": "Why do I need a garden?"},
        {"side": "right", "text": "4.2 stars — 81% match."},
    ]
    t = ctx.local_time
    font = get_font(30)
    pad, radius = 34, 14
    for i, b in enumerate(bubbles[:6]):
        if not isinstance(b, dict):
            continue
        progress = _smoothstep(
            float(b.get("delay", 0.0)), float(b.get("delay", 0.0)) + 0.35, t
        )
        if progress < 0.02:
            continue
        accent = str(b.get("accent", el.get("accent", "#A65A38")))
        text = str(b.get("text", ""))
        tw = min(font.getlength(text) + pad, (x1 - x0) * 0.62)
        th = 46 + len(text.split()) * 10
        side = str(b.get("side", "left")).lower()
        ty0 = y0 + 10 + i * (th + 18) * 1.1 + (1.0 - progress) * 18
        if side == "right":
            bx0 = x1 - tw - pad
            tx = bx0 + pad * 0.5
            tail_pts = [
                (bx0 + tw + 4, ty0 + th - 6),
                (bx0 + tw + 22, ty0 + th - 12),
                (bx0 + tw - 4, ty0 + th - 20),
            ]
        else:
            bx0 = x0 + pad
            tx = bx0 + 4
            tail_pts = [
                (bx0 - 6, ty0 + th - 6),
                (bx0 - 18, ty0 + th - 12),
                (bx0 + 4, ty0 + th - 20),
            ]
        cv.rectangle((bx0, ty0, bx0 + tw, ty0 + th), fill=accent, radius=radius)
        cv.polygon(tail_pts, fill=accent)
        cv.text(
            (tx, ty0 + th / 2),
            text,
            str(el.get("text_color", "#FFF4D6")),
            size=float(el.get("size", 34)),
            anchor="lm",
            bold=False,
        )


# ---------------------------------------------------------------------------
# app_toast — bottom notification pill, slides up from time-delay
# ---------------------------------------------------------------------------


def paint_app_toast(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    t = ctx.local_time
    delay = float(el.get("delay", 0.25))
    show_in = float(el.get("show_in", 0.25))
    duration = float(el.get("duration", 0.9))
    progress = _smoothstep(delay, delay + show_in, t)
    if progress < 0.02 or t > delay + show_in + duration:
        return
    x0, y0, x1, y1 = (float(v) for v in el.get("box", [0, 0, ctx.width, ctx.height]))
    toast = el.get("toast") or {
        "text": "MATCH: Stallion #412 — garden: yes",
        "accent": el.get("accent", "#FF4D6D"),
    }
    text = str(toast.get("text", ""))
    # slides up from below the safe band as `show_in` elapses
    ty = y1 - 40 - (y1 - y0) * 0.28 + (1.0 - progress) * 12
    cv.rectangle(
        (x0 + 40, ty - 48, x1 - 40, ty + 10),
        fill=str(toast.get("accent", el.get("accent", "#FF4D6D"))),
        radius=22,
    )
    cv.text(
        (x0 + 66, ty - 10),
        text,
        str(el.get("text_color", "#FFF4D6")),
        size=float(el.get("size", 32)),
    )
