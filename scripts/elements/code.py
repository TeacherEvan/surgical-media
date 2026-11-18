"""elements/code.py — code terminal and system-architecture diagrams."""

from __future__ import annotations

from canvas import get_font

from elements._shared import (
    CYAN,
    GREEN,
    INK,
    RED,
    TERMINAL_BG,
    TERMINAL_EDGE,
    ElementContext,
    _bezier,
    _smoothstep,
)

_NODE_W = 210.0
_NODE_H = 64.0


def paint_system_architecture(cv, el: dict, ctx: ElementContext) -> None:
    nodes = el.get("nodes", [])
    if not nodes:
        return
    cascade_start = float(el.get("cascade_start", 1.1))
    cascade_step = float(el.get("cascade_step", 0.65))
    source = next((n for n in nodes if n.get("role") == "source"), nodes[0])
    targets = [n for n in nodes if n is not source]
    font_size = max(11, int(ctx.height * 0.017))
    mono = True

    # failure cascade order: targets in declaration order
    def node_state(node) -> tuple[str, float]:
        role = node.get("role", "exchange")
        if role == "source":
            return "ok", 0.0
        idx = targets.index(node)
        fail_at = cascade_start + idx * cascade_step
        if ctx.local_time >= fail_at:
            return "fail", ctx.local_time - fail_at
        return "ok", 0.0

    # edges: cubic bezier from source to each target, animated packets
    sx, sy = float(source["x"]) + _NODE_W / 2, float(source["y"])
    for k, tgt in enumerate(targets):
        tx, ty = float(tgt["x"]) - _NODE_W / 2, float(tgt["y"])
        p0, p3 = (sx, sy), (tx, ty)
        midx = (p0[0] + p3[0]) / 2
        p1, p2 = (midx, p0[1]), (midx, p3[1])
        cv.line(p0, p3, "#1F2A3D", 1.0)  # faint guide
        # bezier spine
        spine = [_bezier(p0, p1, p2, p3, i / 60) for i in range(61)]
        cv.polyline(spine, "#26334A", 2.0)
        state, _ = node_state(tgt)
        for pk in range(2):
            p = (ctx.local_time * 0.75 + pk * 0.5 + k * 0.17) % 1.0
            pos = _bezier(p0, p1, p2, p3, p)
            if state == "ok":
                color = CYAN
            else:
                color = (
                    RED if p > 0.55 else CYAN
                )  # packets redden as they die mid-flight
            r = 5.0
            cv.ellipse((pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r), fill=color)
            if color == RED:
                cv.bloom_ellipse(
                    (pos[0] - r * 2, pos[1] - r * 2, pos[0] + r * 2, pos[1] + r * 2),
                    fill=RED,
                )

    # nodes
    for node in nodes:
        nx, ny = float(node["x"]), float(node["y"])
        state, since = node_state(node)
        ok = state == "ok"
        border = GREEN if ok else RED
        label = str(node.get("label", node["id"])).upper()
        box = (nx - _NODE_W / 2, ny - _NODE_H / 2, nx + _NODE_W / 2, ny + _NODE_H / 2)
        cv.rectangle(box, fill=TERMINAL_BG, outline=border, width=2.4, radius=10.0)
        # status dot
        dot_r = 5.0
        cv.ellipse(
            (
                nx - _NODE_W / 2 + 12,
                ny - dot_r,
                nx - _NODE_W / 2 + 12 + dot_r * 2,
                ny + dot_r,
            ),
            fill=border,
        )
        cv.bloom_ellipse(
            (
                nx - _NODE_W / 2 + 12 - dot_r,
                ny - dot_r * 2,
                nx - _NODE_W / 2 + 12 + dot_r * 3,
                ny + dot_r * 2,
            ),
            fill=border,
        )
        cv.text(
            (nx - _NODE_W / 2 + 30, ny - 14),
            label,
            INK,
            size=font_size,
            mono=mono,
            anchor="lm",
        )
        status = "200 OK" if ok else "503 TLS POOL"
        cv.text(
            (nx - _NODE_W / 2 + 30, ny + 12),
            status,
            border,
            size=font_size,
            mono=mono,
            anchor="lm",
        )
        if not ok and since < 0.35:  # failure flash
            flash = 1.0 - since / 0.35
            cv.bloom_rectangle(
                (
                    box[0] - 8 * flash,
                    box[1] - 8 * flash,
                    box[2] + 8 * flash,
                    box[3] + 8 * flash,
                ),
                fill="#2A0505",
            )


_CODE_KIND = {
    "normal": ("#C9D1D9", None),
    "add": ("#7EE787", "#1B3326"),
    "del": ("#FFA198", "#3B2526"),
    "comment": ("#8B949E", None),
    "accent": (CYAN, None),
}


def paint_code_terminal(cv, el: dict, ctx: ElementContext) -> None:
    box = el.get(
        "box",
        [ctx.width * 0.14, ctx.height * 0.24, ctx.width * 0.86, ctx.height * 0.72],
    )
    x0, y0, x1, y1 = [float(v) for v in box]
    lines = el.get("lines", [])
    title = str(el.get("title", "logs/api.log"))
    reveal = _smoothstep(0.06, 0.86, ctx.t)
    total = max(1, len(lines))
    shown = min(total, int(reveal * total) + (1 if reveal > 0 else 0))

    cv.rectangle(box, fill=TERMINAL_BG, outline=TERMINAL_EDGE, width=2.0, radius=14.0)
    bar_h = max(30.0, (y1 - y0) * 0.085)
    cv.rectangle((x0, y0, x1, y0 + bar_h), fill="#0D1117", radius=14.0)
    # square off the bottom corners of the title bar
    cv.rectangle((x0, y0 + bar_h / 2, x1, y0 + bar_h), fill="#0D1117")
    dot_y = y0 + bar_h / 2
    for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        dx = x0 + 20 + i * 20
        cv.ellipse((dx - 5, dot_y - 5, dx + 5, dot_y + 5), fill=c)
    title_size = max(10, int(bar_h * 0.42))
    cv.text(
        ((x0 + x1) / 2, dot_y),
        title,
        "#8B949E",
        size=title_size,
        mono=True,
        anchor="mm",
    )

    body_top = y0 + bar_h + 12
    body_h = y1 - body_top - 12
    line_h = body_h / max(1.0, min(shown, 18))
    font_size = max(9, int(line_h * 0.58))
    mono_font = get_font(font_size, mono=True)
    cursor_on = int(ctx.local_time * 2.4) % 2 == 0

    for i, line in enumerate(lines[:shown]):
        ly = body_top + i * line_h
        if isinstance(line, str):
            line = {"text": line, "kind": "normal"}
        text = str(line.get("text", ""))
        kind = str(line.get("kind", "normal"))
        fg, row_bg = _CODE_KIND.get(kind, _CODE_KIND["normal"])
        if row_bg:
            cv.rectangle((x0 + 4, ly, x1 - 4, ly + line_h), fill=row_bg)
        gutter = str(i + 1).rjust(3)
        cv.text(
            (x0 + 14, ly + line_h / 2),
            gutter,
            "#4B5563",
            size=font_size,
            mono=True,
            anchor="lm",
        )
        cv.text(
            (x0 + 44, ly + line_h / 2), text, fg, size=font_size, mono=True, anchor="lm"
        )
        if i == shown - 1 and cursor_on:
            tx = x0 + 44 + mono_font.getlength(text) + 2
            cv.rectangle(
                (tx, ly + line_h * 0.18, tx + font_size * 0.6, ly + line_h * 0.82),
                fill=CYAN,
            )
