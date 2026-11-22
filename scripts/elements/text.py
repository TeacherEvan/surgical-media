"""elements/text.py — HUD badge, quote card and kinetic captions."""

from __future__ import annotations

from typing import Any

from canvas import SupersampledCanvas, get_font, rgb
from easings import ease_out_expo, spring_pop
from PIL import Image, ImageDraw

from elements._shared import DIM, GOLD, INK, ElementContext, _smoothstep, _wrap_text


def _paste_soft_pill(
    cv: SupersampledCanvas,
    box: tuple[float, float, float, float],
    fill: str,
    alpha: float,
    radius: float,
    outline: str | None = None,
    outline_width: float = 0.0,
) -> None:
    """Alpha-blend a rounded rectangle onto cv.image in design coordinates."""
    s = cv.scale
    x0 = max(0, round(box[0] * s))
    y0 = max(0, round(box[1] * s))
    x1 = min(cv.image.width, round(box[2] * s))
    y1 = min(cv.image.height, round(box[3] * s))
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2 or alpha <= 0.01:
        return
    r_px = max(1, round(radius * s))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=r_px, fill=round(255 * min(1.0, alpha))
    )
    cv.image.paste(Image.new("RGB", (w, h), rgb(fill)), (x0, y0), mask)
    if outline and outline_width > 0:
        omask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(omask).rounded_rectangle(
            (0, 0, w - 1, h - 1),
            radius=r_px,
            outline=round(255 * min(1.0, alpha * 1.15)),
            width=max(1, round(outline_width * s)),
        )
        cv.image.paste(Image.new("RGB", (w, h), rgb(outline)), (x0, y0), omask)


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
    reveal_start = float(el.get("reveal_start", 0.18))
    reveal_end = float(el.get("reveal_end", 0.62))
    reveal = ease_out_expo(_smoothstep(reveal_start, reveal_end, ctx.t))
    if reveal <= 0.01:
        return
    slide = (1.0 - reveal) * float(el.get("slide_px", 34.0))
    y0, y1 = y0 + slide, y1 + slide

    fill_col = el.get("fill", "#111C31")
    outline_col = el.get("outline", "#2B3A55")
    ink_col = str(el.get("ink_color", INK))
    dim_col = str(el.get("dim_color", DIM))
    accent_col = str(el.get("accent", GOLD))
    family = el.get("font_family")
    bold = bool(el.get("bold", True))
    align = str(el.get("align", "left")).lower()
    show_mark = bool(el.get("show_quote_mark", True))
    card_alpha = float(el.get("alpha", 1.0))
    rad = min(26.0, (y1 - y0) * 0.12)

    # With alpha < 1 the soft-pill card writes straight to cv.image and
    # ignores the world camera, while the card text uses it — under zoom/orbit
    # they drift apart (same pattern as paint_kinetic_captions).
    saved_cam = cv.camera
    if card_alpha < 0.999:
        cv.camera = None
    try:
        if fill_col not in (None, "", "none"):
            if card_alpha < 0.999:
                _paste_soft_pill(
                    cv,
                    (x0, y0, x1, y1),
                    str(fill_col),
                    card_alpha * reveal,
                    rad,
                    outline=(
                        None if outline_col in (None, "", "none") else str(outline_col)
                    ),
                    outline_width=1.8,
                )
            else:
                cv.rectangle(
                    (x0, y0, x1, y1),
                    fill=str(fill_col),
                    outline=(
                        None if outline_col in (None, "", "none") else str(outline_col)
                    ),
                    width=2.0,
                    radius=rad,
                )

        inner_w = (x1 - x0) * 0.86
        if show_mark:
            glyph_size = int((y1 - y0) * 0.34)
            cv.text(
                (x0 + (x1 - x0) * 0.055, y0 + (y1 - y0) * 0.16),
                "“",
                accent_col,
                size=glyph_size,
                anchor="lm",
                family=family,
                bold=bold,
            )
        font_size = int(el.get("size") or max(13, int((y1 - y0) * 0.115)))
        font = get_font(font_size, family=family, bold=bold)
        max_w = inner_w if align == "center" else inner_w - (x1 - x0) * 0.12
        lines = _wrap_text(quote, font, max_w)
        line_step = font_size * 1.32
        if align == "center":
            total_h = line_step * min(4, len(lines))
            ty = (y0 + y1) * 0.5 - total_h * 0.5 + font_size * 0.45
            if attribution:
                ty -= font_size * 0.55
            tx = (x0 + x1) * 0.5
            anchor = "mm"
        else:
            ty = y0 + (y1 - y0) * 0.30
            tx = x0 + (x1 - x0) * 0.075
            anchor = "lm"
        for line in lines[:4]:
            cv.text(
                (tx, ty),
                line,
                ink_col,
                size=font_size,
                anchor=anchor,
                family=family,
                bold=bold,
            )
            ty += line_step
        if attribution:
            attr_prefix = str(el.get("attribution_prefix", "— "))
            attr_text = f"{attr_prefix}{attribution}"
            attr_size = int(
                el.get("attribution_size") or max(10, int(font_size * 0.68))
            )
            attr_family = el.get("attribution_family", family)
            max_w_attr = (x1 - x0) * 0.86
            while (
                attr_size > 8
                and get_font(attr_size, family=attr_family, bold=False).getlength(
                    attr_text
                )
                > max_w_attr
            ):
                attr_size -= 1
            attr_pos = (
                ((x0 + x1) * 0.5, ty + font_size * 0.35)
                if align == "center"
                else (x0 + (x1 - x0) * 0.075, y1 - (y1 - y0) * 0.16)
            )
            cv.text(
                attr_pos,
                attr_text,
                dim_col,
                size=attr_size,
                anchor="mm" if align == "center" else "lm",
                family=attr_family,
                bold=False,
            )
    finally:
        if card_alpha < 0.999:
            cv.camera = saved_cam


def paint_kinetic_captions(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    words = ctx.words
    if not words:
        return
    _, cap_y0, _, cap_y1 = ctx.zones["captions"]
    font_size = int(el.get("size") or max(18, int(ctx.height * 0.030)))
    family = el.get("font_family")
    bold = bool(el.get("bold", True))
    font = get_font(font_size, family=family, bold=bold)
    accent = str(el.get("accent", GOLD))
    ink_color = str(el.get("ink_color", INK))
    dim_color = str(el.get("dim_color", "#39424F"))
    bg_color = el.get("bg_color", "#05070C")
    bg_alpha = float(el.get("bg_alpha", 1.0))
    bg_outline = el.get("bg_outline")
    stroke_color = el.get("stroke_color", "#05070C")
    if stroke_color in ("none", ""):
        stroke_color = None
    stroke_width = float(el.get("stroke_width", 2.0))
    active_stroke_width = float(
        el.get(
            "active_stroke_width", max(stroke_width, 3.0 if stroke_width > 0 else 0.0)
        )
    )
    pop_scale = float(el.get("pop_scale", 0.09))

    current_idx = -1
    for i, w in enumerate(words):
        if ctx.local_time >= float(w["start"]) - 0.02:
            current_idx = i
        else:
            break

    max_w_frac = float(el.get("max_width_frac", 0.94))
    max_w = (ctx.zones["safe"][2] - ctx.zones["safe"][0]) * max_w_frac
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

    line_boxes: list[tuple[float, float, list[tuple[int, float, float]]]] = []
    space_w = max(font.getlength(" "), font_size * 0.28)
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

    line_h = font_size * float(el.get("line_height", 1.28))
    block_h = line_h * len(lines)
    y_anchor = el.get("y_anchor")
    if y_anchor is not None:
        y = float(y_anchor) * ctx.height - block_h * 0.5
    else:
        y = cap_y0 + max(0.0, (cap_y1 - cap_y0 - block_h) / 2.0)

    # caption backdrop (optional; supports translucent pastel mist or clean no-box)
    pad = font_size * 0.48
    wide = max((s[-1][2] - s[0][1]) for _, _, s in line_boxes) if line_boxes else 0
    if bg_color not in (None, "", "none") and bg_alpha > 0.01:
        pill_box = (
            ctx.width / 2 - wide / 2 - pad * 1.15,
            y - pad * 0.62,
            ctx.width / 2 + wide / 2 + pad * 1.15,
            y + block_h + pad * 0.62,
        )
        pill_rad = float(el.get("bg_radius", 14.0))
        if bg_alpha < 0.999:
            _paste_soft_pill(
                cv,
                pill_box,
                str(bg_color),
                bg_alpha,
                pill_rad,
                outline=str(bg_outline) if bg_outline else None,
                outline_width=1.2 if bg_outline else 0.0,
            )
        else:
            saved_cam = cv.camera
            if y_anchor is not None:
                cv.camera = None
            try:
                cv.rectangle(
                    pill_box,
                    fill=str(bg_color),
                    outline=str(bg_outline) if bg_outline else None,
                    width=1.2 if bg_outline else 0.0,
                    radius=pill_rad,
                )
            finally:
                cv.camera = saved_cam

    for li, (_, _, spans) in enumerate(line_boxes):
        ly = y + li * line_h
        for wi_idx, wx0, wx1 in spans:
            wtext = words[wi_idx]["word"]
            if wi_idx < current_idx:
                fill = ink_color
            elif wi_idx == current_idx:
                pop = 1.0 + pop_scale * (
                    1.0
                    - _smoothstep(
                        float(words[wi_idx]["start"]),
                        float(words[wi_idx]["end"]),
                        ctx.local_time,
                    )
                )
                fill = accent
                saved_cam = cv.camera
                if y_anchor is not None or bg_alpha < 0.999:
                    cv.camera = None
                try:
                    cv.text(
                        ((wx0 + wx1) / 2, ly + line_h / 2),
                        wtext,
                        fill,
                        size=round(font_size * pop),
                        anchor="mm",
                        stroke_fill=stroke_color if active_stroke_width > 0 else None,
                        stroke_width=active_stroke_width,
                        family=family,
                        bold=bold,
                    )
                finally:
                    cv.camera = saved_cam
                continue
            else:
                fill = dim_color
            saved_cam = cv.camera
            if y_anchor is not None or bg_alpha < 0.999:
                cv.camera = None
            try:
                cv.text(
                    (wx0, ly + line_h / 2),
                    wtext,
                    fill,
                    size=font_size,
                    anchor="lm",
                    stroke_fill=stroke_color if stroke_width > 0 else None,
                    stroke_width=stroke_width,
                    family=family,
                    bold=bold,
                )
            finally:
                cv.camera = saved_cam


def paint_source_tag(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    """Lower-third provenance tag: ``LABEL · text`` (e.g. SOURCE / OPINION / FACT).

    Newsroom-style explainers put one on every factual claim; ``style_lint``
    treats a ``source_tag`` (or a ``quote_card`` ``attribution``) as the claim's
    citation. Fades/slides in over ``reveal_sec`` after ``start`` (scene-local).
    """
    text = str(el.get("text", "")).strip()
    if not text:
        return
    start = float(el.get("start", 0.0))
    reveal = ease_out_expo(
        _smoothstep(start, start + float(el.get("reveal_sec", 0.45)), ctx.local_time)
    )
    if reveal <= 0.01:
        return
    label = str(el.get("label", "SOURCE")).upper()
    ink = str(el.get("ink_color", INK))
    accent = str(el.get("accent", GOLD))
    fill = str(el.get("fill", "#0B1220"))
    sx0, sy0, sx1, sy1 = ctx.zones["safe"]
    size = int(el.get("size") or max(13, int(ctx.height * 0.021)))
    family = el.get("font_family")
    max_w = (sx1 - sx0) * 0.96
    while size > 9:
        label_font = get_font(size, family=family, bold=True)
        body_font = get_font(size, family=family, bold=False)
        gap = size * 0.6
        pad_x, pad_y = size * 0.7, size * 0.45
        w = label_font.getlength(label) + gap + body_font.getlength(text) + 2 * pad_x
        if w <= max_w:
            break
        size -= 1
    w = min(w, max_w)
    h = size + 2 * pad_y
    corner = str(el.get("corner", "bl"))
    x0 = sx1 - w if corner.endswith("r") else sx0
    y0 = (sy0 if corner.startswith("t") else sy1 - h) + (1.0 - reveal) * size * 1.2
    box = (x0, y0, x0 + w, y0 + h)
    _paste_soft_pill(
        cv,
        box,
        fill,
        float(el.get("alpha", 0.88)) * reveal,
        h * 0.28,
        outline=str(el.get("outline", accent)),
        outline_width=1.2,
    )
    cy = y0 + h / 2
    saved_cam = cv.camera
    cv.camera = None
    try:
        cv.text(
            (x0 + pad_x, cy),
            label,
            accent,
            size=size,
            anchor="lm",
            family=family,
            bold=True,
        )
        cv.text(
            (x0 + pad_x + label_font.getlength(label) + gap, cy),
            text,
            ink,
            size=size,
            anchor="lm",
            family=family,
            bold=False,
        )
    finally:
        cv.camera = saved_cam
