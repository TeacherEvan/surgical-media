#!/usr/bin/env python3
"""blender_plate.py — optional Blender-rendered 3D plate generator.

**Optional path.** The Pillow pipeline remains the core renderer; this tool
exists for the shots Pillow cannot do: a stylised planet, a faceted iceberg,
a ringed sentinel — rendered headless to a transparent PNG that the `image`
element composites like any fetched photograph.

Run it like any other repo tool:

    python3 scripts/blender_plate.py --kind earth --out assets/earth.png --size 1280x720

When invoked outside Blender it re-execs headless via ``blender --background
--python <this file> -- …``. When Blender is absent it exits 2 with a clear
message — the rest of the skill is unaffected.

Uses the Workbench engine (no GPU/display server required, no HDRI assets),
material colours + cavity shading for a matte, editorial look. Deterministic:
noise origins come from ``--seed``.
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # bpy exists only inside Blender
    import bpy

KINDS = ("earth", "iceberg", "ringed")


def build_scene(kind: str, seed: int) -> bpy.types.Scene:
    import bpy

    # --- reset scene ---------------------------------------------------------
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = True  # alpha plate for compositing
    shading = scene.display.shading
    shading.color_type = "MATERIAL"
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.show_shadows = False

    def mat(name: str, hex_color: str) -> bpy.types.Material:
        m = bpy.data.materials.new(name)
        rgb = tuple(int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
        m.diffuse_color = (*rgb, 1.0)
        return m

    if kind == "earth":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=96, ring_count=48, radius=1.0, location=(0, 0, 0)
        )
        globe = bpy.context.active_object
        globe.data.materials.append(mat("ocean", "#123B5C"))
        bpy.context.view_layer.objects.active = globe
        bpy.ops.object.shade_smooth()
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=48, ring_count=16, radius=0.34, location=(0.18, 0.15, 0.86)
        )
        cap = bpy.context.active_object
        cap.scale = (1.0, 1.0, 0.38)
        bpy.ops.object.shade_smooth()
        cap.data.materials.append(mat("ice-cap", "#E8F2F8"))
    elif kind == "iceberg":
        bpy.ops.mesh.primitive_cone_add(
            vertices=9, radius1=1.0, radius2=0.42, depth=1.7, location=(0, 0, 0.4)
        )
        berg = bpy.context.active_object
        # deterministic facet displacement — a hand-rough, crystal look
        import random

        rng = random.Random(seed)
        for v in berg.data.vertices:
            v.co.x += rng.uniform(-0.09, 0.09)
            v.co.y += rng.uniform(-0.09, 0.09)
            v.co.z += rng.uniform(-0.05, 0.05)
        berg.data.materials.append(mat("iceberg", "#BFE3F2"))
    elif kind == "ringed":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=64, ring_count=32, radius=0.78, location=(0, 0, 0)
        )
        planet = bpy.context.active_object
        planet.data.materials.append(mat("planet", "#324A66"))
        bpy.context.view_layer.objects.active = planet
        bpy.ops.object.shade_smooth()
        bpy.ops.mesh.primitive_torus_add(
            major_radius=1.28, minor_radius=0.075, location=(0, 0, 0)
        )
        ring = bpy.context.active_object
        ring.scale = (1.0, 1.0, 0.35)
        ring.rotation_euler = (0.42, 0.12, 0.0)
        ring.data.materials.append(mat("ring", "#8FA8C4"))
    else:  # pragma: no cover — argparse restricts choices before this
        raise ValueError(kind)

    # camera: three-quarter orthographic-ish view, seeded micro-orbit
    import math
    import random

    from mathutils import Vector

    orbit = math.radians(28 + random.Random(seed).uniform(-6.0, 6.0))
    distance = 4.4
    cam_loc = Vector((distance * math.cos(orbit), distance * math.sin(orbit), 1.05))
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    direction = Vector((0.0, 0.0, 0.0)) - cam_loc
    cam.rotation_euler = direction.to_track_quat("-Z", "Z").to_euler()
    cam.data.lens = 45
    scene.camera = cam
    return scene


def render(scene: bpy.types.Scene, out: Path, width: int, height: int) -> None:
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(out)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    import bpy

    bpy.ops.render.render(write_still=True)


def png_dimensions(path: Path) -> tuple[int, int]:
    """Parse PNG IHDR without any imaging dependency (blender-safe)."""
    with open(path, "rb") as fh:
        header = fh.read(33)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


def run_under_blender(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--size", default="1280x720", help="WIDTHxHEIGHT, default 1280x720"
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        width, height = (int(part) for part in args.size.lower().split("x"))
    except ValueError:
        print(
            f"blender_plate: --size must look like 1280x720, got {args.size!r}",
            file=sys.stderr,
        )
        return 2
    scene = build_scene(args.kind, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(scene, args.out, width, height)
    try:
        w, h = png_dimensions(args.out)
    except ValueError as exc:
        print(f"blender_plate: {exc}", file=sys.stderr)
        return 3
    print(
        f"blender_plate: rendered {args.out} ({w}x{h}, kind={args.kind}, seed={args.seed})"
    )
    return 0


def main() -> int:
    if (
        "bpy" in sys.modules
    ):  # already inside Blender: `blender --background --python … -- args`
        argv = sys.argv[sys.argv.index("--") + 1 :]
        return run_under_blender(argv)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--size", default="1280x720", help="WIDTHxHEIGHT, default 1280x720"
    )
    parser.add_argument("--seed", type=int, default=42)
    args, extra = parser.parse_known_args()
    blender = shutil.which("blender")
    if blender is None:
        print(
            "blender_plate: Blender not found on PATH. This is an OPTIONAL step — "
            "the Pillow pipeline does not need it. Install Blender ≥ 4.2 or skip plates.",
            file=sys.stderr,
        )
        return 2
    forwarded = [
        "--kind",
        args.kind,
        "--out",
        str(args.out),
        "--size",
        args.size,
        "--seed",
        str(args.seed),
        *extra,
    ]
    proc = subprocess.run(
        [
            blender,
            "--background",
            "--python",
            str(Path(__file__).resolve()),
            "--",
            *forwarded,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
