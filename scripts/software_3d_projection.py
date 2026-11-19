#!/usr/bin/env python3
"""software_3d_projection.py — math-mirror of Blender's Track-To camera +
``bpy_extras.object_utils.world_to_camera_view``.

Renders parametric 3D meshes (exploded hardware stack / stellarator torus /
living serpent) with a 4x4 look-at view matrix, perspective divide, Painter's-algorithm Z
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
from typing import TYPE_CHECKING, Any

from canvas import parse_color
from scene_router import CAMERA_3D_DEFAULTS

if TYPE_CHECKING:
    from canvas import SupersampledCanvas

SUPPORTED_CATEGORIES = (
    "exploded_hardware_3d",
    "orbital_or_field_3d",
    "organic_serpent_3d",
    "network_topology_3d",
    "external_asset_3d",
)

_ZNEAR = 0.15
_POLY_ZNEAR = 0.2

Vec3 = tuple[float, float, float]
MeshFace = dict[str, Any]


# ---------------------------------------------------------------------------
# Minimal 3-vector helpers (plain tuples — no numpy)
# ---------------------------------------------------------------------------
def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> Vec3:
    length = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if length <= 0.0:
        raise ValueError("cannot normalize a zero-length vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _rotate_z(pt: Vec3, angle: float) -> Vec3:
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
        eye: Vec3,
        target: Vec3 = (0.0, 0.0, 0.0),
        up: Vec3 = (0.0, 0.0, 1.0),
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

    def project_point(self, pt: Vec3) -> tuple[float, float, float, bool]:
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
    center: Vec3, scale: Vec3, color_hex: str, edge_hex: str, emissive: bool = False
) -> list[MeshFace]:
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


def generate_torus_stellarator_mesh(t_norm: float) -> list[MeshFace]:
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

    def tor_point(u: float, v: float, r_eff: float, coil: bool) -> Vec3:
        twist = 0.25 * math.sin(3.0 * u) if coil else 0.0
        vv = v + twist
        pt = (
            (big_r + r_eff * math.cos(vv)) * math.cos(u),
            (big_r + r_eff * math.cos(vv)) * math.sin(u),
            r_eff * math.sin(vv),
        )
        return _rotate_z(pt, rot_z)

    polys: list[MeshFace] = []
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


def serpent_spine_point(u: float, t_norm: float) -> tuple[float, float, float]:
    """World-space point on the living snake's open S-curve spine.

    ``u`` in [0, 1] runs tail (0) → head (1); ``t_norm`` in [0, 1] drives the
    undulation via ``phase = t_norm * 2*pi``. Shared by the mesh generator and
    the anchor tracker so HUD handles follow the exact body they annotate.
    """
    u = _clamp01(float(u))
    phase = _clamp01(float(t_norm)) * 2.0 * math.pi
    x = 0.85 * math.sin(3.2 * math.pi * u + phase) * (0.55 + 0.45 * u)
    y = -0.25 + 0.45 * math.cos(2.1 * math.pi * u + phase * 0.5)
    z = -1.25 + 2.5 * u
    return (x, y, z)


def generate_serpent_mesh(t_norm: float) -> list[MeshFace]:
    """Parametric *living snake* tube — an open, tapering S-spine, NOT a ring.

    26 rings × 8 sides sweep a circular cross-section along the open spine
    returned by :func:`serpent_spine_point`. The radius tapers from ~0.10 at
    the tail to ~0.30 at the body with a gaussian bulge to ~0.36 near the head
    (``u ~= 0.9``). A stable orthonormal frame is rebuilt per ring from the
    numerically-approximated tangent with up=(0, 0, 1), and each quad's
    outward normal is the normalized ring vertex minus the spine centre.

    Jade/emerald scales use two alternating band hexes; the last few segments
    are amber/gold head accents, and two small emissive eye quads sit just in
    front of the head (all plain tuples + math, no numpy).
    """
    rings, sides = 26, 8
    up = (0.0, 0.0, 1.0)

    def radius_at(u: float) -> float:
        # tail (u=0) ~0.10 → body ~0.30 by u=0.35, plus a head bulge near u=0.9
        base = 0.10 + 0.20 * min(1.0, u / 0.35)
        bulge = 0.06 * math.exp(-(((u - 0.9) / 0.08) ** 2))
        return base + bulge

    def tangent_at(u: float) -> Vec3:
        du = 1.0e-3
        u0 = max(0.0, u - du)
        u1 = min(1.0, u + du)
        return _norm(
            _sub(serpent_spine_point(u1, t_norm), serpent_spine_point(u0, t_norm))
        )

    # Pre-compute ring vertices + outward (unit) normals for every side.
    ring_verts: list[list[tuple[float, float, float]]] = []
    ring_normals: list[list[tuple[float, float, float]]] = []
    for i in range(rings):
        u = i / (rings - 1)
        centre = serpent_spine_point(u, t_norm)
        tangent = tangent_at(u)
        right = _norm(_cross(tangent, up))
        frame_up = _norm(_cross(right, tangent))
        r = radius_at(u)
        rv: list[tuple[float, float, float]] = []
        rn: list[tuple[float, float, float]] = []
        for j in range(sides):
            theta = 2.0 * math.pi * j / sides
            n = _norm(
                (
                    math.cos(theta) * right[0] + math.sin(theta) * frame_up[0],
                    math.cos(theta) * right[1] + math.sin(theta) * frame_up[1],
                    math.cos(theta) * right[2] + math.sin(theta) * frame_up[2],
                )
            )
            rv.append(
                (
                    centre[0] + r * n[0],
                    centre[1] + r * n[1],
                    centre[2] + r * n[2],
                )
            )
            rn.append(n)
        ring_verts.append(rv)
        ring_normals.append(rn)

    polys: list[MeshFace] = []
    for i in range(rings - 1):
        is_head = i >= rings - 3  # last ~3 segments form the head
        if is_head:
            color_hex, edge_hex = "#CA8A04", "#FDE047"
        else:
            band = (i // 2) % 2
            color_hex = "#047857" if band == 0 else "#059669"
            edge_hex = "#34D399"
        for j in range(sides):
            jn = (j + 1) % sides
            verts = [
                ring_verts[i][j],
                ring_verts[i + 1][j],
                ring_verts[i + 1][jn],
                ring_verts[i][jn],
            ]
            n0, n1 = ring_normals[i][j], ring_normals[i + 1][j]
            normal = _norm((n0[0] + n1[0], n0[1] + n1[1], n0[2] + n1[2]))
            polys.append(
                {
                    "verts": verts,
                    "normal": normal,
                    "color_hex": color_hex,
                    "edge_hex": edge_hex,
                    "emissive": is_head,
                }
            )

    # Two small emissive eye quads just in front of the head (facing +x).
    hc = serpent_spine_point(0.88, t_norm)
    e = 0.055
    for side in (-1.0, 1.0):
        ex = hc[0] + 0.26
        ey = hc[1] + side * 0.13
        ez = hc[2] + 0.05
        polys.append(
            {
                "verts": [
                    (ex - e, ey - e, ez),
                    (ex + e, ey - e, ez),
                    (ex + e, ey + e, ez),
                    (ex - e, ey + e, ez),
                ],
                "normal": (1.0, 0.0, 0.0),
                "color_hex": "#0B0B0B",
                "edge_hex": "#FDE047",
                "emissive": True,
            }
        )
    return polys


def network_topology_nodes() -> list[tuple[str, Vec3, float, str, str]]:
    """World-space nodes for ``network_topology_3d`` (matches Three.js & Blender).

    Returns ``(anchor_id, position, box_size, color_hex, edge_hex)``.
    """
    nodes: list[tuple[str, Vec3, float, str, str]] = [
        ("anchor_core", (0.0, 0.0, 0.45), 0.54, "#0284C7", "#38BDF8"),
    ]
    ring_colors = [
        ("#065F46", "#34D399"),
        ("#78350F", "#FACC15"),
        ("#4C1D95", "#A78BFA"),
        ("#7F1D1D", "#FB7185"),
        ("#0C4A6E", "#38BDF8"),
    ]
    for i, (color_hex, edge_hex) in enumerate(ring_colors):
        angle = 2.0 * math.pi * i / 5.0 - math.pi / 2.0
        r = 1.85
        z = -0.30 + 0.22 * math.sin(i * 1.4)
        nodes.append(
            (
                f"anchor_edge_{i + 1}",
                (r * math.cos(angle), r * math.sin(angle), z),
                0.36,
                color_hex,
                edge_hex,
            )
        )
    return nodes


def generate_network_topology_mesh(
    t_norm: float,
) -> tuple[list[MeshFace], dict[str, Vec3]]:
    """3D distributed-systems graph: hub + 5 satellite nodes + animated packet cubes."""
    t = _clamp01(float(t_norm))
    nodes = network_topology_nodes()
    polys: list[MeshFace] = []
    dynamic_anchors: dict[str, Vec3] = {}
    for aid, pos, size, color_hex, edge_hex in nodes:
        polys.extend(
            generate_box_mesh(pos, (size, size, size), color_hex, edge_hex, True)
        )
        dynamic_anchors[aid] = pos

    edges: list[tuple[int, int]] = []
    for i in range(1, len(nodes)):
        edges.append((0, i))
        edges.append((i, 1 if i == len(nodes) - 1 else i + 1))

    # Build segmented 3D quadratic bezier arcs + moving emissive packet cubes.
    for edge_idx, (a_idx, b_idx) in enumerate(edges):
        p_a = nodes[a_idx][1]
        p_b = nodes[b_idx][1]
        mid = (
            0.5 * (p_a[0] + p_b[0]),
            0.5 * (p_a[1] + p_b[1]),
            0.5 * (p_a[2] + p_b[2]) + 0.35,
        )

        def _qbez(u: float, a: Vec3 = p_a, m: Vec3 = mid, b: Vec3 = p_b) -> Vec3:
            inv = 1.0 - u
            return (
                inv * inv * a[0] + 2.0 * inv * u * m[0] + u * u * b[0],
                inv * inv * a[1] + 2.0 * inv * u * m[1] + u * u * b[1],
                inv * inv * a[2] + 2.0 * inv * u * m[2] + u * u * b[2],
            )

        steps = 6
        for s in range(steps):
            pt = _qbez((s + 0.5) / steps)
            polys.extend(
                generate_box_mesh(
                    pt, (0.06, 0.06, 0.06), "#0C4A6E", "#38BDF8", emissive=False
                )
            )
        u_pkt = (t * 1.4 + edge_idx * 0.17) % 1.0
        pkt_pos = _qbez(u_pkt)
        polys.extend(
            generate_box_mesh(
                pkt_pos, (0.14, 0.14, 0.14), "#CA8A04", "#FDE047", emissive=True
            )
        )
    return polys, dynamic_anchors


# ---------------------------------------------------------------------------
# Scene render + anchor tracking
# ---------------------------------------------------------------------------
def _exploded_layers(
    t_norm: float, explode_factor: float
) -> list[tuple[str, Vec3, Vec3, str, str, bool]]:
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


def _build_scene(
    scene_spec: dict[str, Any], t_norm: float
) -> tuple[list[MeshFace], dict[str, Vec3]]:
    """Return (polys, dynamic_anchor_pos); raise on unsupported categories."""
    category = scene_spec.get("category")
    if category == "exploded_hardware_3d":
        explode_factor = float(scene_spec.get("explode_factor", 1.0))
        polys: list[MeshFace] = []
        dynamic_anchor_pos: dict[str, Vec3] = {}
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
    if category == "organic_serpent_3d":
        # Head/body/tail anchors track the moving spine even without local_pos.
        return generate_serpent_mesh(t_norm), {
            "anchor_head": serpent_spine_point(0.88, t_norm),
            "anchor_body": serpent_spine_point(0.5, t_norm),
            "anchor_tail": serpent_spine_point(0.12, t_norm),
        }
    if category == "network_topology_3d":
        return generate_network_topology_mesh(t_norm)
    if category == "external_asset_3d":
        # Software fallback placeholder when Three.js GLTFLoader / Blender isn't used.
        angle = _clamp01(float(t_norm)) * math.pi * 0.7
        faces = generate_box_mesh(
            (0.0, 0.0, 0.0), (1.6, 1.6, 1.6), "#0C4A6E", "#38BDF8", emissive=True
        )
        rotated: list[MeshFace] = []
        for f in faces:
            rotated.append(
                {
                    **f,
                    "verts": [_rotate_z(v, angle) for v in f["verts"]],
                    "normal": _rotate_z(f["normal"], angle),
                }
            )
        return rotated, {"anchor_asset_center": (0.0, 0.0, 0.0)}
    raise NotImplementedError(
        f"unsupported 3D scene category {category!r}; "
        f"supported categories: {', '.join(SUPPORTED_CATEGORIES)}"
    )


def render_3d_scene_and_track(
    canvas: SupersampledCanvas, scene_spec: dict[str, Any], t_norm: float
) -> list[dict[str, Any]]:
    """Render the parametric 3D scene and return tracked anchor screen positions.

    ``scene_spec`` keys: ``category`` (``"exploded_hardware_3d"``,
    ``"orbital_or_field_3d"`` or ``"organic_serpent_3d"`` — anything else
    raises :class:`NotImplementedError`),
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
    draw_list: list[tuple[float, MeshFace, list[tuple[float, float, float, bool]]]] = []
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

    tracked: list[dict[str, Any]] = []
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
