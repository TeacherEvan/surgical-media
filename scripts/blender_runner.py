#!/usr/bin/env python3
"""blender_runner.py — standalone headless Blender scene renderer.

This script runs *inside* Blender's own Python interpreter. It must not import
any repo modules; it ships as a single self-contained file. It implements a
focused subset of a 3D scene plan and is honest about scope.

Exact invocation line:

    blender -b -P scripts/blender_runner.py -- --spec spec.json --out-dir build/scene --width 1920 --height 1080 --fps 30 --frames 60

Supported categories:

  exploded_hardware_3d   layered AI-package hardware exploded view (default):
                         Package Substrate / CoWoS HBM3e Interposer / 5nm AI
                         Compute Die / 3D Vapor Chamber Fins, beveled cubes,
                         sinusoidal explode driven by ``explode_factor``.
  orbital_or_field_3d    plasma torus with 12 twisted coil tori parented to a
                         coil rig; plasma rotation keyframed 0 -> 2*pi.
  organic_serpent_3d     animated jade serpent: a tapered, beveled CURVE spine
                         (26 poly points) whose coordinates are keyframed per
                         frame for a travelling S-wave, with a gold head,
                         emissive eyes and a tongue on a head rig; the whole
                         body sways gently on a parent rig.

The following known 3D categories are **not** implemented and raise
``NotImplementedError`` (no silent fallback):

  network_topology_3d, rigid_body_physics_3d, mathematical_manifold_3d,
  external_asset_3d

Importing this module outside Blender is safe: ``bpy``/``bmesh``/``mathutils``/
``bpy_extras`` are imported in a guarded block and ``INSIDE_BLENDER`` is set to
``False``. Every bpy-touching code path is only reachable when
``INSIDE_BLENDER`` is true, and ``run_blender_scene`` raises ``RuntimeError``
otherwise.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # bpy exists only inside Blender
    from bpy.types import Object

try:  # Blender-provided modules; absent under the repo's interpreter.
    import bmesh
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    INSIDE_BLENDER = True
except Exception:  # noqa: BLE001 - any failure means "not inside Blender"
    bpy = None  # type: ignore[assignment]
    bmesh = None  # type: ignore[assignment]
    world_to_camera_view = None  # type: ignore[assignment]
    Vector = None  # type: ignore[assignment]
    INSIDE_BLENDER = False

SUPPORTED_CATEGORIES = (
    "exploded_hardware_3d",
    "orbital_or_field_3d",
    "organic_serpent_3d",
)
UNIMPLEMENTED_CATEGORIES = (
    "network_topology_3d",
    "rigid_body_physics_3d",
    "mathematical_manifold_3d",
    "external_asset_3d",
)


def hex_to_linear_rgba(hex_str, alpha=1.0):
    """Convert an sRGB hex color (#RGB or #RRGGBB, lenient about case/'#')
    to a linear-space RGBA tuple."""
    s = str(hex_str).strip().removeprefix("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"Cannot parse hex color: {hex_str!r}")
    try:
        r8, g8, b8 = (int(s[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f"Cannot parse hex color: {hex_str!r}") from None

    def _srgb_to_linear(channel: int) -> float:
        c = channel / 255.0
        if c <= 0.04045:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    return (
        _srgb_to_linear(r8),
        _srgb_to_linear(g8),
        _srgb_to_linear(b8),
        float(alpha),
    )


def set_bsdf_socket(bsdf_node, candidates, value):
    """Set the first matching Principled BSDF input by name. Returns True on hit."""
    inputs = bsdf_node.inputs
    for name in candidates:
        socket = inputs.get(name)
        if socket is None:
            continue
        try:
            socket.default_value = value
        except (TypeError, ValueError):
            continue
        return True
    return False


def create_pbr_material(
    name,
    base_hex,
    metallic=0.0,
    roughness=0.5,
    emission_hex="#000000",
    emission_strength=0.0,
    transmission=0.0,
    coat=0.0,
):
    """Create a Principled-BSDF material with linear-space inputs."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    set_bsdf_socket(bsdf, ["Base Color"], hex_to_linear_rgba(base_hex))
    set_bsdf_socket(bsdf, ["Metallic"], float(metallic))
    set_bsdf_socket(bsdf, ["Roughness"], float(roughness))
    set_bsdf_socket(bsdf, ["Coat Weight", "Clearcoat"], float(coat))
    set_bsdf_socket(bsdf, ["Transmission Weight", "Transmission"], float(transmission))
    set_bsdf_socket(
        bsdf,
        ["Emission Color", "Emission"],
        hex_to_linear_rgba(emission_hex),
    )
    set_bsdf_socket(bsdf, ["Emission Strength"], float(emission_strength))
    return mat


def _try_set(obj, attr, value):
    try:
        setattr(obj, attr, value)
        return True
    except Exception:  # noqa: BLE001 - optional/renamed property on this build
        return False


def _configure_cycles(scene):
    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.samples = 64
    _try_set(cycles, "use_adaptive_sampling", True)
    _try_set(cycles, "use_denoising", True)
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA", "HIP", "METAL"):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                devices = list(prefs.devices)
                if any(getattr(d, "type", None) == backend for d in devices):
                    for device in devices:
                        device.use = True
                    cycles.device = "GPU"
                    return
            except Exception:  # noqa: S112,BLE001 - backend unavailable; try next
                continue
        cycles.device = "CPU"
    except Exception:  # noqa: BLE001 - GPU not available; CPU fallback
        _try_set(cycles, "device", "CPU")


def _configure_eevee(scene):
    version = tuple(bpy.app.version)
    if (4, 2) <= version < (5, 0):
        engine = "BLENDER_EEVEE_NEXT"
    else:
        engine = "BLENDER_EEVEE"
    if not _try_set(scene.render, "engine", engine):
        _try_set(scene.render, "engine", "BLENDER_EEVEE")
    eevee = getattr(scene, "eevee", None)
    if eevee is None:
        return
    for attr, value in (
        ("taa_render_samples", 64),
        ("use_bloom", True),
        ("use_ssr", True),
    ):
        if hasattr(eevee, attr):
            _try_set(eevee, attr, value)


def _set_glare_option(glare, socket_name, legacy_attr, values):
    """Set a glare option via socket (Blender 5+) or property (Blender <=4.x)."""
    sock = glare.inputs.get(socket_name) if hasattr(glare, "inputs") else None
    for value in values:
        try:
            if sock is not None:
                sock.default_value = value
            else:
                setattr(glare, legacy_attr, value)
            return True
        except Exception:  # noqa: S112,BLE001 - try next candidate identifier
            continue
    return False


def _link_glare_chain(tree, rl, glare, comp):
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])


def _setup_compositor_glare(scene):
    """RLayers -> Glare(FOG_GLOW) -> composite. Tolerates Blender 4 and 5."""
    _try_set(scene, "use_nodes", True)
    if hasattr(scene, "node_tree"):  # Blender <= 4.x classic compositor
        tree = scene.node_tree
        if tree is None:
            raise RuntimeError("scene.node_tree is None after use_nodes=True")
        for node in list(tree.nodes):
            tree.nodes.remove(node)
        rl = tree.nodes.new("CompositorNodeRLayers")
        glare = tree.nodes.new("CompositorNodeGlare")
        _set_glare_option(glare, "unused", "glare_type", ("FOG_GLOW",))
        _set_glare_option(glare, "unused", "quality", ("HIGH",))
        _set_glare_option(glare, "unused", "threshold", (0.85,))
        _set_glare_option(glare, "unused", "size", (7,))
        comp = tree.nodes.new("CompositorNodeComposite")
        rl.location = (0, 0)
        glare.location = (250, 0)
        comp.location = (500, 0)
        _link_glare_chain(tree, rl, glare, comp)
        return
    if hasattr(scene, "compositing_node_group"):  # Blender 5.x node group
        group = bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
        group.interface.new_socket(
            "Image", in_out="OUTPUT", socket_type="NodeSocketColor"
        )
        rl = group.nodes.new("CompositorNodeRLayers")
        glare = group.nodes.new("CompositorNodeGlare")
        _set_glare_option(glare, "Type", "glare_type", ("Fog Glow", "FOG_GLOW"))
        _set_glare_option(glare, "Quality", "quality", ("High", "HIGH"))
        _set_glare_option(glare, "Threshold", "threshold", (0.85,))
        _set_glare_option(glare, "Size", "size", (0.85,))
        out = group.nodes.new("NodeGroupOutput")
        rl.location = (0, 0)
        glare.location = (250, 0)
        out.location = (500, 0)
        _link_glare_chain(group, rl, glare, out)
        scene.compositing_node_group = group
        return
    raise RuntimeError("no compositor node tree API found on this Blender build")


def configure_render_pipeline(
    scene,
    width,
    height,
    fps,
    total_frames,
    engine_pref="AUTO_EEVEE",
    transparent_bg=False,
):
    """Apply resolution/fps/range/motion-blur/engine/color/compositor settings."""
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    _try_set(scene.render, "resolution_percentage", 100)
    scene.render.fps = round(fps)
    scene.frame_start = 1
    scene.frame_end = int(total_frames)
    scene.render.film_transparent = bool(transparent_bg)
    _try_set(scene.render, "use_motion_blur", True)
    _try_set(scene.render, "motion_blur_shutter", 0.45)

    pref = (engine_pref or "AUTO_EEVEE").strip().upper()
    if pref.startswith("CYCLES"):
        try:
            _configure_cycles(scene)
        except Exception as exc:  # noqa: BLE001 - fall back to EEVEE
            print(f"warning: CYCLES setup failed ({exc}); falling back to EEVEE")
            _configure_eevee(scene)
    else:
        _configure_eevee(scene)

    for view_transform in ("AgX", "Filmic", "Standard"):
        try:
            scene.view_settings.view_transform = view_transform
            break
        except Exception:  # noqa: S112,BLE001 - transform missing on this build
            continue
    for look in (
        "AgX - High Contrast",
        "High Contrast",
        "Medium High Contrast",
        "None",
    ):
        try:
            scene.view_settings.look = look
            break
        except Exception:  # noqa: S112,BLE001 - look missing on this build
            continue

    try:
        _setup_compositor_glare(scene)
    except Exception as exc:  # noqa: BLE001 - glare is an enhancement, not core
        print(f"warning: compositor glare setup skipped: {exc}")


def setup_lighting_and_world(scene, preset="cyber_studio_volumetric"):
    """World background + three area lights (linear-space colors)."""
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    background = next((n for n in nodes if n.type == "BACKGROUND"), None)
    if background is None:
        background = nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = hex_to_linear_rgba("#050811")
    background.inputs["Strength"].default_value = 0.65

    key_hex = "#E0F2FE" if preset == "cyber_studio_volumetric" else "#FFFBEB"
    light_specs = [
        ("KeyLight", 1400.0, 4.5, (5.0, -4.5, 5.5), key_hex, (42, 0, 42)),
        ("RimLight", 2200.0, 3.5, (-5.5, 5.0, 4.0), "#38BDF8", (58, 0, -135)),
        ("FillLight", 600.0, 6.0, (-4.0, -5.0, 2.5), "#818CF8", (65, 0, -40)),
    ]
    for name, energy, size, location, hex_color, rot_deg in light_specs:
        light_data = bpy.data.lights.new(name, type="AREA")
        light_data.energy = energy
        light_data.size = size
        light_data.color = hex_to_linear_rgba(hex_color)[:3]
        obj = bpy.data.objects.new(name, light_data)
        obj.location = location
        obj.rotation_euler = tuple(math.radians(a) for a in rot_deg)
        scene.collection.objects.link(obj)


def _cubic_ease_in_out(u: float) -> float:
    u = min(1.0, max(0.0, u))
    if u < 0.5:
        return 4.0 * u * u * u
    return 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0


def setup_camera_rig(scene, cam_spec, total_frames):
    """Focus-target empty + DoF camera on a keyframed eased orbit."""
    cam_spec = cam_spec or {}
    target = cam_spec.get("target_pos", [0.0, 0.0, 0.0])
    focal = float(cam_spec.get("focal_length_mm", 50))
    fstop = float(cam_spec.get("aperture_fstop", 2.8))
    radius_start = float(cam_spec.get("radius_start", 9.0))
    radius_end = float(cam_spec.get("radius_end", 6.0))
    azimuth_start = float(cam_spec.get("azimuth_start_deg", -38.0))
    azimuth_end = float(cam_spec.get("azimuth_end_deg", 40.0))
    elevation = math.radians(float(cam_spec.get("elevation_deg", 24.0)))

    empty = bpy.data.objects.new("Focus_Target_Empty", None)
    _try_set(empty, "empty_display_type", "SPHERE")
    empty.location = (float(target[0]), float(target[1]), float(target[2]))
    scene.collection.objects.link(empty)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = focal
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = empty
    cam_data.dof.aperture_fstop = fstop
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    cam_obj.location = (0.0, -radius_start, 3.0)
    scene.collection.objects.link(cam_obj)
    constraint = cam_obj.constraints.new("TRACK_TO")
    constraint.target = empty
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    scene.camera = cam_obj

    n = max(1, int(total_frames))
    for frame in range(1, n + 1):
        u = (frame - 1) / max(1, n - 1)
        eased = _cubic_ease_in_out(u)
        azimuth = math.radians(azimuth_start + (azimuth_end - azimuth_start) * eased)
        radius = radius_start + (radius_end - radius_start) * eased
        cam_obj.location = (
            radius * math.cos(elevation) * math.sin(azimuth),
            -radius * math.cos(elevation) * math.cos(azimuth),
            radius * math.sin(elevation),
        )
        cam_obj.keyframe_insert(data_path="location", frame=frame)
    return cam_obj


_LAYER_SPECS = [
    {
        "anchor_id": "anchor_substrate",
        "name": "Package Substrate",
        "z": -0.65,
        "size": (2.2, 2.2, 0.14),
        "base_hex": "#0F172A",
        "metallic": 0.3,
        "roughness": 0.4,
        "emission_hex": "#0F172A",
        "emission_strength": 0.0,
        "exp_dz": -0.55,
    },
    {
        "anchor_id": "anchor_interposer",
        "name": "CoWoS HBM3e Interposer",
        "z": -0.20,
        "size": (1.65, 1.65, 0.09),
        "base_hex": "#FACC15",
        "metallic": 0.95,
        "roughness": 0.15,
        "emission_hex": "#FACC15",
        "emission_strength": 0.4,
        "exp_dz": -0.15,
    },
    {
        "anchor_id": "anchor_compute_die",
        "name": "5nm AI Compute Die",
        "z": 0.20,
        "size": (1.15, 1.15, 0.12),
        "base_hex": "#38BDF8",
        "metallic": 0.9,
        "roughness": 0.1,
        "emission_hex": "#38BDF8",
        "emission_strength": 2.2,
        "exp_dz": 0.25,
    },
    {
        "anchor_id": "anchor_vapor_chamber",
        "name": "3D Vapor Chamber Fins",
        "z": 0.70,
        "size": (2.0, 2.0, 0.22),
        "base_hex": "#334155",
        "metallic": 0.88,
        "roughness": 0.25,
        "emission_hex": "#334155",
        "emission_strength": 0.0,
        "exp_dz": 0.75,
    },
]


def _new_beveled_cube(name, z, size):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, z))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (float(size[0]), float(size[1]), float(size[2]))
    try:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    except Exception:  # noqa: S110,BLE001 - unscaled cube still renders fine
        pass
    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = 0.03
    bevel.segments = 3
    return obj


def _keyframe_explode(obj, base_z, exp_dz, explode_amp, total_frames):
    n = max(1, int(total_frames))
    for frame in range(1, n + 1):
        u = (frame - 1) / max(1, n - 1)
        pulse = math.sin(u * math.pi) * explode_amp
        obj.location = (0.0, 0.0, base_z + exp_dz * pulse)
        obj.keyframe_insert(data_path="location", frame=frame)


def _create_anchor_empties(scene, spec, base_map=None):
    anchors = dict(base_map or {})
    for anchor in spec.get("anchors_3d", []) or []:
        if not isinstance(anchor, dict):
            continue
        anchor_id = anchor.get("anchor_id")
        if not anchor_id:
            continue
        anchor_id = str(anchor_id)
        if anchor_id in anchors:
            continue
        local = anchor.get("local_pos", [0.0, 0.0, 0.0])
        empty = bpy.data.objects.new(anchor_id, None)
        _try_set(empty, "empty_display_type", "SPHERE")
        _try_set(empty, "empty_display_size", 0.15)
        empty.location = tuple(float(c) for c in local[:3])
        scene.collection.objects.link(empty)
        anchors[anchor_id] = empty
    return anchors


def build_exploded_hardware_3d(scene, spec, total_frames) -> "dict[str, Object]":
    """Four beveled layer cubes with a sinusoidal explode; returns anchor map."""
    explode_amp = float((spec or {}).get("explode_factor", 1.0))
    n = max(1, int(total_frames))
    layer_objects = {}
    for layer in _LAYER_SPECS:
        obj = _new_beveled_cube(layer["name"], layer["z"], layer["size"])
        material = create_pbr_material(
            f"{layer['name']} Material",
            layer["base_hex"],
            metallic=layer["metallic"],
            roughness=layer["roughness"],
            emission_hex=layer["emission_hex"],
            emission_strength=layer["emission_strength"],
            transmission=0.0,
            coat=0.0,
        )
        obj.data.materials.append(material)
        _keyframe_explode(obj, layer["z"], layer["exp_dz"], explode_amp, n)
        layer_objects[layer["anchor_id"]] = obj
    return _create_anchor_empties(scene, spec or {}, layer_objects)


def build_orbital_or_field_3d(scene, spec, total_frames) -> "dict[str, Object]":
    """Plasma torus + 12 twisted coil tori on a rig; returns anchor map."""
    n = max(1, int(total_frames))

    bpy.ops.mesh.primitive_torus_add(
        major_radius=1.65, minor_radius=0.38, location=(0.0, 0.0, 0.0)
    )
    plasma = bpy.context.active_object
    plasma.name = "Plasma_Torus"
    plasma_mat = create_pbr_material(
        "Plasma Material",
        "#38BDF8",
        metallic=0.2,
        roughness=0.3,
        emission_hex="#38BDF8",
        emission_strength=4.5,
        transmission=0.0,
        coat=0.0,
    )
    plasma.data.materials.append(plasma_mat)
    for frame in range(1, n + 1):
        u = (frame - 1) / max(1, n - 1)
        plasma.rotation_euler = (0.0, 0.0, u * 2.0 * math.pi)
        plasma.keyframe_insert(data_path="rotation_euler", frame=frame)

    rig = bpy.data.objects.new("Coil_Rig_Empty", None)
    _try_set(rig, "empty_display_type", "PLAIN_AXES")
    scene.collection.objects.link(rig)

    coil_count = 12
    for index in range(coil_count):
        angle = index * (2.0 * math.pi / coil_count)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.62,
            minor_radius=0.055,
            location=(1.65 * math.cos(angle), 1.65 * math.sin(angle), 0.0),
        )
        coil = bpy.context.active_object
        coil.name = f"Coil_{index + 1:02d}"
        coil.rotation_euler = (
            math.radians(90.0),
            math.sin(3.0 * angle) * 0.35,
            angle + math.pi / 2.0,
        )
        coil_mat = create_pbr_material(
            f"Coil Material {index + 1:02d}",
            "#F59E0B",
            metallic=0.92,
            roughness=0.3,
            emission_hex="#F59E0B",
            emission_strength=0.8,
            transmission=0.0,
            coat=0.0,
        )
        coil.data.materials.append(coil_mat)
        coil.parent = rig

    base_map = {"plasma_torus": plasma, "coil_rig": rig}
    return _create_anchor_empties(scene, spec or {}, base_map)


_SERPENT_POINTS = 26
_SERPENT_TAIL_RADIUS = 0.10
_SERPENT_BODY_RADIUS = 0.30
_SERPENT_HEAD_BULGE = 0.06
_SERPENT_HEAD_BULGE_U = 0.90
_SERPENT_HEAD_BULGE_WIDTH = 0.08


def _serpent_spine(u, phase):
    """Point on the S-shaped spine in rig-local space for arc position ``u``.

    ``phase`` (radians) advances the travelling wave; geometry is deterministic
    for a given (u, phase) pair, so it is safe to keyframe per frame.
    """
    x = 0.85 * math.sin(3.2 * math.pi * u + phase) * (0.55 + 0.45 * u)
    y = -0.25 + 0.45 * math.cos(2.1 * math.pi * u + phase * 0.5)
    z = -1.25 + 2.5 * u
    return (x, y, z)


def _serpent_radius(u):
    """Tail -> head taper (0.10 -> 0.30) with a subtle bulge near the head."""
    base = _SERPENT_TAIL_RADIUS + (_SERPENT_BODY_RADIUS - _SERPENT_TAIL_RADIUS) * u
    bulge = _SERPENT_HEAD_BULGE * math.exp(
        -(((u - _SERPENT_HEAD_BULGE_U) / _SERPENT_HEAD_BULGE_WIDTH) ** 2)
    )
    return base + bulge


def _serpent_anchor_u(anchor_id):
    """Pick a spine arc position for an anchor whose ``local_pos`` is absent."""
    lowered = str(anchor_id).lower()
    if "head" in lowered:
        return 1.0
    if "tail" in lowered:
        return 0.0
    return 0.5


def build_organic_serpent_3d(scene, spec, total_frames) -> "dict[str, Object]":
    """Animated jade serpent: tapered curve spine + gold head rig; anchor map."""
    n = max(1, int(total_frames))

    # Whole-body sway on a parent rig; all body parts are authored in rig-local
    # coordinates, so a single rotation keeps them aligned with their anchors.
    rig = bpy.data.objects.new("Serpent_Rig_Empty", None)
    _try_set(rig, "empty_display_type", "PLAIN_AXES")
    scene.collection.objects.link(rig)
    for frame in range(1, n + 1):
        u = (frame - 1) / max(1, n - 1)
        rig.rotation_euler = (0.0, 0.0, 0.12 * math.sin(2.0 * math.pi * u))
        rig.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Tapered S-shaped body as a single POLY spline with a bevel. The per-point
    # coordinates are keyframed each frame to produce a travelling undulation.
    curve = bpy.data.curves.new("Serpent_Spine", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 8
    curve.bevel_depth = 0.3
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    spline.points.add(_SERPENT_POINTS - 1)
    for index, point in enumerate(spline.points):
        point.radius = _serpent_radius(index / (_SERPENT_POINTS - 1))
    body = bpy.data.objects.new("Organic_Serpent_Body", curve)
    scene.collection.objects.link(body)
    body.parent = rig
    jade = create_pbr_material(
        "Jade Serpent Material",
        "#047857",
        metallic=0.15,
        roughness=0.35,
        emission_hex="#34D399",
        emission_strength=0.35,
        transmission=0.0,
        coat=0.0,
    )
    curve.materials.append(jade)

    # Head empty follows the head spine point (rig-local), carrying the face.
    head = bpy.data.objects.new("Serpent_Head_Empty", None)
    _try_set(head, "empty_display_type", "SPHERE")
    _try_set(head, "empty_display_size", 0.12)
    scene.collection.objects.link(head)
    head.parent = rig

    for frame in range(1, n + 1):
        u_norm = (frame - 1) / max(1, n - 1)
        phase = 2.0 * math.pi * u_norm
        for index, point in enumerate(spline.points):
            x, y, z = _serpent_spine(index / (_SERPENT_POINTS - 1), phase)
            point.co = (x, y, z, 1.0)
            point.keyframe_insert(data_path="co", frame=frame)
        hx, hy, hz = _serpent_spine(1.0, phase)
        head.location = (hx, hy, hz)
        head.keyframe_insert(data_path="location", frame=frame)

    gold = create_pbr_material(
        "Serpent Head Gold",
        "#FBBF24",
        metallic=0.85,
        roughness=0.25,
        emission_hex="#F59E0B",
        emission_strength=0.5,
        transmission=0.0,
        coat=0.0,
    )
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1.0)
    head_mesh = bpy.context.active_object
    head_mesh.name = "Serpent_Head"
    head_mesh.scale = (0.34, 0.30, 0.30)
    head_mesh.parent = head
    head_mesh.data.materials.append(gold)

    eye_mat = create_pbr_material(
        "Serpent Eye Material",
        "#34D399",
        metallic=0.0,
        roughness=0.15,
        emission_hex="#6EE7B7",
        emission_strength=3.0,
        transmission=0.0,
        coat=0.0,
    )
    for side, label in ((-1, "L"), (1, "R")):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=1.0)
        eye = bpy.context.active_object
        eye.name = f"Serpent_Eye_{label}"
        eye.scale = (0.04, 0.04, 0.04)
        eye.location = (0.22, side * 0.16, 0.14)
        eye.parent = head
        eye.data.materials.append(eye_mat)

    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.02, depth=0.34)
    tongue = bpy.context.active_object
    tongue.name = "Serpent_Tongue"
    tongue.location = (0.34, 0.0, -0.02)
    tongue.rotation_euler = (0.0, math.pi / 2.0, 0.0)
    tongue.parent = head
    tongue_mat = create_pbr_material(
        "Serpent Tongue Material",
        "#F43F5E",
        metallic=0.0,
        roughness=0.4,
        emission_hex="#F43F5E",
        emission_strength=1.5,
        transmission=0.0,
        coat=0.0,
    )
    tongue.data.materials.append(tongue_mat)

    anchors = {}
    for anchor in (spec or {}).get("anchors_3d", []) or []:
        if not isinstance(anchor, dict):
            continue
        anchor_id = anchor.get("anchor_id")
        if not anchor_id:
            continue
        anchor_id = str(anchor_id)
        empty = bpy.data.objects.new(anchor_id, None)
        _try_set(empty, "empty_display_type", "SPHERE")
        _try_set(empty, "empty_display_size", 0.15)
        scene.collection.objects.link(empty)
        empty.parent = rig
        local = anchor.get("local_pos")
        if local is not None:
            empty.location = tuple(float(c) for c in local[:3])
        else:
            target_u = _serpent_anchor_u(anchor_id)
            for frame in range(1, n + 1):
                u_norm = (frame - 1) / max(1, n - 1)
                phase = 2.0 * math.pi * u_norm
                x, y, z = _serpent_spine(target_u, phase)
                empty.location = (x, y, z)
                empty.keyframe_insert(data_path="location", frame=frame)
        anchors[anchor_id] = empty
    return anchors


def export_anchor_tracks(
    scene,
    cam_obj,
    spec,
    anchor_objs,
    total_frames,
    out_json_path,
):
    """Project every anchor to camera space per frame; dump JSON."""
    if not INSIDE_BLENDER:
        raise RuntimeError(
            "export_anchor_tracks must run inside Blender via `blender -b -P`"
        )
    anchor_objs = anchor_objs or {}
    anchor_defs = (spec or {}).get("anchors_3d", []) or []
    n = max(1, int(total_frames))
    view_layer = scene.view_layers[0]
    frames_out = []
    for frame in range(1, n + 1):
        scene.frame_set(frame)
        view_layer.update()
        anchor_entries = []
        for anchor in anchor_defs:
            if not isinstance(anchor, dict):
                continue
            anchor_id = anchor.get("anchor_id")
            if not anchor_id:
                continue
            anchor_id = str(anchor_id)
            obj = anchor_objs.get(anchor_id)
            if obj is not None:
                world_pos = obj.matrix_world.translation.copy()
            else:
                local = anchor.get("local_pos", [0.0, 0.0, 0.0])
                world_pos = Vector((float(local[0]), float(local[1]), float(local[2])))
            co = world_to_camera_view(scene, cam_obj, world_pos)
            u_raw, v_raw, z_raw = co.x, 1.0 - co.y, co.z
            visible = z_raw > 0.0 and 0.02 <= u_raw <= 0.98 and 0.02 <= v_raw <= 0.98
            anchor_entries.append(
                {
                    "anchor_id": anchor_id,
                    "u": round(u_raw, 5),
                    "v": round(v_raw, 5),
                    "z_depth": round(z_raw, 4),
                    "visible": bool(visible),
                }
            )
        frames_out.append({"frame": frame, "anchors": anchor_entries})
    payload = {"total_frames": n, "frames": frames_out}
    out_path = Path(out_json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def run_blender_scene(spec_path, out_dir, width, height, fps, total_frames):
    """Build the scene, export anchor tracks, render the animation."""
    if not INSIDE_BLENDER:
        raise RuntimeError(
            "run_blender_scene must run via `blender -b -P`, e.g. "
            "`blender -b -P scripts/blender_runner.py -- --spec spec.json "
            "--out-dir build/scene --width 1920 --height 1080 --fps 30 "
            "--frames 60`; it cannot run under a plain Python interpreter"
        )
    spec = json.loads(Path(spec_path).read_text())
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    configure_render_pipeline(
        scene,
        width,
        height,
        fps,
        total_frames,
        engine_pref=spec.get("engine_pref", "AUTO_EEVEE"),
        transparent_bg=bool(spec.get("transparent_bg", False)),
    )
    setup_lighting_and_world(
        scene, preset=spec.get("lighting_preset", "cyber_studio_volumetric")
    )
    cam_spec = spec.get("camera") or {}
    cam_obj = setup_camera_rig(scene, cam_spec, total_frames)

    category = spec.get("category")
    if category == "orbital_or_field_3d":
        anchor_objs = build_orbital_or_field_3d(scene, spec, total_frames)
    elif category == "organic_serpent_3d":
        anchor_objs = build_organic_serpent_3d(scene, spec, total_frames)
    elif category in UNIMPLEMENTED_CATEGORIES:
        raise NotImplementedError(
            f"Category {category!r} is not implemented in blender_runner.py. "
            f"Supported categories: {', '.join(SUPPORTED_CATEGORIES)}"
        )
    else:
        anchor_objs = build_exploded_hardware_3d(scene, spec, total_frames)

    tracks_path = out_dir / "anchor_tracks.json"
    export_anchor_tracks(scene, cam_obj, spec, anchor_objs, total_frames, tracks_path)

    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(out_dir / "frame_")
    bpy.ops.render.render(animation=True)
    return tracks_path


if __name__ == "__main__":
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(
        description="Standalone headless Blender scene renderer "
        "(run via `blender -b -P scripts/blender_runner.py -- ...`)."
    )
    parser.add_argument("--spec", required=True, help="Path to the scene spec JSON")
    parser.add_argument("--out-dir", required=True, help="Output directory for frames")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        run_blender_scene(
            args.spec, args.out_dir, args.width, args.height, args.fps, args.frames
        )
    except Exception:  # noqa: BLE001 - top-level: report and exit non-zero
        import traceback

        traceback.print_exc()
        sys.exit(1)
