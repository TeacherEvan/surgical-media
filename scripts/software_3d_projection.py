#!/usr/bin/env python3
"""software_3d_projection.py — math-mirror of Blender's Track-To camera +
``bpy_extras.object_utils.world_to_camera_view``.

Renders parametric 3D meshes (exploded hardware stack / stellarator torus)
with a 4x4 look-at view matrix, perspective divide, Painter's-algorithm Z
sort and Blinn-Phong-ish diffuse shading in pure Python (stdlib + Pillow
via the repo canvas — no numpy); returns screen-space anchor tracks for the
HUD compositor in ``hybrid_compositor.py``.

Design notes:

- Coordinates entering the canvas are *design-space* pixels (target
  resolution). Normalized ``u, v`` from :meth:`PerspectiveCamera3D.project_point`
  are multiplied by ``canvas.width`` / ``canvas.height`` at the call site.
- ``v`` uses a top-left origin (``v = 0.5 - 0.5 * ndc_y``), matching the repo
  canvas convention (y grows downward).
- Colors are opaque RGB hex strings pre-blended against a dark canvas; there
  is no alpha compositing anywhere in this pipeline.
- Stdlib only. No numpy, no trimesh.
"""

from __future__ import annotations

import math

from canvas import parse_color
from scene_router import CAMERA_3D_DEFAULTS

SUPPORTED_CATEGORIES = ("exploded_hardware_3d", "orbital_or_field_3d")

_ZNEAR = 0.15
_POLY_ZNEAR = 0.2


# ---------------------------------------------------------------------------
# Minimal 3-vector helpers (plain tuples — no numpy)
# ---------------------------------------------------------------------------
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a):
    length = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if length <= 0.0:
        raise ValueError("cannot normalize a zero-length vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _rotate_z(pt, angle: float):
    c, s = math.cos(angle), math.sin(angle)
    return (pt[0] * c - pt[1] * s, pt[0] * s + pt[1] * c, pt[2])


def _clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else (min(t, 1.0))


def _cubic_ease_in_out(u: float) -> float:
    return 4.0 * u * u * u if u < 0.5 else 1.0 - math.pow(-2.0 * u + 2.0, 3) / 2.0


class PerspectiveCamera3D:
    """Look-at (Track-To) perspective camera.

    Mirrors Blender's *Track To* constraint feeding
    ``bpy_extras.object_utils.world_to_camera_view``: a 4x4 look-at view
    matrix is built from ``forward``/``right``/``true_up``, vertices are
    transformed into camera space, divided by depth, and mapped to
    normalized ``u, v`` with a top-left origin.
    """

    def __init__(
        self,
        eye,
        target=(0.0, 0.0, 0.0),
        up=(0.0, 0.0, 1.0),
        focal_length_mm: float = 50.0,
        sensor_width_mm: float = 36.0,
        aspect_ratio: float = 16.0 / 9.0,
    ) -> None:
        self.eye = (float(eye[0]), float(eye[1]), float(eye[2]))
        self.target = (float(target[0]), float(target[1]), float(target[2]))
        self.up = (float(up[0]), float(up[1]), float(up[2]))
        self.focal_length_mm = float(focal_length_mm)
        self.sensor_width_mm = float(sensor_width_mm)
        self.aspect_ratio = float(aspect_ratio) or 1.0

        fov_x = 2.0 * math.atan(self.sensor_width_mm / (2.0 * self.focal_length_mm))
        self.fov_x = fov_x
        self.f_scale = 1.0 / math.tan(fov_x / 2.0)

        self.forward = _norm(_sub(self.target, self.eye))
        self.right = _norm(_cross(self.forward, self.up))
        self.true_up = _cross(self.right, self.forward)

        # 4x4 look-at view matrix: rows are the camera basis + translation.
        self.view_matrix = (
            (self.right[0], self.right[1], self.right[2], -_dot(self.right, self.eye)),
            (
                self.true_up[0],
                self.true_up[1],
                self.true_up[2],
                -_dot(self.true_up, self.eye),
            ),
            (
                self.forward[0],
                self.forward[1],
                self.forward[2],
                -_dot(self.forward, self.eye),
            ),
            (0.0, 0.0, 0.0, 1.0),
        )

    def project_point(self, pt) -> tuple[float, float, float, bool]:
        """Project a world-space point → (u, v, z_depth, visible).

        ``u, v`` are normalized device coordinates with a top-left origin
        (``v`` grows downward), matching the repo canvas convention. Points
        at or behind ``z_cam <= 0.15`` collapse to screen center and are
        reported invisible.
        """
        m = self.view_matrix
        x, y, z = pt
        x_cam = m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3]
        y_cam = m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3]
        z_cam = m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]

        if z_cam <= _ZNEAR:
            return (0.5, 0.5, z_cam, False)
        ndc_x = x_cam / z_cam * self.f_scale
        ndc_y = y_cam / z_cam * self.f_scale * self.aspect_ratio
        u = 0.5 + 0.5 * ndc_x
        v = 0.5 - 0.5 * ndc_y
        visible = z_cam > _ZNEAR and 0.02 <= u <= 0.98 and 0.02 <= v <= 0.98
        return (u, v, z_cam, visible)


# ---------------------------------------------------------------------------
# Parametric mesh generators
# ---------------------------------------------------------------------------
def generate_box_mesh(
    center, scale, color_hex, edge_hex, emissive: bool = False
) -> list[dict]:
    """Axis-aligned box mesh with hardcoded outward quad normals.

    ``scale`` is the full (x, y, z) size. Returns 6 faces, each
    ``{"verts": [4 tuples], "normal": (x, y, z), "color_hex": ...,
    "edge_hex": ..., "emissive": bool}``.
    """
    cx, cy, cz = (float(v) for v in center)
    hx, hy, hz = (float(v) * 0.5 for v in scale)
    v000 = (cx - hx, cy - hy, cz - hz)
    v100 = (cx + hx, cy - hy, cz - hz)
    v110 = (cx + hx, cy + hy, cz - hz)
    v010 = (cx - hx, cy + hy, cz - hz)
    v001 = (cx - hx, cy - hy, cz + hz)
    v101 = (cx + hx, cy - hy, cz + hz)
    v111 = (cx + hx, cy + hy, cz + hz)
    v011 = (cx - hx, cy + hy, cz + hz)
    faces = [
        ((v000, v100, v110, v010), (0.0, 0.0, -1.0)),  # bottom
        ((v001, v101, v111, v011), (0.0, 0.0, 1.0)),  # top
        ((v000, v100, v101, v001), (0.0, -1.0, 0.0)),  # front (y-)
        ((v100, v110, v111, v101), (1.0, 0.0, 0.0)),  # right (x+)
        ((v110, v010, v011, v111), (0.0, 1.0, 0.0)),  # back (y+)
        ((v010, v000, v001, v011), (-1.0, 0.0, 0.0)),  # left (x-)
    ]
    return [
        {
            "verts": list(verts),
            "normal": normal,
            "color_hex": color_hex,
            "edge_hex": edge_hex,
            "emissive": bool(emissive),
        }
        for verts, normal in faces
    ]


def generate_torus_stellarator_mesh(t_norm: float) -> list[dict]:
    """Parametric stellarator torus with highlighted field coils.

    ``R = 1.65``, ``r = 0.36``, 32 major x 14 minor segments. The whole
    torus is rotated about z by ``rot_z = t_norm * pi * 1.5``. Every major
    segment where ``i % 3 == 0`` is a *coil*: ``r_eff = r * 1.28`` with a
    helical ``twist = 0.25 * sin(3 * u0)`` phase shift on the poloidal
    angle, colour #F59E0B / edge #FDE047 and always emissive. Plasma quads
    are #0284C7 / #38BDF8 and emissive when ``j % 4 == 0``.

    Per-quad normals use the un-twisted analytic torus normal direction
    ``(cos(v0)cos(u0), cos(v0)sin(u0), sin(v0))`` — good enough for a
    Blinn-Phong-ish diffuse term and documented as approximate: it ignores
    the coil twist and the quad's two-axis curvature.
    """
    big_r, small_r = 1.65, 0.36
    n_maj, n_min = 32, 14
    rot_z = _clamp01(float(t_norm)) * math.pi * 1.5

    def tor_point(u: float, v: float, r_eff: float, coil: bool):
        twist = 0.25 * math.sin(3.0 * u) if coil else 0.0
        vv = v + twist
        pt = (
            (big_r + r_eff * math.cos(vv)) * math.cos(u),
            (big_r + r_eff * math.cos(vv)) * math.sin(u),
            r_eff * math.sin(vv),
        )
        return _rotate_z(pt, rot_z)

    polys: list[dict] = []
    for i in range(n_maj):
        u0 = 2.0 * math.pi * i / n_maj
        u1 = 2.0 * math.pi * (i + 1) / n_maj
        is_coil = i % 3 == 0
        r_eff = small_r * 1.28 if is_coil else small_r
        color_hex = "#F59E0B" if is_coil else "#0284C7"
        edge_hex = "#FDE047" if is_coil else "#38BDF8"
        for j in range(n_min):
            v0 = 2.0 * math.pi * j / n_min
            v1 = 2.0 * math.pi * (j + 1) / n_min
            verts = [
                tor_point(u0, v0, r_eff, is_coil),
                tor_point(u1, v0, r_eff, is_coil),
                tor_point(u1, v1, r_eff, is_coil),
                tor_point(u0, v1, r_eff, is_coil),
            ]
            normal = _rotate_z(
                (
                    math.cos(v0) * math.cos(u0),
                    math.cos(v0) * math.sin(u0),
                    math.sin(v0),
                ),
                rot_z,
            )
            emissive = True if is_coil else (j % 4 == 0)
            polys.append(
                {
                    "verts": verts,
                    "normal": _norm(normal),
                    "color_hex": color_hex,
                    "edge_hex": edge_hex,
                    "emissive": emissive,
                }
            )
    return polys


# ---------------------------------------------------------------------------
# Scene render + anchor tracking
# ---------------------------------------------------------------------------
def _exploded_layers(t_norm: float, explode_factor: float):
    amp = explode_factor * math.sin(min(1.0, t_norm * 1.15) * math.pi * 0.65)
    return [
        (
            "anchor_substrate",
            (0.0, 0.0, -0.52 - 0.32 * amp),
            (2.25, 2.25, 0.14),
            "#0F172A",
            "#A78BFA",
            False,
        ),
        (
            "anchor_interposer",
            (0.0, 0.0, -0.16 - 0.10 * amp),
            (1.80, 1.80, 0.10),
            "#064E3B",
            "#34D399",
            True,
        ),
        (
            "anchor_compute_die",
            (0.0, 0.0, 0.18 + 0.14 * amp),
            (1.30, 1.30, 0.13),
            "#78350F",
            "#FACC15",
            True,
        ),
        (
            "anchor_vapor_chamber",
            (0.0, 0.0, 0.56 + 0.36 * amp),
            (2.05, 2.05, 0.18),
            "#0C4A6E",
            "#38BDF8",
            True,
        ),
    ]


def _build_scene(scene_spec: dict, t_norm: float):
    """Return (polys, dynamic_anchor_pos); raise on unsupported categories."""
    category = scene_spec.get("category")
    if category == "exploded_hardware_3d":
        explode_factor = float(scene_spec.get("explode_factor", 1.0))
        polys: list[dict] = []
        dynamic_anchor_pos: dict[str, tuple[float, float, float]] = {}
        for anchor_id, center, scale, color, edge, emissive in _exploded_layers(
            t_norm, explode_factor
        ):
            polys.extend(generate_box_mesh(center, scale, color, edge, emissive))
            px, py, pz = center
            sx, sy, _ = scale
            dynamic_anchor_pos[anchor_id] = (px + sx * 0.42, py - sy * 0.42, pz)
        return polys, dynamic_anchor_pos
    if category == "orbital_or_field_3d":
        # Torus anchors fall back to scene_spec local_pos (no per-part handles).
        return generate_torus_stellarator_mesh(t_norm), {}
    raise NotImplementedError(
        f"unsupported 3D scene category {category!r}; "
        f"supported categories: {', '.join(SUPPORTED_CATEGORIES)}"
    )


def render_3d_scene_and_track(canvas, scene_spec: dict, t_norm: float) -> list[dict]:
    """Render the parametric 3D scene and return tracked anchor screen positions.

    ``scene_spec`` keys: ``category`` (``"exploded_hardware_3d"`` or
    ``"orbital_or_field_3d"`` — anything else raises :class:`NotImplementedError`),
    ``camera_3d`` (``radius_start``/``radius_end``/``azimuth_start_deg``/
    ``azimuth_end_deg``/``elevation_deg``/``focal_length_mm``),
    ``explode_factor`` (exploded stack only) and ``anchors_3d`` (list of
    ``{anchor_id, label, metric, accent_hex?, local_pos}``).

    Anchor dicts are ``{anchor_id, label, metric, accent_hex, u, v, z_depth,
    visible}`` with raw floats, ready for ``hybrid_compositor``.
    """
    t_norm = _clamp01(float(t_norm))
    w, h = canvas.width, canvas.height

    cam_cfg = scene_spec.get("camera_3d", {})
    r0 = float(cam_cfg.get("radius_start", CAMERA_3D_DEFAULTS["radius_start"]))
    r1 = float(cam_cfg.get("radius_end", CAMERA_3D_DEFAULTS["radius_end"]))
    az0 = math.radians(
        float(cam_cfg.get("azimuth_start_deg", CAMERA_3D_DEFAULTS["azimuth_start_deg"]))
    )
    az1 = math.radians(
        float(cam_cfg.get("azimuth_end_deg", CAMERA_3D_DEFAULTS["azimuth_end_deg"]))
    )
    elev = math.radians(
        float(cam_cfg.get("elevation_deg", CAMERA_3D_DEFAULTS["elevation_deg"]))
    )
    focal = float(cam_cfg.get("focal_length_mm", CAMERA_3D_DEFAULTS["focal_length_mm"]))

    u_ease = _cubic_ease_in_out(t_norm)
    radius = r0 + (r1 - r0) * u_ease
    az = az0 + (az1 - az0) * u_ease
    eye = (
        radius * math.cos(elev) * math.sin(az),
        -radius * math.cos(elev) * math.cos(az),
        radius * math.sin(elev),
    )
    cam = PerspectiveCamera3D(
        eye=eye, focal_length_mm=focal, aspect_ratio=w / max(1, h)
    )

    # Perspective ground grid at z = -1.25 (pre-blended stroke, no alpha).
    grid_z = -1.25
    for g in range(-3, 4):
        for p0, p1 in (
            ((g * 0.9, -2.7, grid_z), (g * 0.9, 2.7, grid_z)),
            ((-2.7, g * 0.9, grid_z), (2.7, g * 0.9, grid_z)),
        ):
            s0 = cam.project_point(p0)
            s1 = cam.project_point(p1)
            if not (s0[3] and s1[3]):
                continue  # both off-frustum endpoints — skip the line
            canvas.line(
                (s0[0] * w, s0[1] * h), (s1[0] * w, s1[1] * h), "#0E2A3F", width=1.4
            )

    polys, dynamic_anchor_pos = _build_scene(scene_spec, t_norm)

    # Project every vertex; skip near/behind-plane polys; Painter's sort.
    light_dir = _norm((0.55, -0.45, 0.70))
    draw_list = []
    for poly in polys:
        projected = [cam.project_point(v) for v in poly["verts"]]
        if any(p[2] <= _POLY_ZNEAR for p in projected):
            continue
        avg_depth = sum(p[2] for p in projected) / len(projected)
        draw_list.append((avg_depth, poly, projected))
    draw_list.sort(key=lambda item: item[0], reverse=True)  # far first

    for _, poly, projected in draw_list:
        points = [(p[0] * w, p[1] * h) for p in projected]
        ndotl = max(0.0, _dot(poly["normal"], light_dir))
        intensity = 0.38 + 0.62 * ndotl
        r, g, b = parse_color(poly["color_hex"])[:3]
        shaded = (
            min(255, int(r * intensity)),
            min(255, int(g * intensity)),
            min(255, int(b * intensity)),
        )
        canvas.polygon(points, outline=poly["edge_hex"], fill=shaded)
        if poly["emissive"]:
            canvas.bloom_polygon(points, outline=poly["edge_hex"])

    tracked: list[dict] = []
    for a_def in scene_spec.get("anchors_3d", []):
        anchor_id = a_def["anchor_id"]
        local = a_def.get("local_pos", (0.0, 0.0, 0.0))
        w_pos = dynamic_anchor_pos.get(anchor_id, tuple(local))
        u, v, z_depth, visible = cam.project_point(w_pos)
        tracked.append(
            {
                "anchor_id": anchor_id,
                "label": a_def.get("label", anchor_id),
                "metric": a_def.get("metric", ""),
                "accent_hex": a_def.get("accent_hex", "#38BDF8"),
                "u": u,
                "v": v,
                "z_depth": z_depth,
                "visible": visible,
            }
        )
    return tracked
