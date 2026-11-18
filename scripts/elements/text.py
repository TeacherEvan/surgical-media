"""elements/text.py — HUD badge, quote card and kinetic captions."""

from __future__ import annotations

from typing import Any

from canvas import SupersampledCanvas, get_font
from easings import ease_out_expo, spring_pop

from elements._shared import DIM, GOLD, INK, ElementContext, _smoothstep, _wrap_text


def paint_hud_badge(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    text = str(el.get("text", ""))
    if not text:
        return
    corner = str(el.get("corner", "tl"))
    reveal = spring_pop(min(1.0, ctx.local_time / 0.55))
    if reveal <= 0.01:
        return
    hud = ctx.zones["hud"]
    font_size = max(14, int((hud[3] - hud[1]) * 0.42))
    font = get_font(font_size, mono=True)
    pad_x, pad_y = font_size * 0.55, font_size * 0.24
    w = font.getlength(text) + 2 * pad_x
    h = font_size + 2 * pad_y
    if corner == "tr":
        bx0 = hud[2] - w
    elif corner == "tc":
        bx0 = (hud[0] + hud[2] - w) / 2.0
    else:  # tl
        bx0 = hud[0]
    by0 = hud[1] + (hud[3] - hud[1] - h) / 2.0
    # reveal: grow from anchor with spring pop
    scale_pop = 0.6 + 0.4 * reveal
    cx, cy = bx0 + w / 2, by0 + h / 2
    sw, sh = w * scale_pop, h * scale_pop
    box = (cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2)
    cv.rectangle(box, fill="#0B1220", outline=GOLD, width=2.0, radius=h * 0.35)
    cv.text((cx, cy), text, GOLD, size=font_size, mono=True, anchor="mm")


def paint_quote_card(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    box = el.get(
        "box",
        [ctx.width * 0.16, ctx.height * 0.52, ctx.width * 0.84, ctx.height * 0.78],
    )
    x0, y0, x1, y1 = [float(v) for v in box]
    quote = str(el.get("quote", ""))
    attribution = str(el.get("attribution", ""))
    reveal = ease_out_expo(_smoothstep(0.18, 0.62, ctx.t))
    if reveal <= 0.01:
        return
    slide = (1.0 - reveal) * 34.0
    y0, y1 = y0 + slide, y1 + slide

    cv.rectangle(
        (x0, y0, x1, y1),
        fill="#111C31",
        outline="#2B3A55",
        width=2.0,
        radius=min(26.0, (y1 - y0) * 0.12),
    )
    inner_w = (x1 - x0) * 0.86
    glyph_size = int((y1 - y0) * 0.34)
    cv.text(
        (x0 + (x1 - x0) * 0.055, y0 + (y1 - y0) * 0.16),
        "“",
        GOLD,
        size=glyph_size,
        anchor="lm",
    )
    font_size = max(13, int((y1 - y0) * 0.115))
    font = get_font(font_size)
    max_w = inner_w - (x1 - x0) * 0.12
    lines = _wrap_text(quote, font, max_w)
    ty = y0 + (y1 - y0) * 0.30
    for line in lines[:4]:
        cv.text((x0 + (x1 - x0) * 0.075, ty), line, INK, size=font_size, anchor="lm")
        ty += font_size * 1.32
    if attribution:
        attr_text = f"— {attribution}"
        attr_size = max(10, int(font_size * 0.78))
        max_w_attr = (x1 - x0) * 0.86
        while attr_size > 8 and get_font(attr_size).getlength(attr_text) > max_w_attr:
            attr_size -= 1
        cv.text(
            (x0 + (x1 - x0) * 0.075, y1 - (y1 - y0) * 0.16),
            attr_text,
            DIM,
            size=attr_size,
            anchor="lm",
        )


def paint_kinetic_captions(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    words = ctx.words
    if not words:
        return
    _, cap_y0, _, cap_y1 = ctx.zones["captions"]
    font_size = el.get("size") or max(18, int(ctx.height * 0.030))
    font = get_font(int(font_size))
    accent = el.get("accent", GOLD)

    current_idx = -1
    for i, w in enumerate(words):
        if ctx.local_time >= float(w["start"]) - 0.02:
            current_idx = i
        else:
            break

    max_w = (ctx.zones["safe"][2] - ctx.zones["safe"][0]) * 0.94
    # wrap the measured token stream itself — edge-tts WordBoundary events
    # may carry multiple whitespace-separated words in one event, so
    # re-splitting a joined string would desynchronize the spans.
    tokens = [str(w["word"]) for w in words]
    lines: list[list[int]] = [[0]]
    cur_text = tokens[0]
    for i in range(1, len(tokens)):
        candidate = f"{cur_text} {tokens[i]}"
        if font.getlength(candidate) <= max_w:
            lines[-1].append(i)
            cur_text = candidate
        else:
            lines.append([i])
            cur_text = tokens[i]

    # locate the current word's line + x-offset while walking indices
    line_boxes: list[tuple[float, float, list[tuple[int, float, float]]]] = []
    space_w = max(font.getlength(" "), font_size * 0.30)
    for line in lines:
        line_words = [tokens[i] for i in line]
        content_w = sum(font.getlength(w) for w in line_words) + space_w * max(
            0, len(line_words) - 1
        )
        x = (ctx.width - content_w) / 2.0
        spans = []
        for i, w in zip(line, line_words):
            ww = font.getlength(w)
            spans.append((i, x, x + ww))
            x += ww + space_w
        line_boxes.append((content_w, 0.0, spans))

    line_h = font_size * 1.28
    block_h = line_h * len(lines)
    y = cap_y0 + max(0.0, (cap_y1 - cap_y0 - block_h) / 2.0)

    # caption backdrop
    pad = font_size * 0.45
    wide = max((s[-1][2] - s[0][1]) for _, _, s in line_boxes) if line_boxes else 0
    cv.rectangle(
        (
            ctx.width / 2 - wide / 2 - pad,
            y - pad * 0.6,
            ctx.width / 2 + wide / 2 + pad,
            y + block_h + pad * 0.6,
        ),
        fill="#05070C",
        radius=12.0,
    )

    for li, (_, _, spans) in enumerate(line_boxes):
        ly = y + li * line_h
        for wi_idx, wx0, wx1 in spans:
            wtext = words[wi_idx]["word"]
            if wi_idx < current_idx:
                fill = INK
            elif wi_idx == current_idx:
                pop = 1.0 + 0.09 * (
                    1.0
                    - _smoothstep(
                        float(words[wi_idx]["start"]),
                        float(words[wi_idx]["end"]),
                        ctx.local_time,
                    )
                )
                fill = accent
                cv.text(
                    ((wx0 + wx1) / 2, ly + line_h / 2),
                    wtext,
                    fill,
                    size=int(font_size * pop),
                    anchor="mm",
                    stroke_fill="#05070C",
                    stroke_width=3,
                )
                continue
            else:
                fill = "#39424F"
            cv.text(
                (wx0, ly + line_h / 2),
                wtext,
                fill,
                size=font_size,
                anchor="lm",
                stroke_fill="#05070C",
                stroke_width=2,
            )
