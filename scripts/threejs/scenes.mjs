/**
 * scenes.mjs — Three.js procedural 3D scene builders, Z-up camera rig,
 * lighting presets, and 3D->2D anchor projection for surgical-media.
 *
 * Coordinate convention: Z-up right-handed, matching software_3d_projection.py
 * and blender_runner.py identically so board `local_pos` and `camera_3d` values
 * produce identical framing across all three 3D backends.
 */

export const SUPPORTED_CATEGORIES = Object.freeze([
  "exploded_hardware_3d",
  "orbital_or_field_3d",
  "organic_serpent_3d",
  "network_topology_3d",
  "external_asset_3d",
]);

export const CAMERA_3D_DEFAULTS = Object.freeze({
  focal_length_mm: 50.0,
  fstop: 2.8,
  radius_start: 6.2,
  radius_end: 4.5,
  azimuth_start_deg: -38.0,
  azimuth_end_deg: 42.0,
  elevation_deg: 25.0,
});

const SENSOR_WIDTH_MM = 36.0;
const Z_NEAR_VISIBLE = 0.15;

export function clamp01(t) {
  const v = Number(t);
  if (!Number.isFinite(v) || v < 0.0) return 0.0;
  return v > 1.0 ? 1.0 : v;
}

export function cubicEaseInOut(u) {
  const t = clamp01(u);
  return t < 0.5 ? 4.0 * t * t * t : 1.0 - Math.pow(-2.0 * t + 2.0, 3) / 2.0;
}

export function cameraEyeAt(camCfg, tNorm) {
  const cfg = camCfg || {};
  const r0 = Number(cfg.radius_start ?? CAMERA_3D_DEFAULTS.radius_start);
  const r1 = Number(cfg.radius_end ?? CAMERA_3D_DEFAULTS.radius_end);
  const az0 =
    (Number(cfg.azimuth_start_deg ?? CAMERA_3D_DEFAULTS.azimuth_start_deg) * Math.PI) /
    180.0;
  const az1 =
    (Number(cfg.azimuth_end_deg ?? CAMERA_3D_DEFAULTS.azimuth_end_deg) * Math.PI) /
    180.0;
  const elev =
    (Number(cfg.elevation_deg ?? CAMERA_3D_DEFAULTS.elevation_deg) * Math.PI) / 180.0;

  const uEase = cubicEaseInOut(tNorm);
  const radius = r0 + (r1 - r0) * uEase;
  const az = az0 + (az1 - az0) * uEase;
  return [
    radius * Math.cos(elev) * Math.sin(az),
    -radius * Math.cos(elev) * Math.cos(az),
    radius * Math.sin(elev),
  ];
}

export function serpentSpinePoint(u, tNorm) {
  const uu = clamp01(u);
  const phase = clamp01(tNorm) * 2.0 * Math.PI;
  const x = 0.85 * Math.sin(3.2 * Math.PI * uu + phase) * (0.55 + 0.45 * uu);
  const y = -0.25 + 0.45 * Math.cos(2.1 * Math.PI * uu + phase * 0.5);
  const z = -1.25 + 2.5 * uu;
  return [x, y, z];
}

export function serpentRadiusAt(u) {
  const uu = clamp01(u);
  const base = 0.1 + 0.2 * Math.min(1.0, uu / 0.35);
  const bulge = 0.06 * Math.exp(-Math.pow((uu - 0.9) / 0.08, 2));
  return base + bulge;
}

export function explodedHardwareLayers(tNorm, explodeFactor) {
  const amp = explodeFactor * Math.sin(Math.min(1.0, clamp01(tNorm) * 1.15) * Math.PI * 0.65);
  return [
    {
      anchorId: "anchor_substrate",
      center: [0.0, 0.0, -0.52 - 0.32 * amp],
      scale: [2.25, 2.25, 0.14],
      colorHex: "#0F172A",
      edgeHex: "#A78BFA",
      emissive: false,
    },
    {
      anchorId: "anchor_interposer",
      center: [0.0, 0.0, -0.16 - 0.1 * amp],
      scale: [1.8, 1.8, 0.1],
      colorHex: "#064E3B",
      edgeHex: "#34D399",
      emissive: true,
    },
    {
      anchorId: "anchor_compute_die",
      center: [0.0, 0.0, 0.18 + 0.14 * amp],
      scale: [1.3, 1.3, 0.13],
      colorHex: "#78350F",
      edgeHex: "#FACC15",
      emissive: true,
    },
    {
      anchorId: "anchor_vapor_chamber",
      center: [0.0, 0.0, 0.56 + 0.36 * amp],
      scale: [2.05, 2.05, 0.18],
      colorHex: "#0C4A6E",
      edgeHex: "#38BDF8",
      emissive: true,
    },
  ];
}

export function networkTopologyLayout() {
  const nodes = [
    { id: "anchor_core", pos: [0.0, 0.0, 0.45], radius: 0.34, color: "#0284C7", accent: "#38BDF8" },
  ];
  const ringColors = [
    ["#065F46", "#34D399"],
    ["#78350F", "#FACC15"],
    ["#4C1D95", "#A78BFA"],
    ["#7F1D1D", "#FB7185"],
    ["#0C4A6E", "#38BDF8"],
  ];
  for (let i = 0; i < 5; i++) {
    const angle = (2.0 * Math.PI * i) / 5.0 - Math.PI / 2.0;
    const r = 1.85;
    const z = -0.3 + 0.22 * Math.sin(i * 1.4);
    nodes.push({
      id: `anchor_edge_${i + 1}`,
      pos: [r * Math.cos(angle), r * Math.sin(angle), z],
      radius: 0.22,
      color: ringColors[i][0],
      accent: ringColors[i][1],
    });
  }
  const edges = [];
  for (let i = 1; i < nodes.length; i++) {
    edges.push([0, i]);
    edges.push([i, i === nodes.length - 1 ? 1 : i + 1]);
  }
  return { nodes, edges };
}

function setupLighting(THREE, scene, preset, transparentBg) {
  const isClean = preset === "clean_product_softbox";
  const bgHex = isClean ? 0x0e1525 : 0x050811;
  if (!transparentBg) {
    scene.background = new THREE.Color(bgHex);
    if (!isClean) {
      scene.fog = new THREE.FogExp2(bgHex, 0.028);
    }
  } else {
    scene.background = null;
  }

  if (isClean) {
    const hemi = new THREE.HemisphereLight(0xf8fafc, 0x1e293b, 1.0);
    scene.add(hemi);

    const key = new THREE.DirectionalLight(0xffffff, 2.3);
    key.position.set(4.5, -5.0, 7.0);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    scene.add(key);

    const fill = new THREE.DirectionalLight(0xbae6fd, 1.0);
    fill.position.set(-5.0, -2.0, 3.5);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0xfef08a, 0.85);
    rim.position.set(0.0, 6.0, 4.0);
    scene.add(rim);
  } else {
    const hemi = new THREE.HemisphereLight(0x93c5fd, 0x0f172a, 0.7);
    scene.add(hemi);

    const key = new THREE.DirectionalLight(0x38bdf8, 2.2);
    key.position.set(5.0, -4.5, 7.5);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    scene.add(key);

    const rim = new THREE.PointLight(0xf59e0b, 22.0, 26.0, 1.6);
    rim.position.set(-4.8, 4.2, 4.0);
    scene.add(rim);

    const back = new THREE.PointLight(0xa78bfa, 16.0, 24.0, 1.6);
    back.position.set(0.0, 5.5, -0.5);
    scene.add(back);
  }

  // Subtle ground grid plane at z = -1.25 (Z-up: GridHelper lies in XZ, rotate +90deg on X)
  if (!transparentBg) {
    const grid = new THREE.GridHelper(6.3, 8, isClean ? 0x334155 : 0x1e3a5f, isClean ? 0x1e293b : 0x0e2a3f);
    grid.rotation.x = Math.PI / 2.0;
    grid.position.z = -1.25;
    scene.add(grid);
  }
}

function buildExplodedHardware(THREE, scene, spec) {
  const explodeFactor = Number(spec.explode_factor ?? 1.0);
  const group = new THREE.Group();
  scene.add(group);

  const initialLayers = explodedHardwareLayers(0.0, explodeFactor);
  const layerMeshes = [];

  for (const layer of initialLayers) {
    const holder = new THREE.Group();
    const [sx, sy, sz] = layer.scale;
    const geom = new THREE.BoxGeometry(sx, sy, sz);
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(layer.colorHex),
      metalness: 0.65,
      roughness: 0.28,
      emissive: new THREE.Color(layer.edgeHex),
      emissiveIntensity: layer.emissive ? 0.16 : 0.04,
    });
    const mesh = new THREE.Mesh(geom, mat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    holder.add(mesh);

    const edges = new THREE.EdgesGeometry(geom);
    const lineMat = new THREE.LineBasicMaterial({
      color: new THREE.Color(layer.edgeHex),
    });
    holder.add(new THREE.LineSegments(edges, lineMat));

    // Subtle accent detail: HBM stacks on interposer, heat-fin ribs on vapor chamber
    if (layer.anchorId === "anchor_compute_die") {
      const hbmGeom = new THREE.BoxGeometry(0.24, 0.42, 0.11);
      const hbmMat = new THREE.MeshStandardMaterial({
        color: 0x1e293b,
        metalness: 0.8,
        roughness: 0.2,
        emissive: 0x38bdf8,
        emissiveIntensity: 0.25,
      });
      for (const sxSign of [-1, 1]) {
        for (const sySign of [-0.36, 0.36]) {
          const hbm = new THREE.Mesh(hbmGeom, hbmMat);
          hbm.position.set(sxSign * 0.82, sySign, 0.0);
          holder.add(hbm);
        }
      }
    } else if (layer.anchorId === "anchor_vapor_chamber") {
      const finGeom = new THREE.BoxGeometry(sx * 0.88, 0.04, 0.04);
      const finMat = new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        metalness: 0.85,
        roughness: 0.22,
        emissive: 0x0284c7,
        emissiveIntensity: 0.35,
      });
      for (let f = -3; f <= 3; f++) {
        const fin = new THREE.Mesh(finGeom, finMat);
        fin.position.set(0, f * 0.24, sz * 0.5 + 0.02);
        holder.add(fin);
      }
    }

    group.add(holder);
    layerMeshes.push({ anchorId: layer.anchorId, holder, scale: layer.scale });
  }

  return (tNorm) => {
    const layers = explodedHardwareLayers(tNorm, explodeFactor);
    const dynamicAnchors = {};
    for (let i = 0; i < layers.length; i++) {
      const { center, scale, anchorId } = layers[i];
      layerMeshes[i].holder.position.set(center[0], center[1], center[2]);
      dynamicAnchors[anchorId] = [
        center[0] + scale[0] * 0.42,
        center[1] - scale[1] * 0.42,
        center[2],
      ];
    }
    return dynamicAnchors;
  };
}

function buildOrbitalOrField(THREE, scene) {
  const bigR = 1.65;
  const smallR = 0.36;
  const group = new THREE.Group();
  scene.add(group);

  // Plasma torus core
  const plasmaGeom = new THREE.TorusGeometry(bigR, smallR, 28, 96);
  const plasmaMat = new THREE.MeshPhysicalMaterial({
    color: 0x0284c7,
    emissive: 0x38bdf8,
    emissiveIntensity: 0.65,
    roughness: 0.18,
    metalness: 0.1,
    transmission: 0.35,
    transparent: true,
    opacity: 0.88,
  });
  const plasmaMesh = new THREE.Mesh(plasmaGeom, plasmaMat);
  group.add(plasmaMesh);

  // Inner hot plasma filament
  const coreGeom = new THREE.TorusGeometry(bigR, smallR * 0.38, 16, 84);
  const coreMat = new THREE.MeshStandardMaterial({
    color: 0xe0f2fe,
    emissive: 0x7dd3fc,
    emissiveIntensity: 1.4,
    roughness: 0.1,
  });
  group.add(new THREE.Mesh(coreGeom, coreMat));

  // 12 twisted metallic gold field coils
  const coilMat = new THREE.MeshStandardMaterial({
    color: 0xf59e0b,
    emissive: 0xfde047,
    emissiveIntensity: 0.28,
    metalness: 0.85,
    roughness: 0.22,
  });
  const coilCount = 12;
  for (let i = 0; i < coilCount; i++) {
    const u = (2.0 * Math.PI * i) / coilCount;
    const coilGeom = new THREE.TorusGeometry(smallR * 1.38, 0.065, 14, 36);
    const coil = new THREE.Mesh(coilGeom, coilMat);
    coil.position.set(bigR * Math.cos(u), bigR * Math.sin(u), 0.0);
    coil.rotation.order = "ZYX";
    coil.rotation.z = u;
    coil.rotation.x = Math.PI / 2.0 + 0.28 * Math.sin(3.0 * u);
    coil.castShadow = true;
    group.add(coil);
  }

  // Orbiting field sparks
  const sparkCount = 48;
  const sparkPositions = new Float32Array(sparkCount * 3);
  const sparkGeom = new THREE.BufferGeometry();
  sparkGeom.setAttribute("position", new THREE.BufferAttribute(sparkPositions, 3));
  const sparkMat = new THREE.PointsMaterial({
    color: 0x7dd3fc,
    size: 0.08,
    transparent: true,
    opacity: 0.9,
  });
  const sparks = new THREE.Points(sparkGeom, sparkMat);
  group.add(sparks);

  return (tNorm) => {
    const t = clamp01(tNorm);
    group.rotation.z = t * Math.PI * 1.5;
    const pos = sparkGeom.attributes.position.array;
    for (let i = 0; i < sparkCount; i++) {
      const u = (2.0 * Math.PI * i) / sparkCount + t * 2.0 * Math.PI;
      const v = 3.0 * u + t * 4.0 * Math.PI;
      const rOrbit = smallR * 1.12;
      pos[i * 3] = (bigR + rOrbit * Math.cos(v)) * Math.cos(u);
      pos[i * 3 + 1] = (bigR + rOrbit * Math.cos(v)) * Math.sin(u);
      pos[i * 3 + 2] = rOrbit * Math.sin(v);
    }
    sparkGeom.attributes.position.needsUpdate = true;
    return {};
  };
}

function buildOrganicSerpent(THREE, scene) {
  const rings = 44;
  const sides = 14;
  const group = new THREE.Group();
  scene.add(group);

  const vertCount = rings * sides;
  const positions = new Float32Array(vertCount * 3);
  const colors = new Float32Array(vertCount * 3);
  const indices = [];

  const cJadeA = new THREE.Color("#047857");
  const cJadeB = new THREE.Color("#059669");
  const cHead = new THREE.Color("#CA8A04");

  for (let i = 0; i < rings; i++) {
    const isHead = i >= rings - 5;
    const col = isHead ? cHead : Math.floor(i / 2) % 2 === 0 ? cJadeA : cJadeB;
    for (let j = 0; j < sides; j++) {
      const idx = (i * sides + j) * 3;
      colors[idx] = col.r;
      colors[idx + 1] = col.g;
      colors[idx + 2] = col.b;
    }
  }
  for (let i = 0; i < rings - 1; i++) {
    for (let j = 0; j < sides; j++) {
      const jn = (j + 1) % sides;
      const a = i * sides + j;
      const b = (i + 1) * sides + j;
      const c = (i + 1) * sides + jn;
      const d = i * sides + jn;
      indices.push(a, b, c, a, c, d);
    }
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geom.setIndex(indices);

  const mat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    metalness: 0.25,
    roughness: 0.32,
    emissive: 0x064e3b,
    emissiveIntensity: 0.18,
  });
  const bodyMesh = new THREE.Mesh(geom, mat);
  bodyMesh.castShadow = true;
  group.add(bodyMesh);

  // Glowing eyes
  const eyeGeom = new THREE.SphereGeometry(0.055, 12, 10);
  const eyeMat = new THREE.MeshStandardMaterial({
    color: 0xfde047,
    emissive: 0xfacc15,
    emissiveIntensity: 1.4,
    roughness: 0.15,
  });
  const eyeL = new THREE.Mesh(eyeGeom, eyeMat);
  const eyeR = new THREE.Mesh(eyeGeom, eyeMat);
  group.add(eyeL, eyeR);

  const up = new THREE.Vector3(0, 0, 1);

  return (tNorm) => {
    const posAttr = geom.attributes.position;
    const arr = posAttr.array;

    for (let i = 0; i < rings; i++) {
      const u = i / (rings - 1);
      const center = serpentSpinePoint(u, tNorm);
      const du = 1e-3;
      const p0 = serpentSpinePoint(Math.max(0.0, u - du), tNorm);
      const p1 = serpentSpinePoint(Math.min(1.0, u + du), tNorm);
      const tangent = new THREE.Vector3(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]).normalize();
      const right = new THREE.Vector3().crossVectors(tangent, up).normalize();
      const frameUp = new THREE.Vector3().crossVectors(right, tangent).normalize();
      const r = serpentRadiusAt(u);

      for (let j = 0; j < sides; j++) {
        const theta = (2.0 * Math.PI * j) / sides;
        const ct = Math.cos(theta);
        const st = Math.sin(theta);
        const nx = ct * right.x + st * frameUp.x;
        const ny = ct * right.y + st * frameUp.y;
        const nz = ct * right.z + st * frameUp.z;
        const idx = (i * sides + j) * 3;
        arr[idx] = center[0] + r * nx;
        arr[idx + 1] = center[1] + r * ny;
        arr[idx + 2] = center[2] + r * nz;
      }
    }
    posAttr.needsUpdate = true;
    geom.computeVertexNormals();

    const hc = serpentSpinePoint(0.88, tNorm);
    eyeL.position.set(hc[0] + 0.25, hc[1] - 0.13, hc[2] + 0.05);
    eyeR.position.set(hc[0] + 0.25, hc[1] + 0.13, hc[2] + 0.05);

    return {
      anchor_head: serpentSpinePoint(0.88, tNorm),
      anchor_body: serpentSpinePoint(0.5, tNorm),
      anchor_tail: serpentSpinePoint(0.12, tNorm),
    };
  };
}

function buildNetworkTopology(THREE, scene) {
  const { nodes, edges } = networkTopologyLayout();
  const group = new THREE.Group();
  scene.add(group);

  const nodeRings = [];
  for (const node of nodes) {
    const sphGeom = new THREE.IcosahedronGeometry(node.radius, 2);
    const sphMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(node.color),
      emissive: new THREE.Color(node.accent),
      emissiveIntensity: 0.42,
      metalness: 0.55,
      roughness: 0.22,
    });
    const mesh = new THREE.Mesh(sphGeom, sphMat);
    mesh.position.set(node.pos[0], node.pos[1], node.pos[2]);
    mesh.castShadow = true;
    group.add(mesh);

    const haloGeom = new THREE.TorusGeometry(node.radius * 1.45, 0.022, 10, 32);
    const haloMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(node.accent),
      emissive: new THREE.Color(node.accent),
      emissiveIntensity: 0.9,
      roughness: 0.2,
    });
    const halo = new THREE.Mesh(haloGeom, haloMat);
    halo.position.copy(mesh.position);
    group.add(halo);
    nodeRings.push(halo);
  }

  const curves = [];
  const packets = [];
  const packetGeom = new THREE.SphereGeometry(0.065, 10, 10);

  for (let i = 0; i < edges.length; i++) {
    const [aIdx, bIdx] = edges[i];
    const pA = new THREE.Vector3(...nodes[aIdx].pos);
    const pB = new THREE.Vector3(...nodes[bIdx].pos);
    const mid = pA.clone().add(pB).multiplyScalar(0.5);
    mid.z += 0.35;
    const curve = new THREE.QuadraticBezierCurve3(pA, mid, pB);
    curves.push(curve);

    const tubeGeom = new THREE.TubeGeometry(curve, 24, 0.024, 8, false);
    const tubeMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0ea5e9,
      emissiveIntensity: 0.45,
      transparent: true,
      opacity: 0.85,
    });
    group.add(new THREE.Mesh(tubeGeom, tubeMat));

    const pktMat = new THREE.MeshStandardMaterial({
      color: 0xfde047,
      emissive: 0xfacc15,
      emissiveIntensity: 1.5,
      roughness: 0.1,
    });
    const pkt = new THREE.Mesh(packetGeom, pktMat);
    group.add(pkt);
    packets.push({ mesh: pkt, curve, phase: (i * 0.17) % 1.0 });
  }

  const dynamicAnchors = {};
  for (const node of nodes) {
    dynamicAnchors[node.id] = node.pos;
  }

  return (tNorm) => {
    const t = clamp01(tNorm);
    for (let i = 0; i < nodeRings.length; i++) {
      nodeRings[i].rotation.x = t * Math.PI * 1.2 + i * 0.5;
      nodeRings[i].rotation.y = t * Math.PI * 0.8;
    }
    for (const pkt of packets) {
      const u = (t * 1.4 + pkt.phase) % 1.0;
      const pt = pkt.curve.getPoint(u);
      pkt.mesh.position.copy(pt);
    }
    return dynamicAnchors;
  };
}

async function buildExternalAsset(THREE, scene, spec, GLTFLoader) {
  const assetUrl = spec._runtime && spec._runtime.assetUrl;
  const group = new THREE.Group();
  scene.add(group);

  if (assetUrl && GLTFLoader) {
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(assetUrl);
    const model = gltf.scene || (gltf.scenes && gltf.scenes[0]);
    if (model) {
      // Auto-center and normalize scale to ~2.8 units max extent
      const box = new THREE.Box3().setFromObject(model);
      const size = new THREE.Vector3();
      const center = new THREE.Vector3();
      box.getSize(size);
      box.getCenter(center);
      const maxDim = Math.max(size.x, size.y, size.z, 1e-4);
      const normScale = Number(spec.params?.asset_scale ?? 2.8) / maxDim;
      model.scale.multiplyScalar(normScale);
      model.position.sub(center.multiplyScalar(normScale));
      // Convert standard glTF Y-up to surgical-media Z-up unless disabled
      if (spec.params?.gltf_y_up !== false) {
        model.rotation.x = Math.PI / 2.0;
      }
      model.traverse((obj) => {
        if (obj.isMesh) {
          obj.castShadow = true;
          obj.receiveShadow = true;
        }
      });
      group.add(model);
    }
  } else {
    // Fallback studio pedestal + wireframe hero cube when no asset_path was supplied
    const geom = new THREE.IcosahedronGeometry(1.1, 1);
    const mat = new THREE.MeshStandardMaterial({
      color: 0x0c4a6e,
      emissive: 0x38bdf8,
      emissiveIntensity: 0.4,
      metalness: 0.8,
      roughness: 0.2,
    });
    group.add(new THREE.Mesh(geom, mat));
  }

  const spin = Number(spec.params?.turntable_turns ?? 0.35);
  return (tNorm) => {
    group.rotation.z = clamp01(tNorm) * Math.PI * 2.0 * spin;
    return { anchor_asset_center: [0.0, 0.0, 0.0] };
  };
}

export async function createSceneController(THREE, spec, width, height, extras = {}) {
  const { renderer = null, envTex = null, GLTFLoader = null, customModule = null } = extras;
  const category = spec.category;
  if (!customModule && !SUPPORTED_CATEGORIES.includes(category)) {
    throw new Error(
      `unsupported 3D scene category ${JSON.stringify(category)}; supported: ${SUPPORTED_CATEGORIES.join(", ")}`,
    );
  }

  const scene = new THREE.Scene();
  if (envTex) {
    scene.environment = envTex;
    scene.environmentIntensity =
      spec.lighting_preset === "clean_product_softbox" ? 1.05 : 0.75;
  }
  setupLighting(
    THREE,
    scene,
    spec.lighting_preset || "cyber_studio_volumetric",
    Boolean(spec.transparent_bg),
  );

  const camCfg = spec.camera_3d || {};
  const focalLengthMm = Number(
    camCfg.focal_length_mm ?? CAMERA_3D_DEFAULTS.focal_length_mm,
  );
  const aspect = width / Math.max(1, height);
  const fovX = 2.0 * Math.atan(SENSOR_WIDTH_MM / (2.0 * focalLengthMm));
  const fovYDeg = (2.0 * Math.atan(Math.tan(fovX / 2.0) / aspect) * 180.0) / Math.PI;

  const camera = new THREE.PerspectiveCamera(fovYDeg, aspect, 0.1, 200.0);
  camera.up.set(0, 0, 1);

  let updateCategory;
  if (customModule && typeof customModule.buildScene === "function") {
    updateCategory = await customModule.buildScene({
      THREE,
      scene,
      camera,
      spec,
      renderer,
    });
  } else if (category === "exploded_hardware_3d") {
    updateCategory = buildExplodedHardware(THREE, scene, spec);
  } else if (category === "orbital_or_field_3d") {
    updateCategory = buildOrbitalOrField(THREE, scene);
  } else if (category === "organic_serpent_3d") {
    updateCategory = buildOrganicSerpent(THREE, scene);
  } else if (category === "external_asset_3d") {
    updateCategory = await buildExternalAsset(THREE, scene, spec, GLTFLoader);
  } else {
    updateCategory = buildNetworkTopology(THREE, scene);
  }

  const anchorDefs = Array.isArray(spec.anchors_3d) ? spec.anchors_3d : [];
  const forward = new THREE.Vector3();
  const targetArr = Array.isArray(spec.params?.camera_target)
    ? spec.params.camera_target
    : [0.0, 0.0, 0.0];
  const camTarget = new THREE.Vector3(
    Number(targetArr[0] ?? 0.0),
    Number(targetArr[1] ?? 0.0),
    Number(targetArr[2] ?? 0.0),
  );

  function update(tNorm) {
    const t = clamp01(tNorm);
    const [ex, ey, ez] = cameraEyeAt(camCfg, t);
    camera.position.set(ex + camTarget.x, ey + camTarget.y, ez + camTarget.z);
    camera.lookAt(camTarget);
    camera.updateMatrixWorld(true);
    camera.updateProjectionMatrix();

    const dynamicAnchors = (typeof updateCategory === "function" ? updateCategory(t) : null) || {};
    camera.getWorldDirection(forward);

    const anchors = [];
    for (const aDef of anchorDefs) {
      if (!aDef || typeof aDef !== "object" || !aDef.anchor_id) continue;
      const aid = String(aDef.anchor_id);
      const rawPos = dynamicAnchors[aid] ?? aDef.local_pos ?? [0, 0, 0];
      const worldVec = new THREE.Vector3(
        Number(rawPos[0] ?? 0),
        Number(rawPos[1] ?? 0),
        Number(rawPos[2] ?? 0),
      );
      const zDepth = worldVec.clone().sub(camera.position).dot(forward);
      if (zDepth <= Z_NEAR_VISIBLE) {
        anchors.push({
          anchor_id: aid,
          u: 0.5,
          v: 0.5,
          z_depth: Number(zDepth.toFixed(4)),
          visible: false,
        });
        continue;
      }
      const ndc = worldVec.clone().project(camera);
      const u = 0.5 + 0.5 * ndc.x;
      const v = 0.5 - 0.5 * ndc.y;
      const visible =
        zDepth > Z_NEAR_VISIBLE && u >= 0.02 && u <= 0.98 && v >= 0.02 && v <= 0.98;
      anchors.push({
        anchor_id: aid,
        u: Number(u.toFixed(5)),
        v: Number(v.toFixed(5)),
        z_depth: Number(zDepth.toFixed(4)),
        visible,
      });
    }
    return anchors;
  }

  return { scene, camera, update };
}
