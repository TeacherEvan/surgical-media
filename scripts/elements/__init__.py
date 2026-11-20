"""elements — drawable element painters for surgical-media scenes.

Package re-exporting every public symbol so existing imports
(``from elements import render_element, ElementContext``) are unchanged.
Painters live in focused modules: scenes, text, dataviz, code, figures, media.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from elements._shared import (
    ElementContext,
    _bezier,
    _smoothstep,
    _wrap_text,
)
from elements.code import paint_code_terminal, paint_system_architecture
from elements.dataviz import (
    _reveal_box,
    paint_phi_divider,
    paint_scaling_chart,
    paint_tesseract,
)
from elements.figures import paint_stick_rig
from elements.media import paint_image
from elements.scenes import paint_background, paint_grid
from elements.svg import paint_svg
from elements.text import (
    paint_hud_badge,
    paint_kinetic_captions,
    paint_quote_card,
    paint_source_tag,
)
from elements.visual import (
    paint_dot_field,
    paint_equalizer,
    paint_leader_arrow,
    paint_orb_pulse,
    paint_orbit_ring,
    paint_typewriter_text,
)

if TYPE_CHECKING:
    from canvas import SupersampledCanvas

__all__ = [
    "RENDERERS",
    "ElementContext",
    "_bezier",
    "_reveal_box",
    "_smoothstep",
    "_wrap_text",
    "paint_background",
    "paint_code_terminal",
    "paint_dot_field",
    "paint_equalizer",
    "paint_grid",
    "paint_hud_badge",
    "paint_image",
    "paint_kinetic_captions",
    "paint_leader_arrow",
    "paint_orb_pulse",
    "paint_orbit_ring",
    "paint_phi_divider",
    "paint_quote_card",
    "paint_scaling_chart",
    "paint_source_tag",
    "paint_stick_rig",
    "paint_svg",
    "paint_system_architecture",
    "paint_tesseract",
    "paint_typewriter_text",
    "render_element",
]


def render_element(
    cv: SupersampledCanvas, el: dict[str, Any], ctx: ElementContext
) -> None:
    painter = RENDERERS.get(str(el.get("type")))
    if painter is None:
        print(
            f"render_engine: warning — unknown element type {el.get('type')!r}; skipping",
            flush=True,
        )
        return
    painter(cv, el, ctx)


RENDERERS = {
    "background": paint_background,
    "grid": paint_grid,
    "hud_badge": paint_hud_badge,
    "scaling_chart": paint_scaling_chart,
    "phi_divider": paint_phi_divider,
    "tesseract": paint_tesseract,
    "system_architecture": paint_system_architecture,
    "code_terminal": paint_code_terminal,
    "quote_card": paint_quote_card,
    "kinetic_captions": paint_kinetic_captions,
    "stick_rig": paint_stick_rig,
    "image": paint_image,
    "svg": paint_svg,
    "source_tag": paint_source_tag,
    # personality painters (visual.py) — motion by local_time, fully deterministic
    "orb_pulse": paint_orb_pulse,
    "dot_field": paint_dot_field,
    "orbit_ring": paint_orbit_ring,
    "equalizer": paint_equalizer,
    "typewriter_text": paint_typewriter_text,
    "leader_arrow": paint_leader_arrow,
}
